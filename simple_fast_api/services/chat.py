"""Gemini 기반 종목 상담 챗봇 모듈."""
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv(override=True)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash"
    ":generateContent?key={key}"
)


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

    return f"""당신은 "{company_name}"의 DART 공시 데이터를 기반으로 투자 상담을 제공하는 전문 애널리스트입니다.

아래 데이터만을 근거로 사용자의 질문에 답변하세요.
데이터에 없는 내용은 "공시된 데이터에 해당 정보가 없습니다"라고 답하세요.
투자 결정은 항상 투자자 본인의 판단임을 강조하세요.
답변은 간결하고 명확하게, 핵심 수치를 인용하며 작성하세요.

=== {company_name} 사업 개요 ===
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


async def chat_with_gemini(
    system_context: str,
    history: list[dict],
    user_message: str,
    company_name: str = "",
) -> str:
    """
    Gemini 멀티턴 대화를 수행합니다.

    history 형식: [{"role": "user"|"model", "text": "..."}]
    """
    contents = []

    # 시스템 컨텍스트를 첫 user/model 턴으로 삽입
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
