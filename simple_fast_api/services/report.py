"""Gemini 기반 AI 투자 리포트 생성 모듈.

Thinking Mode를 활용하여 더 깊은 추론 기반 분석을 제공합니다.
"""
import json
from config import GEMINI_REPORT_CONFIG, AI_EVIDENCE_RULES
from utils import fmt_krw, call_gemini
from services.scoring import (
    compute_investment_score,
    compute_owner_earnings,
    compute_dupont,
    compute_yoy_highlights,
)


def _build_data_section(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict] | None = None,
) -> str:
    """프롬프트에 삽입할 기업 데이터 섹션을 생성합니다."""
    sorted_fin = sorted(financials, key=lambda x: x['year'])[-5:]

    # ── 핵심 CAGR 요약 ──
    cagr_text = ""
    if len(sorted_fin) >= 2:
        first, last = sorted_fin[0], sorted_fin[-1]
        years = last['year'] - first['year']
        if years > 0:
            cagr_lines = []
            for key, label in [('revenue', '매출'), ('net_income', '순이익'), ('operating_income', '영업이익')]:
                start_v = first.get(key)
                end_v = last.get(key)
                if start_v is not None and end_v is not None and start_v > 0 and end_v >= 0:
                    cagr = ((end_v / start_v) ** (1 / years) - 1) * 100
                    cagr_lines.append(f"  {label} CAGR: {cagr:+.1f}% ({years}년)")
            if cagr_lines:
                cagr_text = "=== 성장률 요약 ===\n" + "\n".join(cagr_lines) + "\n"

    # ── YoY 하이라이트 ──
    yoy_highlights = compute_yoy_highlights(financials)
    yoy_text = ""
    if yoy_highlights:
        yoy_text = "=== 전년 대비 주요 변화 ===\n" + "\n".join(f"  ⚡ {h}" for h in yoy_highlights) + "\n"

    # 사업 개요 (3개 섹션, 1200자까지 확장)
    biz_text = ""
    for sec in business_sections[:3]:
        blocks = sec.get("blocks", [])
        text_parts = [b["content"] for b in blocks if b.get("type") == "text" and b.get("content")]
        combined = " ".join(text_parts)[:1200]
        biz_text += f"\n[{sec['number']}. {sec['title']}]\n{combined}\n"

    # 재무 테이블 (FCF 항상 포함)
    fin_rows = ""
    for f in sorted_fin:
        row = (
            f"  {f['year']}년 | 매출 {fmt_krw(f.get('revenue'))} | "
            f"영업이익 {fmt_krw(f.get('operating_income'))} | "
            f"당기순이익 {fmt_krw(f.get('net_income'))} | "
            f"ROE {f.get('roe') if f.get('roe') is not None else 'N/A'}% | "
            f"영업이익률 {f.get('operating_margin') if f.get('operating_margin') is not None else 'N/A'}% | "
            f"부채비율 {f.get('debt_ratio') if f.get('debt_ratio') is not None else 'N/A'}% | "
            f"FCF {fmt_krw(f.get('fcf'))}"
        )
        fin_rows += row + "\n"

    # 오너이익 추세
    oe_data = compute_owner_earnings(financials)
    oe_rows = ""
    for oe in oe_data[-5:]:
        if oe['owner_earnings'] is not None:
            ratio_text = f", FCF/NI={oe['fcf_ni_ratio']}" if oe['fcf_ni_ratio'] else ""
            oe_rows += f"  {oe['year']}년: {fmt_krw(oe['owner_earnings'])} ({oe['method']}){ratio_text}\n"

    # DuPont 분해 (최근 3개년)
    dupont_data = compute_dupont(financials)
    dupont_rows = ""
    for dp in dupont_data[-3:]:
        if all(dp[k] is not None for k in ('net_margin_pct', 'asset_turnover', 'leverage')):
            dupont_rows += (
                f"  {dp['year']}년: 순이익률 {dp['net_margin_pct']:.1f}% × "
                f"자산회전율 {dp['asset_turnover']:.2f} × "
                f"레버리지 {dp['leverage']:.2f} → ROE {dp['roe'] or 'N/A'}%\n"
            )

    # 배당 이력
    div_rows = ""
    for d in dividends[-5:]:
        div_rows += f"  {d.get('year')}년: 주당 {d.get('dividend', 0):,}원\n"

    # 밸류에이션
    val_text = "N/A"
    if valuation:
        val_text = (
            f"현재가 {fmt_krw(valuation.get('price'))} | "
            f"시가총액 {fmt_krw(valuation.get('market_cap'))} | "
            f"PER {valuation.get('per') if valuation.get('per') is not None else 'N/A'}x | "
            f"PBR {valuation.get('pbr') if valuation.get('pbr') is not None else 'N/A'}x | "
            f"PSR {valuation.get('psr') if valuation.get('psr') is not None else 'N/A'}x | "
            f"EV/EBIT {valuation.get('ev_ebit') if valuation.get('ev_ebit') is not None else 'N/A'}x"
        )

    # 정량 스코어링 결과
    score_data = compute_investment_score(financials, dividends, valuation)
    score_text = score_data['summary_text']

    # 최근 공시
    filing_text = ""
    if recent_filings:
        for f in recent_filings[:8]:
            filing_text += f"  - {f.get('rcept_dt', '')} {f.get('report_nm', '')}\n"

    sections = [
        cagr_text,
        yoy_text,
        f"=== 사업 개요 ===\n{biz_text}",
        f"=== 재무 지표 (최근 5개년) ===\n{fin_rows}",
        f"=== 오너이익 추세 ===\n{oe_rows or '  데이터 부족'}",
        f"=== DuPont ROE 분해 (최근 3개년) ===\n{dupont_rows or '  데이터 부족'}",
        f"=== 배당 이력 ===\n{div_rows or '  데이터 없음'}",
        f"=== 현재 밸류에이션 ===\n{val_text}",
        f"\n{score_text}",
    ]
    if filing_text:
        sections.append(f"=== 최근 공시 목록 ===\n{filing_text}")
    return "\n".join(s for s in sections if s)


STANDARD_REPORT_TEMPLATE = """당신은 한국 주식 전문 애널리스트입니다.
아래 제공된 DART 공시 데이터와 정량 분석 결과를 바탕으로 "{company_name}"에 대한 종합 투자 리포트를 작성하세요.

## 분석 원칙
1. 반드시 제공된 데이터의 실제 수치를 인용하며 근거를 제시하세요.
2. "정량 투자 스코어" 섹션의 자동 계산 결과를 참고하되, 맹목적으로 따르지 말고 맥락을 고려해 해석하세요.
3. "자동 감지 시그널"에서 발견된 이상 신호는 반드시 리포트에 언급하세요.
4. 단순 수치 나열이 아닌, 투자 판단에 도움되는 인사이트를 제공하세요.
5. YoY 변화, 추세, 동종업계 대비 수준을 고려하여 분석하세요.
6. DuPont 분해 결과를 활용하여 ROE의 질적 원천(수익성 vs 레버리지)을 반드시 판단하세요.
7. 오너이익 데이터를 활용하여 기업의 실질 현금창출력을 평가하세요.
8. 정량 스코어와 당신의 정성적 판단이 다를 경우, 그 이유를 명시하세요.

{data_section}

---
위 데이터를 분석하여 아래 형식으로 리포트를 작성하세요.
각 항목은 3~5문장으로 핵심만 간결하게 작성하세요.

## {company_name} 종합 투자 리포트

### 1. 사업 경쟁력
(핵심 사업 구조, 경쟁 우위, 시장 내 포지셔닝)

### 2. 재무 건전성 및 이익의 질
(부채 구조, 유동성, FCF 창출력, 오너이익 추세, DuPont 분석 — ROE가 수익성에서 오는지 레버리지에서 오는지 판단)

### 3. 성장성 분석
(매출·이익 성장 추세와 CAGR, 최근 YoY 변화, 성장 지속 가능성 평가)

### 4. 수익성 분석
(ROE 지속성과 DuPont 분해 해석, 영업이익률 추세, 이익의 질 — FCF/순이익 비율)

### 5. 밸류에이션 평가
(PER·PBR·EV/EBIT 수준 평가, ROE 대비 PBR 적정성, 안전마진 수준)

### 6. 배당 매력도
(배당 지속성, 배당 성향, 배당 성장 추세)

### 7. 주요 리스크
(투자 시 주의해야 할 리스크 요인 2~3가지)

### 8. 종합 투자 의견
**투자 등급: [적극 매수 / 매수 / 중립 / 비중축소 / 매도]**
**정량 스코어: {company_name} 점/100 (등급)**
(한 문단 종합 의견 — 핵심 투자 포인트와 리스크를 균형있게 제시)

---
*본 리포트는 AI가 DART 공시 데이터를 정량 분석한 참고 자료이며, 투자 결정의 책임은 투자자 본인에게 있습니다.*
"""

BUFFETT_REPORT_TEMPLATE = """당신은 워렌 버핏의 투자 철학을 완벽히 체화한 투자 분석가입니다.
아래 DART 공시 데이터와 정량 분석 결과를 기반으로 "{company_name}"에 대한 버핏 스타일 투자 리포트를 작성하세요.

## 버핏 투자 원칙 (분석 시 반드시 적용)
- 경제적 해자(Economic Moat): 브랜드, 전환비용, 네트워크 효과, 원가 우위. 핵심 테스트 = 가격 결정력
- 내재가치(Intrinsic Value): 오너이익 = 당기순이익 + 감가상각 - Capex. ROE 지속성, FCF 창출 능력
- 안전마진(Margin of Safety): 내재가치 대비 30~50% 할인된 가격. 불확실성 클수록 높은 마진 요구
- 이익의 질: FCF > 순이익이면 이익의 질이 높음. 이 비율("FCF/NI 비율")을 반드시 확인
- 경영진 평가: 자본 배분 능력. ROE 15% 이상 재투자 or 배당/자사주 환원
- 10년 보유 테스트: 10년 뒤 이 회사가 더 많은 돈을 벌고 있을까?

## 분석 원칙
1. "정량 투자 스코어"와 "자동 감지 시그널"을 반드시 참고하여 분석하세요.
2. 실제 수치를 인용하며, 버핏의 기준(ROE 15%, 부채 3~4년 내 상환 가능 등)과 비교하세요.
3. DuPont 분해로 ROE의 원천을 반드시 파악하세요 (레버리지 의존 vs 수익성 기반).
4. 오너이익 추세를 분석하여 주주에게 실제 돌아갈 수 있는 현금 흐름을 판단하세요.
5. 버핏의 주주 서한처럼 쉽고 직관적인 비유를 사용하세요 (야구, 슈퍼마켓, 농장 등).
6. 정량 스코어와 당신의 판단이 다를 경우, 그 이유를 명시하세요.

{data_section}

---
위 데이터를 분석하여 아래 형식으로 버핏 스타일 리포트를 작성하세요.
각 항목은 3~5문장으로 핵심만 간결하게, 실제 수치를 인용하며 작성하세요.

## {company_name} — 워렌 버핏 스타일 투자 리포트

### 1. 사업 이해 (Circle of Competence)
(이 사업을 10살 어린이에게 설명할 수 있는가? 핵심 수익 구조와 사업 모델의 단순성)

### 2. 경제적 해자 (Economic Moat)
**해자 등급: [넓음 / 보통 / 좁음 / 없음]**
(해자 종류와 강도를 구체적 근거와 함께 평가. ROE 지속성, DuPont 분해 결과, 가격 결정력 중심)

### 3. 재무 건전성 및 내재가치
(ROE 지속성 → 버핏 기준 15% 대비 평가, DuPont ROE 원천 분석, FCF/순이익 비율, 부채 상환 능력, 오너이익 추세 및 추정)

### 4. 안전마진 (Margin of Safety)
(ROE 기반 적정 PBR 추정, 오너이익 기반 내재가치 추정, 현재 PBR·PER과 비교, 매수 적정 가격대 구체적 제시)

### 5. 배당 및 주주 환원
(배당 지속성, 배당성향, 잉여현금 사용 효율성)

### 6. 주요 리스크
(버핏이 가장 우려할 리스크 2~3가지 — 해자 침식, 경기순환성, 자본배분 비효율 등)

### 7. 버핏의 최종 의견
**[매수 적극 고려 / 적정 가격 대기 / 관심 종목 보류 / 투자 부적합]**
**정량 스코어: 점/100 (등급)**
("만약 내가 이 주식을 10년 보유해야 한다면..." 형식으로 작성. 한 문단.)

---
*본 리포트는 워렌 버핏의 투자 철학을 AI가 적용한 참고 자료이며, 투자 결정의 책임은 투자자 본인에게 있습니다.*
"""


async def generate_report(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
    data_quality: dict | None = None,
) -> str:
    data_section = _build_data_section(
        company_name, business_sections, financials, dividends, valuation, recent_filings
    )
    prompt = AI_EVIDENCE_RULES + STANDARD_REPORT_TEMPLATE.format(company_name=company_name, data_section=data_section)
    if data_quality:
        prompt += "\n분석 데이터 출처와 한계:\n" + json.dumps(data_quality, ensure_ascii=False)
    return await call_gemini(prompt, generation_config=GEMINI_REPORT_CONFIG, timeout=120)


async def generate_buffett_report(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
    data_quality: dict | None = None,
) -> str:
    data_section = _build_data_section(
        company_name, business_sections, financials, dividends, valuation, recent_filings
    )
    prompt = AI_EVIDENCE_RULES + BUFFETT_REPORT_TEMPLATE.format(company_name=company_name, data_section=data_section)
    if data_quality:
        prompt += "\n분석 데이터 출처와 한계:\n" + json.dumps(data_quality, ensure_ascii=False)
    return await call_gemini(prompt, generation_config=GEMINI_REPORT_CONFIG, timeout=120)
