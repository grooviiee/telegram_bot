"""Gemini 기반 AI 투자 리포트 생성 모듈."""
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _gemini_url() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    return f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={key}"


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


def _build_prompt(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
) -> str:
    # 사업 개요 (1~2항만 요약)
    biz_text = ""
    for sec in business_sections[:2]:
        blocks = sec.get("blocks", [])
        text_parts = [b["content"] for b in blocks if b.get("type") == "text" and b.get("content")]
        combined = " ".join(text_parts)[:800]
        biz_text += f"\n[{sec['number']}. {sec['title']}]\n{combined}\n"

    # 재무 테이블
    fin_rows = ""
    for f in financials[-5:]:
        fin_rows += (
            f"  {f['year']}년 | 매출 {_fmt_krw(f.get('revenue'))} | "
            f"영업이익 {_fmt_krw(f.get('operating_income'))} | "
            f"당기순이익 {_fmt_krw(f.get('net_income'))} | "
            f"ROE {f.get('roe') or 'N/A'}% | "
            f"부채비율 {f.get('debt_ratio') or 'N/A'}% | "
            f"순부채비율 {f.get('net_debt_ratio') or 'N/A'}%\n"
        )

    # 배당 이력
    div_rows = ""
    for d in dividends[-5:]:
        div_rows += f"  {d.get('year')}년: 주당 {d.get('dividend', 0):,}원\n"

    # 밸류에이션
    val_text = "N/A"
    if valuation:
        val_text = (
            f"현재가 {valuation.get('price', 0):,.0f}원 | "
            f"시가총액 {_fmt_krw(valuation.get('market_cap'))} | "
            f"PER {valuation.get('per') or 'N/A'}x | "
            f"PBR {valuation.get('pbr') or 'N/A'}x | "
            f"PSR {valuation.get('psr') or 'N/A'}x | "
            f"EV/EBIT {valuation.get('ev_ebit') or 'N/A'}x"
        )

    # 최근 공시
    filing_text = ""
    for f in recent_filings[:8]:
        filing_text += f"  - {f.get('rcept_dt', '')} {f.get('report_nm', '')}\n"

    prompt = f"""당신은 한국 주식 전문 애널리스트입니다.
아래 제공된 DART 공시 데이터를 바탕으로 "{company_name}"에 대한 종합 투자 리포트를 작성하세요.

=== 사업 개요 ===
{biz_text}

=== 재무 지표 (최근 5개년) ===
{fin_rows}

=== 배당 이력 ===
{div_rows}

=== 현재 밸류에이션 ===
{val_text}

=== 최근 공시 목록 ===
{filing_text}

---
위 데이터를 분석하여 아래 형식으로 리포트를 작성하세요.
각 항목은 2~4문장으로 핵심만 간결하게 작성하세요.

## {company_name} 종합 투자 리포트

### 1. 사업 경쟁력
(핵심 사업 구조와 경쟁 우위 요약)

### 2. 재무 건전성
(최근 재무 추세, 부채 수준, 현금흐름 평가)

### 3. 성장성 분석
(매출·이익 성장 추세, 향후 성장 가능성)

### 4. 밸류에이션 평가
(현재 주가 수준이 저평가/적정/고평가인지 판단)

### 5. 배당 매력도
(배당 지속성, 배당 성향 평가)

### 6. 주요 리스크
(투자 시 주의해야 할 리스크 요인 2~3가지)

### 7. 종합 투자 의견
**[긍정적 / 중립 / 부정적]**
(한 문단 종합 의견)

---
*본 리포트는 AI가 공시 데이터를 분석한 참고 자료이며, 투자 결정의 책임은 투자자 본인에게 있습니다.*
"""
    return prompt


async def generate_report(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
) -> str:
    prompt = _build_prompt(
        company_name, business_sections, financials, dividends, valuation, recent_filings
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    async with aiohttp.ClientSession() as session:
        async with session.post(_gemini_url(), json=payload, timeout=aiohttp.ClientTimeout(total=60)) as res:
            res.raise_for_status()
            data = await res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
