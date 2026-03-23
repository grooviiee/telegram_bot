"""Gemini 기반 종목 상담 챗봇 모듈."""
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv(override=True)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash"
    ":generateContent?key={key}"
)

# ── 워렌 버핏 투자 철학 시스템 프롬프트 ──────────────────────────────────────
BUFFETT_SYSTEM_PROMPT = """당신은 워렌 버핏의 투자 철학을 완벽히 체화한 투자 분석가입니다.
아래 원칙과 제공된 DART 공시 데이터를 함께 활용해 모든 투자 질문에 답변하세요.

## 핵심 투자 원칙

### 1. 기업 가치 (Intrinsic Value)
- 주식은 기업의 일부 소유권이다. 주가가 아닌 기업을 산다.
- 내재가치(Intrinsic Value) = 미래 현금흐름의 현재가치(DCF)
- "가격은 당신이 지불하는 것, 가치는 당신이 얻는 것"

### 2. 안전마진 (Margin of Safety)
- 내재가치 대비 30~50% 이상 할인된 가격에만 매수
- 불확실성에 대한 버퍼 확보가 핵심

### 3. 경제적 해자 (Economic Moat)
- 브랜드 파워, 전환 비용, 네트워크 효과, 원가 우위
- 해자 없는 기업은 장기 보유 불가

### 4. 경영진 신뢰성
- 자본 배분 능력이 뛰어난 경영진
- 주주 친화적 지표: ROE, 자사주 매입, 배당
- "훌륭한 경영진이 망가진 사업을 구할 수 없다"

### 5. 장기 보유
- 보유 기간: 영원히 (기업 가치 유지 시)
- 단기 주가 변동은 무시, 복리의 마법을 최대한 활용

### 6. 능력 범위 (Circle of Competence)
- 이해하지 못하는 사업에는 투자하지 않는다

### 7. 역발상 투자
- "남들이 탐욕스러울 때 두려워하고, 남들이 두려워할 때 탐욕스러워라"

## 분석 프레임워크
질문을 받으면 아래 순서로 답변하세요:
1. 핵심 사업 이해 (제공된 사업 개요 데이터 활용)
2. 경제적 해자 존재 여부 판단
3. 재무 건전성 및 내재가치 추정 (ROE, FCF, 부채비율 데이터 활용)
4. 안전마진 여부 판단 (PBR, PER 등 밸류에이션 데이터 활용)
5. 최종 버핏식 의견

## 말투/스타일
- 버핏의 주주 서한처럼 쉬운 언어로 복잡한 개념 설명
- 야구, 농구 등 비유를 자주 사용
- 한국어로 답변
- 핵심 수치(재무 데이터)를 반드시 인용하며 근거를 제시
"""

BUFFETT_FEW_SHOT_USER = """## 버핏 스타일 답변 예시

Q: 삼성전자 지금 사도 될까요?
A: 먼저 사업을 이해해야 합니다. 삼성전자는 반도체(HBM, DRAM), 스마트폰, 가전이라는 세 개의 엔진을 가진 기업입니다.
해자 관점에서는 반도체 기술력과 제조 규모의 원가 우위가 있지만, 사이클 산업이라는 점에서 해자의 지속성은 제한적입니다.
내재가치 추정 시 반도체 사이클 정상화 이익을 기준으로 PBR 1.0배 이하라면 안전마진이 충분하다고 볼 수 있습니다.
단, 저라면 "10년 뒤 이 회사가 지금보다 더 많은 돈을 벌고 있을까?"를 먼저 자문합니다.

Q: 단기 트레이딩으로 수익 내는 방법이 뭔가요?
A: 저는 그 게임을 하지 않습니다. 단기 시세 예측은 저의 능력 범위(Circle of Competence) 밖입니다.
훌륭한 기업을 적정 가격에 사서 오래 보유하는 것, 그것이 제가 60년간 해온 전부입니다.

위 예시를 참고하여 버핏의 관점으로 분석하겠습니다."""

BUFFETT_FEW_SHOT_MODEL = """네, 워렌 버핏의 투자 철학과 제공된 DART 공시 데이터를 바탕으로 분석해 드리겠습니다.
기업의 본질적 가치, 경제적 해자, 안전마진을 중심으로 답변드리겠습니다. 무엇이 궁금하신가요?"""


def _url() -> str:
    return GEMINI_URL.format(key=os.getenv("GEMINI_API_KEY", ""))


def _fmt_krw(v) -> str:
    if v is None:
        return "N/A"
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}조원"
    if abs_v >= 100_000_000:
        return f"{sign}{abs_v / 100_000_000:.0f}억원"
    return f"{sign}{abs_v:,.0f}원"


def build_system_context(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
    buffett_mode: bool = False,
) -> str:
    """회사 공시 데이터를 Gemini 시스템 컨텍스트 문자열로 변환합니다."""

    # 사업 개요
    biz_text = ""
    for sec in business_sections[:3]:
        blocks = sec.get("blocks", [])
        text_parts = [b["content"] for b in blocks if b.get("type") == "text" and b.get("content")]
        combined = " ".join(text_parts)[:600]
        biz_text += f"\n[{sec['number']}. {sec['title']}]\n{combined}\n"

    # 재무 지표
    fin_rows = ""
    for f in financials[-5:]:
        fin_rows += (
            f"  {f['year']}년: 매출 {_fmt_krw(f.get('revenue'))}, "
            f"영업이익 {_fmt_krw(f.get('operating_income'))}, "
            f"당기순이익 {_fmt_krw(f.get('net_income'))}, "
            f"ROE {f.get('roe') or 'N/A'}%, "
            f"부채비율 {f.get('debt_ratio') or 'N/A'}%, "
            f"순부채비율 {f.get('net_debt_ratio') or 'N/A'}%\n"
        )

    # 배당
    div_rows = ""
    for d in dividends[-5:]:
        div_rows += f"  {d.get('year')}년: 주당 {d.get('dividend', 0):,}원\n"

    # 밸류에이션
    val_text = "N/A"
    if valuation:
        val_text = (
            f"현재가 {valuation.get('price', 0):,.0f}원, "
            f"시가총액 {_fmt_krw(valuation.get('market_cap'))}, "
            f"PER {valuation.get('per') or 'N/A'}x, "
            f"PBR {valuation.get('pbr') or 'N/A'}x, "
            f"PSR {valuation.get('psr') or 'N/A'}x"
        )

    # 최근 공시
    filing_text = ""
    for f in recent_filings[:10]:
        filing_text += f"  - {f.get('rcept_dt', '')} {f.get('report_nm', '')}\n"

    data_context = f"""=== {company_name} 사업 개요 ===
{biz_text}

=== 재무 지표 (최근 5개년) ===
{fin_rows}

=== 배당 이력 ===
{div_rows}

=== 현재 밸류에이션 ===
{val_text}

=== 최근 공시 목록 ===
{filing_text}
"""

    if buffett_mode:
        return f"""{BUFFETT_SYSTEM_PROMPT}

아래는 분석 대상 기업 "{company_name}"의 DART 공시 데이터입니다.
이 데이터를 워렌 버핏의 투자 원칙에 따라 분석하세요.

{data_context}
데이터에 없는 내용은 "공시된 데이터에 해당 정보가 없습니다"라고 답하세요.
"""

    return f"""당신은 "{company_name}"의 DART 공시 데이터를 기반으로 투자 상담을 제공하는 전문 애널리스트입니다.

아래 데이터만을 근거로 사용자의 질문에 답변하세요.
데이터에 없는 내용은 "공시된 데이터에 해당 정보가 없습니다"라고 답하세요.
투자 결정은 항상 투자자 본인의 판단임을 강조하세요.
답변은 간결하고 명확하게, 핵심 수치를 인용하며 작성하세요.

{data_context}
"""


async def chat_with_gemini(
    system_context: str,
    history: list[dict],
    user_message: str,
    company_name: str = "",
    buffett_mode: bool = False,
) -> str:
    """
    Gemini 멀티턴 대화를 수행합니다.

    history 형식: [{"role": "user"|"model", "text": "..."}]
    """
    contents = []

    if buffett_mode:
        # 버핏 모드: 시스템 컨텍스트 + few-shot 예시를 첫 턴으로 삽입
        contents.append({
            "role": "user",
            "parts": [{"text": f"[시스템 컨텍스트]\n{system_context}\n\n{BUFFETT_FEW_SHOT_USER}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": BUFFETT_FEW_SHOT_MODEL}]
        })
    else:
        # 일반 모드
        contents.append({
            "role": "user",
            "parts": [{"text": f"[시스템 컨텍스트]\n{system_context}\n\n위 데이터를 바탕으로 투자 상담을 시작합니다."}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": f"네, {company_name}의 DART 공시 데이터를 바탕으로 질문에 답변드리겠습니다. 무엇이 궁금하신가요?"}]
        })

    # 이전 대화 이력
    for msg in history:
        contents.append({
            "role": msg["role"],
            "parts": [{"text": msg["text"]}]
        })

    # 현재 질문
    contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    payload = {"contents": contents}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            _url(), json=payload, timeout=aiohttp.ClientTimeout(total=60)
        ) as res:
            res.raise_for_status()
            data = await res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
