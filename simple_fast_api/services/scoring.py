"""투자 스코어링 및 정량 분석 엔진.

AI에 원본 데이터만 전달하는 대신, 사전에 계산된 인사이트를 함께 제공하여
AI 자문의 정확도를 높입니다.
"""
from __future__ import annotations
from config import SCORE_WEIGHTS as WEIGHTS


# ── 성장률 계산 ──────────────────────────────────────────────────────────────

def _cagr(start: int | float | None, end: int | float | None, years: int) -> float | None:
    """연평균 복합 성장률(CAGR)을 계산합니다."""
    if start is None or end is None or years <= 0 or start <= 0 or end < 0:
        return None
    try:
        return (end / start) ** (1 / years) - 1
    except (ZeroDivisionError, ValueError):
        return None


def _yoy_growth(prev: int | float | None, curr: int | float | None) -> float | None:
    """전년 대비 성장률을 계산합니다."""
    if prev is None or curr is None or prev == 0:
        return None
    return (curr - prev) / abs(prev)


def _trend_direction(values: list[float | None]) -> str:
    """숫자 리스트의 추세 방향을 판단합니다."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "데이터 부족"
    increases = sum(1 for i in range(1, len(clean)) if clean[i] > clean[i - 1])
    decreases = sum(1 for i in range(1, len(clean)) if clean[i] < clean[i - 1])
    total = len(clean) - 1
    if increases == total:
        return "지속 상승"
    if decreases == total:
        return "지속 하락"
    if increases >= total * 0.7:
        return "상승 추세"
    if decreases >= total * 0.7:
        return "하락 추세"
    return "혼조세"


def _consistency_score(values: list[float | None], threshold: float) -> float:
    """threshold 이상인 비율을 0~100 점수로 반환합니다."""
    clean = [v for v in values if v is not None]
    if not clean:
        return 0
    above = sum(1 for v in clean if v >= threshold)
    return round(above / len(clean) * 100, 1)


# ── 개별 영역 스코어링 ──────────────────────────────────────────────────────

def _score_growth(financials: list[dict]) -> dict:
    """성장성 점수 (0~100) 및 상세 지표를 계산합니다."""
    if len(financials) < 2:
        return {'score': 0, 'grade': 'N/A', 'details': {}, 'signals': ['데이터 부족']}

    sorted_fin = sorted(financials, key=lambda x: x['year'])
    revenues = [f.get('revenue') for f in sorted_fin]
    net_incomes = [f.get('net_income') for f in sorted_fin]
    op_incomes = [f.get('operating_income') for f in sorted_fin]

    years = sorted_fin[-1]['year'] - sorted_fin[0]['year']
    rev_cagr = _cagr(revenues[0], revenues[-1], years) if revenues[0] is not None and revenues[-1] is not None else None
    ni_cagr = _cagr(net_incomes[0], net_incomes[-1], years) if net_incomes[0] is not None and net_incomes[-1] is not None else None

    # YoY 성장률
    rev_yoy = [(_yoy_growth(revenues[i], revenues[i + 1]) if sorted_fin[i + 1]['year'] == sorted_fin[i]['year'] + 1 else None) for i in range(len(revenues) - 1)]
    ni_yoy = [(_yoy_growth(net_incomes[i], net_incomes[i + 1]) if sorted_fin[i + 1]['year'] == sorted_fin[i]['year'] + 1 else None) for i in range(len(net_incomes) - 1)]

    rev_trend = _trend_direction(revenues)
    ni_trend = _trend_direction(net_incomes)

    # 점수 계산
    score = 50  # 기본
    if rev_cagr is not None:
        if rev_cagr > 0.15:
            score += 20
        elif rev_cagr > 0.08:
            score += 12
        elif rev_cagr > 0.03:
            score += 5
        elif rev_cagr < -0.05:
            score -= 15
    if ni_cagr is not None:
        if ni_cagr > 0.15:
            score += 15
        elif ni_cagr > 0.05:
            score += 8
        elif ni_cagr < -0.1:
            score -= 15
    if rev_trend == "지속 상승":
        score += 10
    elif rev_trend == "지속 하락":
        score -= 10

    score = max(0, min(100, score))

    # 시그널 감지
    signals = []
    if rev_cagr is not None and rev_cagr > 0.15:
        signals.append(f"매출 고성장 (CAGR {rev_cagr:.1%})")
    if rev_cagr is not None and rev_cagr < -0.03:
        signals.append(f"매출 역성장 (CAGR {rev_cagr:.1%})")
    if ni_cagr is not None and rev_cagr is not None and ni_cagr > rev_cagr + 0.05:
        signals.append("이익 성장이 매출 성장을 상회 (수익성 개선)")
    if ni_cagr is not None and rev_cagr is not None and ni_cagr < rev_cagr - 0.1:
        signals.append("이익 성장이 매출 성장에 미달 (수익성 악화)")
    latest_rev_yoy = rev_yoy[-1] if rev_yoy and rev_yoy[-1] is not None else None
    if latest_rev_yoy is not None and latest_rev_yoy < -0.1:
        signals.append(f"최근 1년 매출 급감 ({latest_rev_yoy:.1%})")
    if latest_rev_yoy is not None and latest_rev_yoy > 0.2:
        signals.append(f"최근 1년 매출 급증 ({latest_rev_yoy:.1%})")

    return {
        'score': score,
        'grade': _score_to_grade(score),
        'details': {
            'revenue_cagr': _pct(rev_cagr),
            'net_income_cagr': _pct(ni_cagr),
            'revenue_trend': rev_trend,
            'net_income_trend': ni_trend,
            'revenue_yoy': [_pct(y) for y in rev_yoy],
            'net_income_yoy': [_pct(y) for y in ni_yoy],
        },
        'signals': signals or ['특이 사항 없음'],
    }


def _score_profitability(financials: list[dict]) -> dict:
    """수익성 점수 (0~100) 및 상세 지표를 계산합니다."""
    if not financials:
        return {'score': 0, 'grade': 'N/A', 'details': {}, 'signals': ['데이터 부족']}

    sorted_fin = sorted(financials, key=lambda x: x['year'])
    roes = [f.get('roe') for f in sorted_fin]
    margins = [f.get('operating_margin') for f in sorted_fin]
    fcfs = [f.get('fcf') for f in sorted_fin]
    net_incomes = [f.get('net_income') for f in sorted_fin]

    latest = sorted_fin[-1]
    latest_roe = latest.get('roe')
    latest_margin = latest.get('operating_margin')

    # 점수 계산
    score = 50
    if latest_roe is not None:
        if latest_roe >= 20:
            score += 20
        elif latest_roe >= 15:
            score += 15
        elif latest_roe >= 10:
            score += 8
        elif latest_roe < 5:
            score -= 10

    roe_consistency = _consistency_score(roes, 15)
    if roe_consistency >= 80:
        score += 10
    elif roe_consistency >= 60:
        score += 5

    if latest_margin is not None:
        if latest_margin >= 20:
            score += 10
        elif latest_margin >= 10:
            score += 5
        elif latest_margin < 3:
            score -= 10

    # FCF vs 순이익 비교 (이익의 질)
    fcf_quality_ratios = []
    for f_val, ni_val in zip(fcfs, net_incomes):
        if f_val is not None and ni_val is not None and ni_val > 0:
            fcf_quality_ratios.append(f_val / ni_val)

    avg_fcf_quality = sum(fcf_quality_ratios) / len(fcf_quality_ratios) if fcf_quality_ratios else None
    if avg_fcf_quality is not None and avg_fcf_quality > 1.0:
        score += 5

    score = max(0, min(100, score))

    # 시그널 감지
    signals = []
    if roe_consistency >= 80:
        signals.append(f"ROE 15% 이상 안정적 유지 ({roe_consistency:.0f}% 달성률)")
    roe_trend = _trend_direction(roes)
    if roe_trend == "지속 하락":
        signals.append("ROE 지속 하락 추세")
    if latest_margin is not None and latest_margin >= 20:
        signals.append(f"높은 영업이익률 ({latest_margin:.1f}%)")
    if avg_fcf_quality is not None and avg_fcf_quality > 1.2:
        signals.append("FCF가 순이익을 상회 (이익의 질 우수)")
    if avg_fcf_quality is not None and avg_fcf_quality < 0.5:
        signals.append("FCF가 순이익 대비 낮음 (이익의 질 주의)")

    return {
        'score': score,
        'grade': _score_to_grade(score),
        'details': {
            'latest_roe': latest_roe,
            'latest_margin': latest_margin,
            'roe_consistency_15pct': roe_consistency,
            'roe_trend': roe_trend,
            'margin_trend': _trend_direction(margins),
            'avg_fcf_quality': round(avg_fcf_quality, 2) if avg_fcf_quality else None,
        },
        'signals': signals or ['특이 사항 없음'],
    }


def _score_financial_health(financials: list[dict]) -> dict:
    """재무 건전성 점수 (0~100)을 계산합니다."""
    if not financials:
        return {'score': 0, 'grade': 'N/A', 'details': {}, 'signals': ['데이터 부족']}

    sorted_fin = sorted(financials, key=lambda x: x['year'])
    latest = sorted_fin[-1]

    debt_ratio = latest.get('debt_ratio')
    net_debt_ratio = latest.get('net_debt_ratio')
    current_ratio = latest.get('current_ratio')
    fcf = latest.get('fcf')
    liabilities = latest.get('liabilities')
    op_income = latest.get('operating_income')

    score = 50

    # 부채비율
    if debt_ratio is not None:
        if debt_ratio < 50:
            score += 15
        elif debt_ratio < 100:
            score += 8
        elif debt_ratio < 200:
            score += 0
        else:
            score -= 15

    # 순부채비율
    if net_debt_ratio is not None:
        if net_debt_ratio < 0:  # 순현금
            score += 10
        elif net_debt_ratio < 30:
            score += 5
        elif net_debt_ratio > 100:
            score -= 10

    # 유동비율
    if current_ratio is not None:
        if current_ratio >= 200:
            score += 10
        elif current_ratio >= 150:
            score += 5
        elif current_ratio < 100:
            score -= 10

    # 이자 상환 능력 (부채/영업이익)
    debt_payback = None
    if liabilities and op_income and op_income > 0:
        debt_payback = round(liabilities / op_income, 1)
        if debt_payback <= 3:
            score += 5
        elif debt_payback > 8:
            score -= 10

    score = max(0, min(100, score))

    # 시그널
    signals = []
    if net_debt_ratio is not None and net_debt_ratio < 0:
        signals.append("순현금 보유 기업")
    if debt_ratio is not None and debt_ratio > 200:
        signals.append(f"부채비율 높음 ({debt_ratio:.0f}%)")
    if current_ratio is not None and current_ratio < 100:
        signals.append(f"유동비율 100% 미만 ({current_ratio:.0f}%) — 단기 유동성 주의")
    if debt_payback is not None and debt_payback > 8:
        signals.append(f"부채 상환에 영업이익 {debt_payback:.0f}년 소요 추정")
    if fcf is not None and fcf < 0:
        signals.append("FCF 마이너스 — 현금창출력 부족")

    debt_ratios = [f.get('debt_ratio') for f in sorted_fin]
    debt_trend = _trend_direction(debt_ratios)
    if debt_trend in ("지속 상승", "상승 추세"):
        signals.append("부채비율 상승 추세")

    return {
        'score': score,
        'grade': _score_to_grade(score),
        'details': {
            'debt_ratio': debt_ratio,
            'net_debt_ratio': net_debt_ratio,
            'current_ratio': current_ratio,
            'debt_payback_years': debt_payback,
            'debt_ratio_trend': debt_trend,
        },
        'signals': signals or ['특이 사항 없음'],
    }


def _score_dividend(financials: list[dict], dividends: list[dict]) -> dict:
    """배당 매력도 점수 (0~100)을 계산합니다."""
    if not dividends:
        return {'score': 30, 'grade': 'D', 'details': {'note': '배당 이력 없음'}, 'signals': ['무배당 또는 배당 이력 없음']}

    sorted_div = sorted(dividends, key=lambda x: x.get('year', 0))
    amounts = [d.get('dividend', 0) for d in sorted_div]

    years_with_div = sum(1 for a in amounts if a > 0)
    total_years = len(amounts)
    consistency = round(years_with_div / total_years * 100, 1) if total_years else 0

    # 배당 성장률
    div_cagr = _cagr(amounts[0], amounts[-1], sorted_div[-1]['year'] - sorted_div[0]['year']) if len(amounts) >= 2 else None
    div_trend = _trend_direction(amounts)

    score = 40
    if consistency >= 80:
        score += 15
    elif consistency >= 60:
        score += 8

    if div_cagr is not None:
        if div_cagr > 0.1:
            score += 15
        elif div_cagr > 0.03:
            score += 8
        elif div_cagr < -0.05:
            score -= 10

    if div_trend == "지속 상승":
        score += 10

    # 배당성향 계산 (최근 연도)
    payout_ratio = None
    if financials and dividends:
        latest_fin = max(financials, key=lambda x: x['year'])
        latest_div = max(dividends, key=lambda x: x.get('year', 0))
        eps = latest_fin.get('eps')
        dps = latest_div.get('dividend', 0)
        if latest_fin['year'] == latest_div['year'] and eps and eps > 0 and dps >= 0:
            payout_ratio = round(dps / eps * 100, 1)
            if 20 <= payout_ratio <= 60:
                score += 5
            elif payout_ratio > 90:
                score -= 5  # 배당성향 과다

    score = max(0, min(100, score))

    signals = []
    if consistency >= 80:
        signals.append(f"안정적 배당 지급 ({years_with_div}/{total_years}년)")
    if div_trend == "지속 상승":
        signals.append("배당금 지속 증가")
    if div_cagr is not None and div_cagr > 0.1:
        signals.append(f"배당 고성장 (CAGR {div_cagr:.1%})")
    if payout_ratio is not None and payout_ratio > 80:
        signals.append(f"배당성향 높음 ({payout_ratio:.0f}%) — 지속 가능성 확인 필요")

    return {
        'score': score,
        'grade': _score_to_grade(score),
        'details': {
            'consistency': consistency,
            'dividend_cagr': _pct(div_cagr),
            'dividend_trend': div_trend,
            'payout_ratio': payout_ratio,
        },
        'signals': signals or ['특이 사항 없음'],
    }


def _score_valuation(valuation: dict | None, financials: list[dict]) -> dict:
    """밸류에이션 매력도 점수 (0~100)을 계산합니다."""
    if not valuation:
        return {'score': 50, 'grade': 'C', 'details': {}, 'signals': ['밸류에이션 데이터 없음']}

    per = valuation.get('per')
    pbr = valuation.get('pbr')
    psr = valuation.get('psr')
    ev_ebit = valuation.get('ev_ebit')

    score = 50
    signals = []

    # PER 평가
    if per is not None:
        if per < 8:
            score += 15
            signals.append(f"PER {per:.1f}x — 저평가 구간")
        elif per < 12:
            score += 8
        elif per < 20:
            score += 0
        elif per > 30:
            score -= 10
            signals.append(f"PER {per:.1f}x — 고평가 주의")

    # PBR 평가
    if pbr is not None:
        if pbr < 0.8:
            score += 10
            signals.append(f"PBR {pbr:.2f}x — 자산가치 대비 저평가")
        elif pbr < 1.2:
            score += 5
        elif pbr > 3:
            score -= 5

    # EV/EBIT 평가
    if ev_ebit is not None:
        if ev_ebit < 8:
            score += 10
        elif ev_ebit < 15:
            score += 3
        elif ev_ebit > 25:
            score -= 5

    # ROE 대비 PBR 적정성 (Graham/Buffett)
    if financials and pbr is not None:
        latest = max(financials, key=lambda x: x['year'])
        roe = latest.get('roe')
        if roe is not None and roe > 0:
            # 적정 PBR ≈ ROE / 기대수익률(10%)
            fair_pbr = roe / 10
            if pbr < fair_pbr * 0.7:
                signals.append(f"ROE({roe:.1f}%) 대비 PBR({pbr:.1f}x) 저평가 (적정 ~{fair_pbr:.1f}x)")
                score += 5
            elif pbr > fair_pbr * 1.5:
                signals.append(f"ROE({roe:.1f}%) 대비 PBR({pbr:.1f}x) 고평가 (적정 ~{fair_pbr:.1f}x)")
                score -= 5

    score = max(0, min(100, score))

    return {
        'score': score,
        'grade': _score_to_grade(score),
        'details': {
            'per': per,
            'pbr': pbr,
            'psr': psr,
            'ev_ebit': ev_ebit,
        },
        'signals': signals or ['특이 사항 없음'],
    }


# ── 종합 스코어 ─────────────────────────────────────────────────────────────




def _score_to_grade(score: int | float | None) -> str:
    if score is None:
        return 'N/A'
    if score >= 85:
        return 'A+'
    if score >= 75:
        return 'A'
    if score >= 65:
        return 'B+'
    if score >= 55:
        return 'B'
    if score >= 45:
        return 'C+'
    if score >= 35:
        return 'C'
    if score >= 25:
        return 'D'
    return 'F'


def _pct(v: float | None) -> str | None:
    """float를 퍼센트 문자열로 변환합니다."""
    if v is None:
        return None
    return f"{v:.1%}"


def compute_investment_score(
    financials: list[dict],
    dividends: list[dict],
    valuation: dict | None,
) -> dict:
    """종합 투자 스코어를 계산합니다.

    Returns:
        {
            'total_score': float,
            'total_grade': str,
            'categories': {
                'growth': {...},
                'profitability': {...},
                'financial_health': {...},
                'dividend': {...},
                'valuation': {...},
            },
            'key_signals': [str, ...],  # 모든 카테고리의 주요 시그널 통합
            'summary_text': str,        # AI 컨텍스트용 요약 텍스트
        }
    """
    categories = {
        'growth': _score_growth(financials),
        'profitability': _score_profitability(financials),
        'financial_health': _score_financial_health(financials),
        'dividend': _score_dividend(financials, dividends),
        'valuation': _score_valuation(valuation, financials),
    }

    latest = max(financials, key=lambda f: f['year']) if financials else {}
    availability = {
        'growth': len(financials) >= 2 and len({f.get('fs_div') for f in financials}) == 1 and all(f.get('revenue') is not None and f.get('net_income') is not None for f in financials),
        'profitability': latest.get('roe') is not None and latest.get('operating_margin') is not None,
        'financial_health': latest.get('debt_ratio') is not None,
        'dividend': bool(dividends) and max(d['year'] for d in dividends) == latest.get('year'),
        'valuation': bool(valuation) and any(valuation.get(k) is not None for k in ('per', 'pbr', 'psr', 'ev_ebit')),
    }
    for name, available in availability.items():
        categories[name]['available'] = available
        if not available:
            categories[name].update(score=None, grade='N/A', signals=['데이터 부족 — 평가 불가'])
    missing = [name for name, available in availability.items() if not available]
    total = sum(
        (categories[cat]['score'] or 0) * weight
        for cat, weight in WEIGHTS.items()
    )
    total = round(total, 1) if not missing else None

    # 주요 시그널 통합 (특이 사항 없음 제외)
    key_signals = []
    for cat_name, cat_data in categories.items():
        for sig in cat_data.get('signals', []):
            if sig != '특이 사항 없음':
                key_signals.append(sig)

    # AI 컨텍스트용 요약 텍스트 생성
    summary_text = _build_score_summary(total, categories, key_signals)

    return {
        'total_score': total,
        'missing_categories': missing,
        'coverage': round(sum(WEIGHTS[n] for n, ok in availability.items() if ok) * 100),
        'total_grade': _score_to_grade(total),
        'categories': categories,
        'key_signals': key_signals,
        'summary_text': summary_text,
    }


def _build_score_summary(total: float | None, categories: dict, signals: list[str]) -> str:
    """AI 프롬프트에 삽입할 정량 분석 요약 텍스트를 생성합니다."""
    lines = [
        "=== 정량 투자 스코어 (자동 계산) ===",
        f"종합 점수: {total:.0f}/100 ({_score_to_grade(total)})" if total is not None else "종합 점수: 평가 불가 (일부 영역 데이터 부족)",
        "",
    ]

    cat_labels = {
        'growth': '성장성',
        'profitability': '수익성',
        'financial_health': '재무건전성',
        'dividend': '배당매력도',
        'valuation': '밸류에이션',
    }

    for cat_key, label in cat_labels.items():
        cat = categories[cat_key]
        lines.append(f"  {label}: {cat['score']:.0f}점 ({cat['grade']})" if cat['score'] is not None else f"  {label}: 평가 불가")

        # 주요 세부 지표 포함
        details = cat.get('details', {})
        detail_parts = []
        for k, v in details.items():
            if v is not None and k not in ('note',):
                detail_parts.append(f"{k}={v}")
        if detail_parts:
            lines.append(f"    [{', '.join(detail_parts[:5])}]")

    if signals:
        lines.append("")
        lines.append("=== 자동 감지 시그널 ===")
        for sig in signals:
            lines.append(f"  ! {sig}")

    return "\n".join(lines)


# ── 오너이익 (Owner Earnings) 계산 ─────────────────────────────────────────

def compute_owner_earnings(financials: list[dict]) -> list[dict]:
    """FCF를 오너이익 근사치로 제공하며 누락된 현금흐름은 추정하지 않습니다.

    유지보수 CapEx를 분리한 정밀 오너이익이 아니므로 근사치임을 표시합니다.
    """
    sorted_fin = sorted(financials, key=lambda x: x['year'])
    results = []

    for f in sorted_fin:
        ni = f.get('net_income')
        fcf = f.get('fcf')
        revenue = f.get('revenue')

        owner_earnings = None
        method = None

        if fcf is not None:
            # FCF가 존재하면 오너이익 근사치로 활용
            # 오너이익 = FCF (이미 감가상각 + Capex가 반영된 값)
            owner_earnings = fcf
            method = "FCF 기반"
        elif ni is not None:
            # 현금흐름이 없으면 순이익으로 대체하지 않습니다.
            owner_earnings = None
            method = "현금흐름 데이터 부족 — 추정하지 않음"

        # 오너이익 수익률 (owner earnings yield)
        oe_yield = None
        if owner_earnings and revenue and revenue > 0:
            oe_yield = round(owner_earnings / revenue * 100, 1)

        results.append({
            'year': f['year'],
            'owner_earnings': owner_earnings,
            'method': method,
            'oe_margin': oe_yield,
            'fcf_ni_ratio': round(fcf / ni, 2) if fcf is not None and ni is not None and ni != 0 else None,
        })

    return results


def compute_dupont(financials: list[dict]) -> list[dict]:
    """DuPont 분해 분석을 수행합니다.

    ROE = 순이익률 × 자산회전율 × 재무레버리지
        = (순이익/매출) × (매출/총자산) × (총자산/자기자본)
    """
    sorted_fin = sorted(financials, key=lambda x: x['year'])
    results = []

    for f in sorted_fin:
        ni = f.get('net_income')
        revenue = f.get('revenue')
        assets = f.get('total_assets')
        equity = f.get('equity')
        roe = f.get('roe')

        net_margin = round(ni / revenue * 100, 2) if ni and revenue and revenue != 0 else None
        asset_turnover = round(revenue / assets, 2) if revenue and assets and assets != 0 else None
        leverage = round(assets / equity, 2) if assets and equity and equity != 0 else None

        # 검증: 세 요소의 곱이 ROE와 유사한지
        computed_roe = None
        if net_margin is not None and asset_turnover is not None and leverage is not None:
            computed_roe = round(net_margin * asset_turnover * leverage, 1)

        results.append({
            'year': f['year'],
            'roe': roe,
            'net_margin_pct': net_margin,
            'asset_turnover': asset_turnover,
            'leverage': leverage,
            'computed_roe': computed_roe,
        })

    return results


def compute_yoy_highlights(financials: list[dict]) -> list[str]:
    """전년 대비 주요 변화를 감지하여 하이라이트 목록을 반환합니다."""
    sorted_fin = sorted(financials, key=lambda x: x['year'])
    if len(sorted_fin) < 2:
        return []

    highlights = []
    prev = sorted_fin[-2]
    curr = sorted_fin[-1]
    year = curr['year']
    if year != prev['year'] + 1:
        return []

    metrics = [
        ('revenue', '매출'),
        ('operating_income', '영업이익'),
        ('net_income', '당기순이익'),
        ('fcf', 'FCF'),
    ]

    for key, label in metrics:
        p, c = prev.get(key), curr.get(key)
        if p and c and p != 0:
            change = (c - p) / abs(p) * 100
            if abs(change) >= 15:
                direction = "증가" if change > 0 else "감소"
                highlights.append(f"{year}년 {label} 전년 대비 {change:+.1f}% {direction}")

    # ROE 변화
    prev_roe, curr_roe = prev.get('roe'), curr.get('roe')
    if prev_roe is not None and curr_roe is not None:
        roe_diff = curr_roe - prev_roe
        if abs(roe_diff) >= 3:
            direction = "상승" if roe_diff > 0 else "하락"
            highlights.append(f"{year}년 ROE {prev_roe:.1f}% → {curr_roe:.1f}% ({roe_diff:+.1f}%p {direction})")

    # 부채비율 변화
    prev_dr, curr_dr = prev.get('debt_ratio'), curr.get('debt_ratio')
    if prev_dr is not None and curr_dr is not None:
        dr_diff = curr_dr - prev_dr
        if abs(dr_diff) >= 10:
            direction = "증가" if dr_diff > 0 else "감소"
            highlights.append(f"{year}년 부채비율 {prev_dr:.0f}% → {curr_dr:.0f}% ({direction})")

    return highlights


async def cached_investment_score(company: str, data: dict) -> tuple[dict, bool]:
    """동일 재무·배당·시세 입력의 정량 결과를 AI 없이 재사용합니다."""
    from cache import score_cache
    from services.company_data import input_fingerprint
    inputs = {key: data[key] for key in ('financials', 'dividends', 'valuation')}
    fingerprint = input_fingerprint(inputs)
    async with score_cache.lock(company):
        cached = await score_cache.get(company)
        if cached and cached.get('input_fingerprint') == fingerprint:
            return cached['score'], True
        result = compute_investment_score(**inputs)
        await score_cache.set(company, {'input_fingerprint': fingerprint, 'score': result})
        return result, False
