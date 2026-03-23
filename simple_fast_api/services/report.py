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


def _build_buffett_prompt(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
) -> str:
    """워렌 버핏 투자 철학 기반 리포트 프롬프트를 생성합니다."""
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
            f"FCF {_fmt_krw(f.get('fcf'))}\n"
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

    return f"""당신은 워렌 버핏의 투자 철학을 완벽히 체화한 투자 분석가입니다.
아래 DART 공시 데이터를 기반으로 "{company_name}"에 대한 버핏 스타일 투자 리포트를 작성하세요.

## 버핏 투자 원칙 체크리스트 (분석 시 반드시 적용)
- 경제적 해자(Economic Moat): 브랜드, 전환비용, 네트워크 효과, 원가 우위
- 내재가치(Intrinsic Value): ROE 지속성, FCF 창출 능력, 이익 성장 추세
- 안전마진(Margin of Safety): PBR, PER이 내재가치 대비 충분히 낮은가
- 경영진 신뢰성: ROE 추세, 자본 배분 효율성
- 능력 범위: 사업 구조가 이해 가능한가

=== 사업 개요 ===
{biz_text}

=== 재무 지표 (최근 5개년) ===
{fin_rows}

=== 배당 이력 ===
{div_rows}

=== 현재 밸류에이션 ===
{val_text}

---
위 데이터를 분석하여 아래 형식으로 버핏 스타일 리포트를 작성하세요.
각 항목은 2~4문장으로 핵심만 간결하게, 실제 수치를 인용하며 작성하세요.
버핏의 주주 서한처럼 쉽고 직관적인 언어를 사용하고, 비유를 적극 활용하세요.

## {company_name} — 워렌 버핏 스타일 투자 리포트

### 1. 사업 이해 (Circle of Competence)
(이 사업을 10살 어린이에게 설명할 수 있는가? 핵심 수익 구조 요약)

### 2. 경제적 해자 (Economic Moat)
(해자 종류와 강도 평가: 강함 / 보통 / 약함 / 없음, 근거 제시)

### 3. 재무 건전성 및 내재가치
(ROE 지속성, FCF 창출, 부채 수준으로 내재가치 방향성 판단)

### 4. 안전마진 (Margin of Safety)
(현재 PBR·PER 기준 저평가/적정/고평가 여부, 매수 가능 가격대 제시)

### 5. 배당 및 주주 환원
(배당 지속성, 배당 성향, 버핏식 배당 재투자 관점 평가)

### 6. 주요 리스크
(버핏이 가장 우려할 리스크 2~3가지)

### 7. 버핏의 최종 의견
**[매수 적극 고려 / 적정 가격 대기 / 관심 종목 보류 / 투자 부적합]**
(한 문단 — "만약 내가 이 주식을 10년 보유해야 한다면..." 형식으로 작성)

---
*본 리포트는 워렌 버핏의 투자 철학을 AI가 적용한 참고 자료이며, 투자 결정의 책임은 투자자 본인에게 있습니다.*
"""


async def generate_buffett_report(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
) -> str:
    """워렌 버핏 투자 철학 기반 종합 투자 리포트를 생성합니다."""
    prompt = _build_buffett_prompt(
        company_name, business_sections, financials, dividends, valuation, recent_filings
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    async with aiohttp.ClientSession() as session:
        async with session.post(_gemini_url(), json=payload, timeout=aiohttp.ClientTimeout(total=60)) as res:
            res.raise_for_status()
            data = await res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
