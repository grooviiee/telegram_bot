"""공유 유틸리티 함수. 여러 모듈에서 사용하는 공통 로직을 제공합니다."""
import json
import aiohttp
from config import GEMINI_URL, GEMINI_SUMMARY_CONFIG, GEMINI_MAX_TOOL_ROUNDS


def fmt_krw(v) -> str:
    """금액을 한국식 단위(조/억/원)로 포맷합니다."""
    if v is None:
        return "N/A"
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}조원"
    if abs_v >= 100_000_000:
        return f"{sign}{abs_v / 100_000_000:.0f}억원"
    return f"{sign}{abs_v:,.0f}원"


def fmt_shares(n: int) -> str:
    """주식 수를 만주/주 단위로 포맷합니다."""
    if abs(n) >= 10_000:
        return f"{n / 10_000:.1f}만주"
    return f"{n:,}주"


def _extract_text_from_candidates(candidates: list[dict]) -> str:
    """Gemini 응답 candidates에서 텍스트를 추출합니다.

    Thinking mode가 활성화된 경우 'thought' 파트를 건너뛰고
    실제 응답 텍스트만 반환합니다.
    """
    if not candidates:
        return "(AI 응답 생성 실패)"

    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = []
    for part in parts:
        # thought 파트 건너뛰기 (thinking mode 결과)
        if part.get("thought"):
            continue
        if "text" in part:
            text_parts.append(part["text"])

    return "\n".join(text_parts) if text_parts else "(AI 응답 생성 실패)"


async def call_gemini(
    prompt: str,
    *,
    system_instruction: str | None = None,
    contents: list[dict] | None = None,
    generation_config: dict | None = None,
    timeout: int = 60,
) -> str:
    """Gemini API를 호출하여 텍스트 응답을 반환합니다.

    Args:
        prompt: 단일 프롬프트 (contents가 None일 때 사용)
        system_instruction: 시스템 프롬프트 (선택)
        contents: 멀티턴 대화 콘텐츠 (prompt 대신 사용)
        generation_config: 생성 파라미터 (기본: GEMINI_SUMMARY_CONFIG)
        timeout: 타임아웃 초

    Returns:
        Gemini 응답 텍스트. 실패 시 에러 메시지 문자열.
    """
    if generation_config is None:
        generation_config = GEMINI_SUMMARY_CONFIG

    payload: dict = {"generationConfig": generation_config}

    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    if contents:
        payload["contents"] = contents
    else:
        payload["contents"] = [{"parts": [{"text": prompt}]}]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GEMINI_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as res:
                if res.status != 200:
                    error_body = await res.text()
                    print(f"[Gemini API Error] status={res.status}, body={error_body[:500]}")
                    return "(AI 응답 생성 실패)"
                data = await res.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    print(f"[Gemini] No candidates returned: {data}")
                    return "(AI 응답 생성 실패)"
                return _extract_text_from_candidates(candidates)
    except Exception as e:
        print(f"[Gemini] 호출 오류: {e}")
        return "(AI 응답 생성 실패)"


async def call_gemini_with_tools(
    *,
    system_instruction: str,
    contents: list[dict],
    tools: list[dict],
    tool_executor,
    generation_config: dict | None = None,
    timeout: int = 90,
) -> str:
    """Function Calling을 지원하는 Gemini API 호출.

    AI가 functionCall로 응답하면 tool_executor를 실행하고 결과를 다시 전달합니다.
    최대 GEMINI_MAX_TOOL_ROUNDS 번까지 반복하며, 최종 텍스트 응답을 반환합니다.

    Args:
        system_instruction: 시스템 프롬프트
        contents: 대화 콘텐츠 (내부 복사본을 사용하므로 원본은 수정되지 않음)
        tools: Gemini function declarations 리스트
        tool_executor: async def(name: str, args: dict) -> dict 콜백
        generation_config: 생성 파라미터
        timeout: 타임아웃 초

    Returns:
        최종 텍스트 응답. 실패 시 에러 메시지.
    """
    if generation_config is None:
        generation_config = GEMINI_SUMMARY_CONFIG

    payload_base: dict = {
        "generationConfig": generation_config,
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "tools": [{"functionDeclarations": tools}],
    }

    working_contents = list(contents)

    try:
        async with aiohttp.ClientSession() as session:
            for _round in range(GEMINI_MAX_TOOL_ROUNDS):
                payload = {**payload_base, "contents": working_contents}

                async with session.post(
                    GEMINI_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as res:
                    if res.status != 200:
                        error_body = await res.text()
                        print(f"[Gemini Tool] API Error status={res.status}, body={error_body[:500]}")
                        return "(AI 응답 생성 실패)"
                    data = await res.json()

                candidates = data.get("candidates", [])
                if not candidates:
                    print(f"[Gemini Tool] No candidates: {data}")
                    return "(AI 응답 생성 실패)"

                response_parts = candidates[0].get("content", {}).get("parts", [])

                # functionCall 파트가 있는지 확인
                function_calls = [p for p in response_parts if "functionCall" in p]

                if not function_calls:
                    # 텍스트 응답 — 최종 결과
                    return _extract_text_from_candidates(candidates)

                # 모델의 응답을 대화에 추가
                working_contents.append({"role": "model", "parts": response_parts})

                # 모든 function call 실행
                function_response_parts = []
                for fc_part in function_calls:
                    fc = fc_part["functionCall"]
                    fn_name = fc["name"]
                    fn_args = fc.get("args", {})
                    print(f"[Gemini Tool] Calling {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:200]})")

                    try:
                        result = await tool_executor(fn_name, fn_args)
                    except Exception as e:
                        print(f"[Gemini Tool] Executor error for {fn_name}: {e}")
                        result = {"error": str(e)}

                    function_response_parts.append({
                        "functionResponse": {
                            "name": fn_name,
                            "response": result,
                        }
                    })

                # function response를 대화에 추가
                working_contents.append({"role": "user", "parts": function_response_parts})

            # 최대 라운드 후 마지막 한 번 더 호출 (텍스트 응답 유도)
            payload = {**payload_base, "contents": working_contents}
            async with session.post(
                GEMINI_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as res:
                if res.status != 200:
                    return "(AI 응답 생성 실패)"
                data = await res.json()
            return _extract_text_from_candidates(data.get("candidates", []))

    except Exception as e:
        print(f"[Gemini Tool] 호출 오류: {e}")
        return "(AI 응답 생성 실패)"
