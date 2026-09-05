"""Gemini 기반 종목 상담 챗봇 모듈.

Function Calling과 Thinking Mode를 활용하여
동적 데이터 조회 및 심층 추론이 가능한 AI 투자 자문을 제공합니다.
"""
import asyncio
import json
from datetime import datetime

from config import GEMINI_CHAT_CONFIG, AI_EVIDENCE_RULES
from utils import fmt_krw, call_gemini_with_tools
from services.dart import fetch_dart_financials_q, fetch_filing_list
from services.scoring import (
    compute_investment_score,
    compute_owner_earnings,
    compute_dupont,
    compute_yoy_highlights,
)

# ── Function Calling 도구 정의 ──────────────────────────────────────────────

CHAT_TOOLS = [
    {
        "name": "get_quarterly_financials",
        "description": "특정 연도·분기의 상세 재무데이터(매출, 영업이익, 순이익 등)를 DART에서 조회합니다. 분기별 추이를 분석하거나 특정 분기 실적을 확인할 때 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "year": {"type": "string", "description": "조회 연도 (예: 2024)"},
                "quarter": {
                    "type": "string",
                    "enum": ["Q1", "Q2", "Q3", "Q4"],
                    "description": "조회 분기",
                },
            },
            "required": ["year", "quarter"],
        },
    },
    {
        "name": "calculate_intrinsic_value",
        "description": "오너이익 기반 DCF 간이 모델로 주당 내재가치를 추정합니다. 할인율과 영구성장률을 입력하면 적정 주가 범위를 계산합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "discount_rate": {
                    "type": "number",
                    "description": "할인율 (예: 0.10은 10%). 보수적 투자자는 0.12~0.15, 적정 수준은 0.08~0.10",
                },
                "growth_rate": {
                    "type": "number",
                    "description": "영구성장률 (예: 0.02는 2%). 보통 GDP 성장률 수준인 0.02~0.03 사용",
                },
            },
            "required": ["discount_rate", "growth_rate"],
        },
    },
    {
        "name": "search_filings",
        "description": "DART에서 특정 키워드가 포함된 공시를 검색합니다. 배당, 합병, 유상증자, 자기주식 등 특정 이벤트를 확인할 때 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "검색 키워드 (예: 배당, 합병, 유상증자, 자기주식, 전환사채)",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_dupont_analysis",
        "description": "DuPont 분해 분석을 수행합니다. ROE를 순이익률 × 자산회전율 × 재무레버리지로 분해하여 ROE의 원천을 파악합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "string",
                    "description": "분석 대상 연도 (예: 2024). 'all'이면 전체 연도 분석",
                },
            },
            "required": ["year"],
        },
    },
]


# ── 워렌 버핏 투자 철학 시스템 프롬프트 ──────────────────────────────────────

BUFFETT_SYSTEM_PROMPT = """당신은 워렌 버핏의 투자 철학을 완벽히 체화한 최고 수준의 투자 분석가입니다.

## 절대 규칙 (반드시 준수)
1. 반드시 아래 [기업 데이터] 섹션에 제공된 DART 공시 데이터만을 근거로 답변하세요.
2. 데이터에 없는 내용을 추측하거나 만들어내지 마세요. "공시 데이터에 해당 정보가 없습니다"라고 솔직히 답하세요.
3. 사용자의 질문을 정확히 파악하고, 질문에 직접 답하세요. 관련 없는 내용으로 빠지지 마세요.
4. 숫자를 인용할 때는 반드시 제공된 데이터의 수치를 그대로 사용하세요. 임의로 변경하지 마세요.
5. 단정적 매수/매도 추천은 하지 않습니다. 버핏식 사고 과정을 보여주는 데 집중하세요.
6. 추가 데이터가 필요하면 제공된 도구(함수)를 적극 활용하세요. 분기별 실적, 내재가치 계산, 공시 검색, DuPont 분석 등을 직접 호출할 수 있습니다.

## 도구 활용 가이드
- 사용자가 분기별 실적을 물으면 → get_quarterly_financials 호출
- 적정 주가/내재가치를 물으면 → calculate_intrinsic_value 호출 (보수적/중립/낙관 시나리오로 여러 번 호출 가능)
- 특정 공시(배당, 합병 등)에 대해 물으면 → search_filings 호출
- ROE의 원천을 분석할 때 → get_dupont_analysis 호출
- 도구 결과를 받으면, 그 데이터를 버핏의 관점에서 해석하여 답변하세요

## 분석 프로세스 (내부적으로 이 순서를 따르되, 답변에 이 프로세스를 노출하지 마세요)
1단계: 사용자의 질문 의도를 정확히 파악 (무엇을 알고 싶은지?)
2단계: 필요한 데이터가 컨텍스트에 있는지 확인. 없으면 도구 호출로 조회
3단계: 제공된 데이터에서 관련 수치를 찾기
4단계: 버핏의 투자 원칙 중 적용 가능한 것을 선택
5단계: 데이터 + 원칙을 결합하여 논리적 답변 구성
6단계: 불확실한 부분은 명시적으로 한계를 언급

## 핵심 투자 원칙

### 1. 기업 가치 (Intrinsic Value)
- 주식은 기업의 일부 소유권이다. 주가가 아닌 기업을 산다.
- 내재가치 = 미래 오너이익(Owner Earnings)의 현재가치
- 오너이익 = 당기순이익 + 감가상각비 - 유지보수 자본지출(Capex)
- "가격은 당신이 지불하는 것, 가치는 당신이 얻는 것"

### 2. 안전마진 (Margin of Safety)
- 내재가치 대비 30~50% 이상 할인된 가격에만 매수
- 불확실성이 클수록 더 큰 안전마진 요구
- 적정 매수가 = 내재가치 × (1 - 안전마진율)

### 3. 경제적 해자 (Economic Moat)
- **강한 해자 신호**: 10년 이상 ROE 15% 초과 유지, 가격 인상에도 고객 이탈 없음
- 해자 종류: 브랜드 파워, 전환 비용, 네트워크 효과, 원가 우위, 효율적 규모
- **가격 결정력(Pricing Power)이 해자의 최종 시험**
- DuPont 분해로 ROE의 원천 파악 → 레버리지가 아닌 수익성과 효율성에서 오는 ROE가 진정한 해자

### 4. 재무 건강 기준
- ROE: 부채 없이 10년 연속 15% 이상이면 강한 해자 신호
- ROIC > WACC 여야 가치 창출
- 부채: 이익으로 3~4년 내 상환 가능한 수준이 이상적
- FCF > 순이익이면 이익의 질이 높다 (FCF/NI 비율 > 1.0)
- 오너이익이 지속 성장하는지 추세 확인

### 5. 경영진 평가
- 자본 배분이 핵심: ROE 15% 이상 재투자 or 배당/자사주 환원
- "훌륭한 경영진이 망가진 사업을 구할 수 없다"

### 6. 장기 보유 & 복리
- "10년 보유할 자신이 없으면 10분도 보유하지 마라"
- 단기 주가 변동은 Mr. Market의 변덕

### 7. 능력 범위 (Circle of Competence)
- 이해하지 못하는 사업에는 투자하지 않는다

### 8. 역발상 투자
- "남들이 탐욕스러울 때 두려워하고, 남들이 두려워할 때 탐욕스러워라"

## 질문 유형별 분석 가이드
- **밸류에이션 질문** → 안전마진 중심 분석. calculate_intrinsic_value 도구로 시나리오별 적정가 계산
- **성장성 질문** → CAGR, YoY 추세, 매출/이익 성장률 비교. 필요시 분기 데이터 조회
- **재무 건전성 질문** → DuPont 분해, 부채비율 추이, FCF 품질, 오너이익 추세
- **배당 관련 질문** → 배당 지속성, 성향, 성장률. search_filings로 배당 관련 공시 확인
- **경영진/지배구조 질문** → 자본 배분 이력, 자사주/배당 정책, search_filings 활용
- **산업/경쟁 질문** → 해자 분석 프레임워크, 가격 결정력, Porter's 5 Forces 관점

## 다층 분석 프레임워크
1. **DuPont 분석**: ROE = 순이익률 × 자산회전율 × 레버리지 → ROE의 질적 원천 파악
2. **오너이익 분석**: 기업이 실제로 주주에게 돌려줄 수 있는 현금 흐름
3. **해자 지속성**: 5년간 ROE 추세, 영업이익률 추세로 해자 침식/강화 판단
4. **안전마진 정량화**: DCF 기반 내재가치 vs 현재 주가 → 할인율 계산

## 말투/스타일
- 버핏의 주주 서한처럼 쉬운 언어로 복잡한 개념 설명
- 일상적 비유를 자연스럽게 사용 (야구, 슈퍼마켓, 농장 등)
- 한국어로 답변
- 핵심 수치를 반드시 인용하며 근거를 제시
- 질문 범위에 맞는 길이로 답변 (간단한 질문에 장문 금지)
- 확신이 부족한 부분은 "다만, ~에 대해서는 추가 확인이 필요합니다"와 같이 명시
"""

BUFFETT_FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "parts": [{"text": "삼성전자 지금 사도 될까요?"}],
    },
    {
        "role": "model",
        "parts": [{"text": "먼저 사업을 이해해야 합니다. 삼성전자는 반도체(HBM, DRAM), 스마트폰, 가전이라는 세 개의 엔진을 가진 기업입니다.\n\n해자 관점에서 반도체 기술력과 제조 규모의 원가 우위가 있지만, 사이클 산업이라는 특성상 해자의 '지속성'이 제한적입니다. 코카콜라처럼 \"가격을 10% 올려도 고객이 떠나지 않는가?\"라는 질문에 반도체는 자신 있게 Yes라고 답하기 어렵습니다.\n\n재무 데이터를 보면 ROE가 10년 평균 15%를 안정적으로 유지하는지, FCF가 순이익보다 꾸준히 높은지 확인해야 합니다. 정상화 이익 기준 PBR 1.0배 이하라면 안전마진이 형성된다고 볼 수 있습니다.\n\n저라면 \"10년 뒤 이 회사가 지금보다 확실히 더 많은 돈을 벌고 있을까?\"를 먼저 자문합니다."}],
    },
    {
        "role": "user",
        "parts": [{"text": "ROE가 높은데 이게 좋은 건가요? 레버리지 때문은 아닌지 궁금해요."}],
    },
    {
        "role": "model",
        "parts": [{"text": "아주 좋은 질문입니다. ROE가 높다고 무조건 좋은 게 아닙니다. 그래서 DuPont 분석이 중요합니다.\n\nROE = 순이익률 × 자산회전율 × 재무레버리지\n\n같은 ROE 20%라도:\n- A기업: 순이익률 15% × 회전율 1.0 × 레버리지 1.3 = 건강한 ROE\n- B기업: 순이익률 5% × 회전율 1.0 × 레버리지 4.0 = 빚으로 만든 ROE\n\n마치 같은 키의 두 사람이 있는데, 한 명은 자기 키로 높은 곳에 닿고, 다른 한 명은 불안정한 사다리를 타고 올라간 격입니다. B기업은 사다리(부채)가 흔들리면 바로 추락합니다.\n\nDuPont 분석 도구를 통해 이 기업의 ROE가 어디서 오는지 바로 확인해드릴 수 있습니다."}],
    },
    {
        "role": "user",
        "parts": [{"text": "적정 주가가 얼마인지 알려주세요."}],
    },
    {
        "role": "model",
        "parts": [{"text": "적정 주가를 한 가지 숫자로 말하는 것은 위험합니다. 대신 오너이익 기반 DCF로 시나리오별 범위를 계산해보겠습니다.\n\n내재가치 계산 도구를 활용하여 세 가지 시나리오를 돌려보겠습니다:\n- **보수적**: 할인율 12%, 영구성장률 2%\n- **중립적**: 할인율 10%, 영구성장률 2.5%  \n- **낙관적**: 할인율 8%, 영구성장률 3%\n\n이렇게 나온 적정가치에서 30~50% 안전마진을 적용한 가격이 버핏이라면 매수를 고려할 구간입니다. 계산을 진행해보겠습니다."}],
    },
    {
        "role": "user",
        "parts": [{"text": "단기 트레이딩으로 수익 내는 방법이 뭔가요?"}],
    },
    {
        "role": "model",
        "parts": [{"text": "저는 그 게임을 하지 않습니다. 단기 시세 예측은 저의 능력 범위(Circle of Competence) 밖입니다.\n\n찰리 멍거가 늘 말하듯, 역발상으로 생각해보세요. \"어떻게 하면 단기 트레이딩으로 망할 수 있을까?\"를 먼저 물어보십시오. 답은 분명합니다 — 잦은 거래는 세금과 수수료를 쌓이게 하고, 감정적 판단을 유도하며, 복리의 마법을 방해합니다.\n\n훌륭한 기업을 적정 가격에 사서 오래 보유하는 것, 그것이 제가 60년간 해온 전부입니다."}],
    },
]


# ── 데이터 컨텍스트 구축 ──────────────────────────────────────────────────

def _build_data_context(
    company_name: str,
    business_sections: list[dict],
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
    recent_filings: list[dict],
) -> str:
    """회사 공시 데이터를 구조화된 문자열로 변환합니다.

    기존 대비 추가:
    - 5개년 CAGR 요약
    - 오너이익 추세
    - DuPont 분해
    - YoY 주요 변화 하이라이트
    """
    sorted_fin = sorted(financials, key=lambda x: x['year'])[-5:]

    # ── 핵심 지표 요약 (데이터 상단에 배치) ──
    summary_lines = [f"[기업 데이터: {company_name}]", ""]

    if len(sorted_fin) >= 2:
        first, last = sorted_fin[0], sorted_fin[-1]
        years = last['year'] - first['year']
        if years > 0:
            summary_lines.append("=== 핵심 지표 요약 ===")
            for key, label in [('revenue', '매출'), ('net_income', '순이익'), ('operating_income', '영업이익')]:
                start_v = first.get(key)
                end_v = last.get(key)
                if start_v is not None and end_v is not None and start_v > 0 and end_v >= 0:
                    cagr = ((end_v / start_v) ** (1 / years) - 1) * 100
                    summary_lines.append(
                        f"  {label}: {fmt_krw(start_v)} → {fmt_krw(end_v)} "
                        f"(CAGR {cagr:+.1f}%, {years}년)"
                    )

            # 최근 ROE
            latest_roe = last.get('roe')
            if latest_roe is not None:
                summary_lines.append(f"  최근 ROE: {latest_roe:.1f}%")

            summary_lines.append("")

    # ── YoY 하이라이트 ──
    yoy_highlights = compute_yoy_highlights(financials)
    if yoy_highlights:
        summary_lines.append("=== 전년 대비 주요 변화 ===")
        for h in yoy_highlights:
            summary_lines.append(f"  ⚡ {h}")
        summary_lines.append("")

    # ── 사업 개요 ──
    biz_text = ""
    for sec in business_sections[:5]:
        blocks = sec.get("blocks", [])
        text_parts = [b["content"] for b in blocks if b.get("type") == "text" and b.get("content")]
        combined = " ".join(text_parts)[:1000]
        biz_text += f"\n[{sec['number']}. {sec['title']}]\n{combined}\n"

    # ── 재무 지표 ──
    fin_rows = ""
    for f in sorted_fin:
        fin_rows += (
            f"  {f['year']}년: 매출 {fmt_krw(f.get('revenue'))}, "
            f"영업이익 {fmt_krw(f.get('operating_income'))}, "
            f"당기순이익 {fmt_krw(f.get('net_income'))}, "
            f"ROE {f.get('roe') if f.get('roe') is not None else 'N/A'}%, "
            f"부채비율 {f.get('debt_ratio') if f.get('debt_ratio') is not None else 'N/A'}%, "
            f"순부채비율 {f.get('net_debt_ratio') if f.get('net_debt_ratio') is not None else 'N/A'}%"
        )
        if f.get('operating_margin') is not None:
            fin_rows += f", 영업이익률 {f['operating_margin']:.1f}%"
        if f.get('current_ratio') is not None:
            fin_rows += f", 유동비율 {f['current_ratio']:.1f}%"
        if f.get('fcf') is not None:
            fin_rows += f", FCF {fmt_krw(f['fcf'])}"
        fin_rows += "\n"

    # ── 오너이익 추세 ──
    owner_earnings = compute_owner_earnings(financials)
    oe_rows = ""
    for oe in owner_earnings[-5:]:
        if oe['owner_earnings'] is not None:
            ratio_text = f", FCF/NI={oe['fcf_ni_ratio']}" if oe['fcf_ni_ratio'] else ""
            oe_rows += (
                f"  {oe['year']}년: 오너이익 {fmt_krw(oe['owner_earnings'])} "
                f"({oe['method']}){ratio_text}\n"
            )

    # ── DuPont 분해 ──
    dupont_data = compute_dupont(financials)
    dupont_rows = ""
    for dp in dupont_data[-3:]:
        if all(dp[k] is not None for k in ('net_margin_pct', 'asset_turnover', 'leverage')):
            dupont_rows += (
                f"  {dp['year']}년: 순이익률 {dp['net_margin_pct']:.1f}% × "
                f"자산회전율 {dp['asset_turnover']:.2f} × "
                f"레버리지 {dp['leverage']:.2f} "
                f"→ ROE {dp['roe'] or 'N/A'}%\n"
            )

    # ── 배당 ──
    div_rows = ""
    for d in dividends[-5:]:
        div_rows += f"  {d.get('year')}년: 주당 {d.get('dividend', 0):,}원\n"

    # ── 밸류에이션 ──
    val_text = "N/A"
    if valuation:
        val_text = (
            f"현재가 {fmt_krw(valuation.get('price'))}, "
            f"시가총액 {fmt_krw(valuation.get('market_cap'))}, "
            f"PER {valuation.get('per') if valuation.get('per') is not None else 'N/A'}x, "
            f"PBR {valuation.get('pbr') if valuation.get('pbr') is not None else 'N/A'}x, "
            f"PSR {valuation.get('psr') if valuation.get('psr') is not None else 'N/A'}x"
        )
        if valuation.get('ev_ebit'):
            val_text += f", EV/EBIT {valuation['ev_ebit']}x"

    # ── 최근 공시 ──
    filing_text = ""
    for f in recent_filings[:10]:
        filing_text += f"  - {f.get('rcept_dt', '')} {f.get('report_nm', '')}\n"

    # ── 정량 스코어링 결과 ──
    score_data = compute_investment_score(financials, dividends, valuation)
    score_text = score_data['summary_text']

    # ── 조합 ──
    sections = [
        "\n".join(summary_lines),
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

    return "\n\n".join(sections)


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
    data_context = _build_data_context(
        company_name, business_sections, financials, dividends, valuation, recent_filings,
    )

    if buffett_mode:
        return f"""{AI_EVIDENCE_RULES}
{BUFFETT_SYSTEM_PROMPT}

{data_context}
"""

    return f"""{AI_EVIDENCE_RULES}
당신은 "{company_name}"의 DART 공시 데이터를 기반으로 투자 상담을 제공하는 최고 수준의 전문 애널리스트입니다.

## 절대 규칙
1. 아래 [기업 데이터]만을 근거로 답변하세요.
2. 데이터에 없는 내용은 "공시된 데이터에 해당 정보가 없습니다"라고 답하세요.
3. 투자 결정은 항상 투자자 본인의 판단임을 강조하세요.
4. 사용자의 질문에 직접적으로 답하세요. 질문 범위를 벗어나지 마세요.
5. 추가 데이터가 필요하면 제공된 도구(함수)를 적극 활용하세요.

## 도구 활용 가이드
- 분기별 실적 → get_quarterly_financials 호출
- 내재가치/적정주가 → calculate_intrinsic_value 호출
- 특정 공시 확인 → search_filings 호출
- ROE 원천 분석 → get_dupont_analysis 호출

## 분석 프레임워크
1. DuPont 분석: ROE의 질적 원천 파악
2. 오너이익 분석: 실질 현금 창출력 평가
3. 안전마진 정량화: 내재가치 vs 현재 주가
4. 추세 분석: 5개년 CAGR, YoY 변화, 방향성

{data_context}
"""


# ── Function Calling 도구 실행기 팩토리 ─────────────────────────────────────

def create_tool_executor(
    corp_code: str,
    company_name: str,
    financials: list[dict],
    valuation: dict | None,
):
    """chat 엔드포인트에서 사용할 tool_executor 클로저를 생성합니다."""
    async def execute(name: str, args: dict) -> dict:
        if name == "get_quarterly_financials":
            year = args.get("year", str(datetime.now().year - 1))
            quarter = args.get("quarter", "Q4")
            try:
                result = await asyncio.to_thread(
                    fetch_dart_financials_q, corp_code, year, quarter,
                )
                if result:
                    return {
                        "company": company_name,
                        "year": year,
                        "quarter": quarter,
                        "revenue": fmt_krw(result.get('revenue')),
                        "operating_income": fmt_krw(result.get('operating_income')),
                        "net_income": fmt_krw(result.get('net_income')),
                        "roe": result.get('roe'),
                        "debt_ratio": result.get('debt_ratio'),
                        "operating_margin": result.get('operating_margin'),
                        "fcf": fmt_krw(result.get('fcf')),
                    }
                return {"error": f"{year}년 {quarter} 데이터를 찾을 수 없습니다."}
            except Exception as e:
                return {"error": f"분기 데이터 조회 실패: {type(e).__name__}"}

        elif name == "calculate_intrinsic_value":
            discount_rate = args.get("discount_rate", 0.10)
            growth_rate = args.get("growth_rate", 0.02)

            # 최근 오너이익 기반 DCF
            oe_data = compute_owner_earnings(financials)
            recent_oe = [oe for oe in oe_data if oe['owner_earnings'] is not None]

            if not recent_oe:
                return {"error": "오너이익 계산에 필요한 데이터가 부족합니다."}

            latest_oe = recent_oe[-1]['owner_earnings']

            # 3년 평균 오너이익 (안정화)
            avg_oe = sum(oe['owner_earnings'] for oe in recent_oe[-3:]) / min(len(recent_oe), 3)

            # Gordon Growth Model: V = OE × (1+g) / (r-g)
            if discount_rate <= growth_rate:
                return {"error": "할인율은 성장률보다 커야 합니다."}

            intrinsic_value_latest = latest_oe * (1 + growth_rate) / (discount_rate - growth_rate)
            intrinsic_value_avg = avg_oe * (1 + growth_rate) / (discount_rate - growth_rate)

            # 주당 가치
            shares = valuation.get('shares') if valuation else None
            per_share_latest = None
            per_share_avg = None
            current_price = valuation.get('price') if valuation else None
            margin_of_safety = None

            if shares and shares > 0:
                per_share_latest = int(intrinsic_value_latest / shares)
                per_share_avg = int(intrinsic_value_avg / shares)
                if current_price and per_share_avg > 0:
                    margin_of_safety = round((1 - current_price / per_share_avg) * 100, 1)

            return {
                "method": "오너이익 기반 DCF (Gordon Growth Model)",
                "discount_rate": f"{discount_rate:.1%}",
                "growth_rate": f"{growth_rate:.1%}",
                "latest_owner_earnings": fmt_krw(latest_oe),
                "avg_3yr_owner_earnings": fmt_krw(int(avg_oe)),
                "intrinsic_value_total_latest": fmt_krw(int(intrinsic_value_latest)),
                "intrinsic_value_total_avg": fmt_krw(int(intrinsic_value_avg)),
                "per_share_latest": f"{per_share_latest:,}원" if per_share_latest else "N/A",
                "per_share_avg_3yr": f"{per_share_avg:,}원" if per_share_avg else "N/A",
                "current_price": f"{current_price:,.0f}원" if current_price else "N/A",
                "margin_of_safety": f"{margin_of_safety}%" if margin_of_safety is not None else "N/A",
                "buffett_buy_price_30pct": f"{int(per_share_avg * 0.7):,}원" if per_share_avg else "N/A",
                "buffett_buy_price_50pct": f"{int(per_share_avg * 0.5):,}원" if per_share_avg else "N/A",
                "note": "보수적/중립/낙관 시나리오를 비교하려면 할인율과 성장률을 달리하여 여러 번 호출하세요.",
            }

        elif name == "search_filings":
            keyword = args.get("keyword", "")
            try:
                current_year = datetime.now().year
                bgn_de = f"{current_year - 2}0101"
                all_filings = await asyncio.to_thread(
                    fetch_filing_list, corp_code, bgn_de,
                )
                if not all_filings:
                    return {"results": [], "message": f"'{keyword}' 관련 공시를 찾을 수 없습니다."}

                matched = [
                    {"date": f.get('rcept_dt', ''), "title": f.get('report_nm', '')}
                    for f in all_filings
                    if keyword in f.get('report_nm', '')
                ]
                return {
                    "keyword": keyword,
                    "total_found": len(matched),
                    "results": matched[:15],
                }
            except Exception as e:
                return {"error": f"공시 검색 실패: {type(e).__name__}"}

        elif name == "get_dupont_analysis":
            year_arg = args.get("year", "all")
            dupont_all = compute_dupont(financials)

            if year_arg == "all":
                results = dupont_all
            else:
                results = [d for d in dupont_all if str(d['year']) == str(year_arg)]
                if not results:
                    return {"error": f"{year_arg}년 DuPont 분석 데이터가 없습니다."}

            formatted = []
            for dp in results:
                entry = {
                    "year": dp['year'],
                    "roe": f"{dp['roe']:.1f}%" if dp['roe'] else "N/A",
                }
                if all(dp[k] is not None for k in ('net_margin_pct', 'asset_turnover', 'leverage')):
                    entry.update({
                        "net_margin": f"{dp['net_margin_pct']:.1f}%",
                        "asset_turnover": f"{dp['asset_turnover']:.2f}x",
                        "leverage": f"{dp['leverage']:.2f}x",
                        "interpretation": _interpret_dupont(dp),
                    })
                formatted.append(entry)

            return {"dupont_analysis": formatted}

        return {"error": f"알 수 없는 도구: {name}"}

    results: dict[str, dict] = {}

    async def tool_executor(name: str, args: dict) -> dict:
        """한 응답 생성 중 중복 도구 요청의 조회·계산을 재사용합니다."""
        key = json.dumps([name, args], sort_keys=True)
        if key not in results:
            result = await execute(name, args)
            if 'error' not in result:
                results[key] = result
            return result
        return results[key]

    return tool_executor


def _interpret_dupont(dp: dict) -> str:
    """DuPont 분석 결과를 해석합니다."""
    parts = []
    if dp['leverage'] and dp['leverage'] > 3.0:
        parts.append("높은 레버리지에 의존한 ROE — 주의 필요")
    elif dp['leverage'] and dp['leverage'] < 1.5:
        parts.append("낮은 레버리지 — 재무 안정적")

    if dp['net_margin_pct'] and dp['net_margin_pct'] > 10:
        parts.append("양호한 수익성")
    elif dp['net_margin_pct'] and dp['net_margin_pct'] < 3:
        parts.append("낮은 수익성")

    if dp['asset_turnover'] and dp['asset_turnover'] > 1.0:
        parts.append("효율적 자산 활용")
    elif dp['asset_turnover'] and dp['asset_turnover'] < 0.5:
        parts.append("자산 활용도 낮음 (자본집약적)")

    return " / ".join(parts) if parts else "특이사항 없음"


async def chat_with_gemini(
    system_context: str,
    history: list[dict],
    user_message: str,
    company_name: str = "",
    buffett_mode: bool = False,
    tool_executor=None,
) -> str:
    """Gemini 멀티턴 대화를 수행합니다.

    tool_executor가 제공되면 Function Calling 모드로 동작합니다.
    history 형식: [{"role": "user"|"model", "text": "..."}]
    """
    contents = []

    if buffett_mode:
        contents.extend(BUFFETT_FEW_SHOT_EXAMPLES)
    else:
        contents.append({
            "role": "user",
            "parts": [{"text": f"{company_name}에 대해 투자 상담을 시작합니다."}],
        })
        contents.append({
            "role": "model",
            "parts": [{"text": f"네, {company_name}의 DART 공시 데이터를 바탕으로 질문에 답변드리겠습니다. 무엇이 궁금하신가요?"}],
        })

    # 이전 대화 이력 (최근 15턴)
    recent_history = history[-30:]
    for msg in recent_history:
        contents.append({
            "role": msg["role"],
            "parts": [{"text": msg["text"]}],
        })

    # 현재 질문 (긴 대화에서 문맥 이탈 방지를 위해 리마인더 추가)
    if len(history) >= 6:
        reminder = f"\n\n[리마인더: {company_name}의 공시 데이터를 근거로 답변하세요. 데이터에 없는 내용은 추측하지 마세요. 필요하면 도구를 호출하세요.]"
    else:
        reminder = ""
    contents.append({
        "role": "user",
        "parts": [{"text": user_message + reminder}],
    })

    # Function Calling 모드
    if tool_executor is not None:
        return await call_gemini_with_tools(
            system_instruction=system_context,
            contents=contents,
            tools=CHAT_TOOLS,
            tool_executor=tool_executor,
            generation_config=GEMINI_CHAT_CONFIG,
            timeout=120,
        )

    # 기존 호출 (도구 없는 폴백)
    from utils import call_gemini
    return await call_gemini(
        prompt="",
        system_instruction=system_context,
        contents=contents,
        generation_config=GEMINI_CHAT_CONFIG,
        timeout=90,
    )
