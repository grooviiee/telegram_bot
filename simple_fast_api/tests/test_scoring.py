"""scoring.py 유닛 테스트.

모든 대상 함수는 외부 I/O가 없는 순수 함수이므로 mock 없이 직접 검증합니다.
"""
import pytest
from services.scoring import (
    _cagr,
    _yoy_growth,
    _trend_direction,
    _consistency_score,
    _score_to_grade,
    _pct,
    _score_growth,
    _score_profitability,
    _score_financial_health,
    _score_dividend,
    _score_valuation,
    compute_investment_score,
    compute_owner_earnings,
    compute_dupont,
    compute_yoy_highlights,
    WEIGHTS,
)


# ─── 유틸리티 함수 ────────────────────────────────────────────────────────────

class TestCagr:
    def test_exact_10pct(self):
        # 100 → 121 over 2 years = exactly 10%
        assert abs(_cagr(100, 121, 2) - 0.10) < 1e-9

    def test_normal_growth(self):
        result = _cagr(100_000, 200_000, 4)
        assert result is not None
        assert abs(result - (2 ** 0.25 - 1)) < 1e-9

    def test_none_start_returns_none(self):
        assert _cagr(None, 200, 5) is None

    def test_none_end_returns_none(self):
        assert _cagr(100, None, 5) is None

    def test_zero_start_returns_none(self):
        assert _cagr(0, 200, 5) is None

    def test_negative_start_returns_none(self):
        assert _cagr(-100, 200, 5) is None

    def test_zero_years_returns_none(self):
        assert _cagr(100, 200, 0) is None

    def test_negative_years_returns_none(self):
        assert _cagr(100, 200, -1) is None

    def test_same_value_returns_zero(self):
        result = _cagr(100, 100, 5)
        assert result is not None
        assert abs(result) < 1e-9

    def test_declining_value_is_negative(self):
        result = _cagr(200_000, 100_000, 4)
        assert result is not None
        assert result < 0

    def test_negative_end_returns_none(self):
        # (-0.5)^0.25 는 복소수 → ValueError → None
        assert _cagr(10_000, -5_000, 4) is None


class TestYoyGrowth:
    def test_positive_growth(self):
        assert abs(_yoy_growth(100, 150) - 0.5) < 1e-9

    def test_negative_growth(self):
        assert abs(_yoy_growth(100, 80) - (-0.2)) < 1e-9

    def test_zero_growth(self):
        assert abs(_yoy_growth(100, 100)) < 1e-9

    def test_zero_prev_returns_none(self):
        assert _yoy_growth(0, 100) is None

    def test_none_prev_returns_none(self):
        assert _yoy_growth(None, 100) is None

    def test_none_curr_returns_none(self):
        assert _yoy_growth(100, None) is None

    def test_negative_prev_uses_abs(self):
        # prev=-100, curr=-50 → (50) / abs(-100) = 0.5
        assert abs(_yoy_growth(-100, -50) - 0.5) < 1e-9


class TestTrendDirection:
    def test_continuous_rise(self):
        assert _trend_direction([1, 2, 3, 4, 5]) == "지속 상승"

    def test_continuous_decline(self):
        assert _trend_direction([5, 4, 3, 2, 1]) == "지속 하락"

    def test_rising_trend(self):
        # 4 pairs, 3 increases (75% ≥ 70%)
        assert _trend_direction([1, 2, 3, 4, 3]) == "상승 추세"

    def test_declining_trend(self):
        # 4 pairs, 3 decreases (75% ≥ 70%)
        assert _trend_direction([5, 4, 3, 2, 3]) == "하락 추세"

    def test_mixed_returns_혼조세(self):
        assert _trend_direction([1, 3, 2, 4]) == "혼조세"

    def test_empty_list(self):
        assert _trend_direction([]) == "데이터 부족"

    def test_single_value(self):
        assert _trend_direction([5]) == "데이터 부족"

    def test_all_none_values(self):
        assert _trend_direction([None, None, None]) == "데이터 부족"

    def test_none_values_filtered_out(self):
        # [1, None, 3] → clean=[1, 3] → 1 increase out of 1 → "지속 상승"
        assert _trend_direction([1, None, 3]) == "지속 상승"


class TestConsistencyScore:
    def test_all_above_threshold(self):
        assert _consistency_score([20, 25, 30], 15) == 100.0

    def test_none_above_threshold(self):
        assert _consistency_score([5, 8, 10], 15) == 0.0

    def test_half_above_threshold(self):
        assert _consistency_score([10, 20, 10, 20], 15) == 50.0

    def test_empty_list_returns_zero(self):
        assert _consistency_score([], 15) == 0.0

    def test_all_none_returns_zero(self):
        assert _consistency_score([None, None], 15) == 0.0

    def test_none_values_ignored(self):
        # [None, 20, None] → clean=[20] → 100%
        assert _consistency_score([None, 20, None], 15) == 100.0

    def test_exact_threshold_value_counts(self):
        # value == threshold → v >= threshold → True
        assert _consistency_score([15, 14], 15) == 50.0


class TestScoreToGrade:
    @pytest.mark.parametrize("score,expected", [
        (100, "A+"), (85, "A+"),
        (84, "A"),   (75, "A"),
        (74, "B+"),  (65, "B+"),
        (64, "B"),   (55, "B"),
        (54, "C+"),  (45, "C+"),
        (44, "C"),   (35, "C"),
        (34, "D"),   (25, "D"),
        (24, "F"),   (0,  "F"),
    ])
    def test_grade_boundaries(self, score, expected):
        assert _score_to_grade(score) == expected


class TestPct:
    def test_none_returns_none(self):
        assert _pct(None) is None

    def test_positive_value(self):
        assert _pct(0.15) == "15.0%"

    def test_negative_value(self):
        assert _pct(-0.05) == "-5.0%"

    def test_zero_value(self):
        assert _pct(0.0) == "0.0%"


# ─── 성장성 스코어 ────────────────────────────────────────────────────────────

class TestScoreGrowth:
    def test_insufficient_data_returns_zero(self):
        result = _score_growth([
            {'year': '2023', 'revenue': 100, 'net_income': 10, 'operating_income': 15},
        ])
        assert result['score'] == 0
        assert result['grade'] == 'N/A'
        assert '데이터 부족' in result['signals']

    def test_high_growth_scores_above_80(self, healthy_financials):
        # rev CAGR ≈ 19%, ni CAGR ≈ 27%, 지속 상승 → 50+20+15+10 = 95
        result = _score_growth(healthy_financials)
        assert result['score'] >= 80
        assert result['grade'] in ('A+', 'A')

    def test_declining_company_scores_below_50(self, declining_financials):
        # rev CAGR ≈ -16% → -15, 지속 하락 → -10
        result = _score_growth(declining_financials)
        assert result['score'] < 50

    def test_score_clamped_between_0_and_100(self, healthy_financials):
        result = _score_growth(healthy_financials)
        assert 0 <= result['score'] <= 100

    def test_output_structure(self, healthy_financials):
        result = _score_growth(healthy_financials)
        assert {'score', 'grade', 'details', 'signals'} <= result.keys()
        assert 'revenue_cagr' in result['details']
        assert 'net_income_cagr' in result['details']
        assert 'revenue_trend' in result['details']

    def test_high_growth_signal_detected(self):
        # rev CAGR > 15% → 매출 고성장 시그널
        financials = [
            {'year': str(2019 + i), 'revenue': int(100 * (1.2 ** i)),
             'net_income': int(50 * (1.2 ** i)), 'operating_income': int(40 * (1.2 ** i))}
            for i in range(5)
        ]
        result = _score_growth(financials)
        assert any("고성장" in s for s in result['signals'])

    def test_revenue_decline_signal_detected(self, declining_financials):
        result = _score_growth(declining_financials)
        assert any("역성장" in s for s in result['signals'])

    def test_unsorted_input_handled(self, healthy_financials):
        shuffled = healthy_financials[::-1]
        result = _score_growth(shuffled)
        assert result['score'] == _score_growth(healthy_financials)['score']


# ─── 수익성 스코어 ────────────────────────────────────────────────────────────

class TestScoreProfitability:
    def test_empty_financials_returns_zero(self):
        result = _score_profitability([])
        assert result['score'] == 0
        assert result['grade'] == 'N/A'

    def test_high_roe_company(self, healthy_financials):
        # latest ROE = 22 ≥ 20 → +20
        result = _score_profitability(healthy_financials)
        assert result['score'] >= 60

    def test_low_roe_penalized(self, declining_financials):
        # latest ROE = -4.0 < 5 → -10
        result = _score_profitability(declining_financials)
        assert result['score'] < 50

    def test_score_clamped_between_0_and_100(self, healthy_financials):
        assert 0 <= _score_profitability(healthy_financials)['score'] <= 100

    def test_high_operating_margin_signal(self):
        financials = [{
            'year': '2023', 'revenue': 100_000, 'operating_income': 25_000,
            'net_income': 18_000, 'roe': 25.0, 'operating_margin': 25.0,
            'fcf': 20_000, 'debt_ratio': 40.0, 'net_debt_ratio': 10.0,
            'current_ratio': 220.0, 'liabilities': 50_000, 'equity': 120_000,
            'total_assets': 170_000,
        }]
        result = _score_profitability(financials)
        assert any("영업이익률" in s for s in result['signals'])

    def test_fcf_exceeds_net_income_bonus(self):
        # FCF > net_income → avg_fcf_quality > 1.0 → +5
        financials = [{
            'year': '2023', 'revenue': 100_000, 'operating_income': 20_000,
            'net_income': 15_000, 'roe': 18.0, 'operating_margin': 20.0,
            'fcf': 18_000, 'debt_ratio': 50.0, 'net_debt_ratio': 5.0,
            'current_ratio': 200.0, 'liabilities': 60_000, 'equity': 130_000,
            'total_assets': 190_000,
        }]
        result = _score_profitability(financials)
        assert result['details']['avg_fcf_quality'] is not None
        assert result['details']['avg_fcf_quality'] > 1.0

    def test_roe_consistency_tracked(self, healthy_financials):
        result = _score_profitability(healthy_financials)
        assert 'roe_consistency_15pct' in result['details']
        assert 0 <= result['details']['roe_consistency_15pct'] <= 100


# ─── 재무 건전성 스코어 ───────────────────────────────────────────────────────

class TestScoreFinancialHealth:
    def test_empty_financials_returns_zero(self):
        result = _score_financial_health([])
        assert result['score'] == 0
        assert result['grade'] == 'N/A'

    def test_healthy_company_high_score(self, healthy_financials):
        # debt=52(+8), net_debt=2(+5), current=235(+10), payback=2.3(+5) → 78
        result = _score_financial_health(healthy_financials)
        assert result['score'] >= 60

    def test_distressed_company_low_score(self, declining_financials):
        # debt=420(-15), net_debt=210(-10), current=55(-10), payback=470(-10) → 5
        result = _score_financial_health(declining_financials)
        assert result['score'] <= 30

    def test_net_cash_signal(self):
        financials = [{
            'year': '2023', 'revenue': 100_000, 'operating_income': 15_000,
            'net_income': 12_000, 'roe': 15.0, 'operating_margin': 15.0,
            'fcf': 10_000, 'debt_ratio': 40.0, 'net_debt_ratio': -10.0,
            'current_ratio': 250.0, 'liabilities': 50_000, 'equity': 125_000,
            'total_assets': 175_000,
        }]
        result = _score_financial_health(financials)
        assert '순현금 보유 기업' in result['signals']

    def test_high_debt_ratio_signal(self, declining_financials):
        result = _score_financial_health(declining_financials)
        assert any("부채비율 높음" in s for s in result['signals'])

    def test_low_current_ratio_signal(self, declining_financials):
        result = _score_financial_health(declining_financials)
        assert any("유동비율" in s for s in result['signals'])

    def test_negative_fcf_signal(self, declining_financials):
        result = _score_financial_health(declining_financials)
        assert any("FCF" in s for s in result['signals'])

    def test_score_clamped_between_0_and_100(self, declining_financials):
        assert 0 <= _score_financial_health(declining_financials)['score'] <= 100


# ─── 배당 매력도 스코어 ───────────────────────────────────────────────────────

class TestScoreDividend:
    def test_no_dividends_returns_base_30(self):
        result = _score_dividend([], [])
        assert result['score'] == 30
        assert result['grade'] == 'D'

    def test_consistent_growing_dividends_high_score(self, healthy_financials, healthy_dividends):
        # consistency=100%(+15), CAGR≈22%(+15), 지속상승(+10) → 80
        result = _score_dividend(healthy_financials, healthy_dividends)
        assert result['score'] >= 65

    def test_inconsistent_dividends_low_score(self):
        dividends = [
            {'year': '2019', 'dividend': 500},
            {'year': '2020', 'dividend': 0},
            {'year': '2021', 'dividend': 0},
            {'year': '2022', 'dividend': 300},
            {'year': '2023', 'dividend': 0},
        ]
        result = _score_dividend([], dividends)
        # consistency=40%(no bonus), CAGR<0(-10), 하락추세(no +10)
        assert result['score'] < 55

    def test_declining_dividends_penalized(self):
        dividends = [
            {'year': str(2019 + i), 'dividend': 1000 - i * 200}
            for i in range(5)
        ]
        result = _score_dividend([], dividends)
        assert result['score'] < 55

    def test_growing_dividends_signal(self, healthy_financials, healthy_dividends):
        result = _score_dividend(healthy_financials, healthy_dividends)
        assert any("배당금 지속 증가" in s or "고성장" in s for s in result['signals'])

    def test_excessive_payout_ratio_penalized(self):
        # EPS=1000, DPS=950 → payout=95% > 90% → -5
        financials = [{
            'year': '2023', 'revenue': 10_000, 'operating_income': 1_500,
            'net_income': 1_000, 'roe': 15.0, 'operating_margin': 15.0,
            'fcf': 800, 'debt_ratio': 60.0, 'net_debt_ratio': 10.0,
            'current_ratio': 180.0, 'liabilities': 8_000, 'equity': 8_000,
            'total_assets': 16_000, 'eps': 1_000,
        }]
        dividends = [{'year': '2023', 'dividend': 950}]
        result = _score_dividend(financials, dividends)
        assert result['details']['payout_ratio'] > 90

    def test_healthy_payout_ratio_bonus(self):
        # EPS=2000, DPS=800 → payout=40% ∈ [20,60] → +5
        financials = [{
            'year': '2023', 'revenue': 10_000, 'operating_income': 2_000,
            'net_income': 2_000, 'roe': 18.0, 'operating_margin': 20.0,
            'fcf': 1_800, 'debt_ratio': 50.0, 'net_debt_ratio': 5.0,
            'current_ratio': 200.0, 'liabilities': 5_000, 'equity': 11_000,
            'total_assets': 16_000, 'eps': 2_000,
        }]
        dividends = [{'year': '2023', 'dividend': 800}]
        result = _score_dividend(financials, dividends)
        assert result['details']['payout_ratio'] == pytest.approx(40.0, abs=0.1)

    def test_score_clamped_between_0_and_100(self, healthy_financials, healthy_dividends):
        assert 0 <= _score_dividend(healthy_financials, healthy_dividends)['score'] <= 100


# ─── 밸류에이션 스코어 ────────────────────────────────────────────────────────

class TestScoreValuation:
    def test_no_data_returns_neutral_50(self):
        result = _score_valuation(None, [])
        assert result['score'] == 50
        assert result['grade'] == 'C'

    def test_low_per_increases_score(self):
        # PER < 8 → +15
        result = _score_valuation({'per': 6.0, 'pbr': None, 'psr': None, 'ev_ebit': None}, [])
        assert result['score'] > 50
        assert any("저평가" in s for s in result['signals'])

    def test_high_per_decreases_score(self):
        # PER > 30 → -10
        result = _score_valuation({'per': 35.0, 'pbr': None, 'psr': None, 'ev_ebit': None}, [])
        assert result['score'] < 50
        assert any("고평가" in s for s in result['signals'])

    def test_low_pbr_increases_score(self):
        # PBR < 0.8 → +10
        result = _score_valuation({'per': None, 'pbr': 0.6, 'psr': None, 'ev_ebit': None}, [])
        assert result['score'] > 50

    def test_attractive_combination_high_score(self, sample_valuation, healthy_financials):
        result = _score_valuation(sample_valuation, healthy_financials)
        assert result['score'] >= 60

    def test_score_clamped_between_0_and_100(self):
        valuation = {'per': 2.0, 'pbr': 0.3, 'psr': 0.1, 'ev_ebit': 2.0}
        financials = [{
            'year': '2023', 'roe': 30.0, 'revenue': 100, 'operating_income': 20,
            'net_income': 15, 'debt_ratio': 50, 'net_debt_ratio': 5,
            'current_ratio': 200, 'liabilities': 50, 'equity': 100,
            'total_assets': 150, 'fcf': 12,
        }]
        result = _score_valuation(valuation, financials)
        assert 0 <= result['score'] <= 100

    def test_roe_pbr_undervaluation_signal(self, healthy_financials):
        # ROE=22, fair_pbr=2.2, pbr=0.9 < 2.2*0.7=1.54 → 저평가 시그널
        valuation = {'per': 12.0, 'pbr': 0.9, 'psr': 0.8, 'ev_ebit': 10.0}
        result = _score_valuation(valuation, healthy_financials)
        assert any("저평가" in s for s in result['signals'])

    def test_roe_pbr_overvaluation_signal(self, healthy_financials):
        # ROE=22, fair_pbr=2.2, pbr=4.0 > 2.2*1.5=3.3 → 고평가 시그널
        valuation = {'per': 25.0, 'pbr': 4.0, 'psr': 2.0, 'ev_ebit': 20.0}
        result = _score_valuation(valuation, healthy_financials)
        assert any("고평가" in s for s in result['signals'])


# ─── 종합 투자 스코어 ─────────────────────────────────────────────────────────

class TestComputeInvestmentScore:
    def test_output_structure(self, healthy_financials, healthy_dividends, sample_valuation):
        result = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        assert {'total_score', 'total_grade', 'categories', 'key_signals', 'summary_text'} <= result.keys()

    def test_all_categories_present(self, healthy_financials, healthy_dividends, sample_valuation):
        cats = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)['categories']
        assert set(cats.keys()) == {'growth', 'profitability', 'financial_health', 'dividend', 'valuation'}

    def test_total_score_within_range(self, healthy_financials, healthy_dividends, sample_valuation):
        result = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        assert 0 <= result['total_score'] <= 100

    def test_healthy_company_scores_high(self, healthy_financials, healthy_dividends, sample_valuation):
        result = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        assert result['total_score'] >= 65

    def test_declining_company_scores_low(self, declining_financials, sample_valuation):
        result = compute_investment_score(declining_financials, [], sample_valuation)
        assert result['total_score'] < 55

    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_weighted_score_matches_manual_calc(self, healthy_financials, healthy_dividends, sample_valuation):
        result = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        cats = result['categories']
        expected = round(sum(cats[cat]['score'] * WEIGHTS[cat] for cat in WEIGHTS), 1)
        assert abs(result['total_score'] - expected) < 0.01

    def test_key_signals_excludes_no_issue_marker(self, healthy_financials, healthy_dividends, sample_valuation):
        result = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        assert '특이 사항 없음' not in result['key_signals']

    def test_summary_text_contains_formatted_score(self, healthy_financials, healthy_dividends, sample_valuation):
        result = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        formatted = f"{result['total_score']:.0f}"
        assert formatted in result['summary_text']

    def test_empty_data_does_not_raise(self):
        result = compute_investment_score([], [], None)
        assert 'total_score' in result
        assert 0 <= result['total_score'] <= 100

    def test_healthy_beats_declining(self, healthy_financials, declining_financials,
                                     healthy_dividends, sample_valuation):
        good = compute_investment_score(healthy_financials, healthy_dividends, sample_valuation)
        bad = compute_investment_score(declining_financials, [], sample_valuation)
        assert good['total_score'] > bad['total_score']


# ─── 오너이익 계산 ────────────────────────────────────────────────────────────

class TestComputeOwnerEarnings:
    def test_uses_fcf_when_available(self, healthy_financials):
        results = compute_owner_earnings(healthy_financials)
        for r, fin in zip(results, sorted(healthy_financials, key=lambda x: x['year'])):
            if fin.get('fcf') and fin.get('net_income'):
                assert r['owner_earnings'] == fin['fcf']
                assert r['method'] == "FCF 기반"

    def test_falls_back_to_80pct_net_income(self):
        financials = [{
            'year': '2023', 'revenue': 100_000, 'net_income': 10_000, 'fcf': None,
            'operating_income': 12_000, 'roe': 15.0, 'operating_margin': 12.0,
            'debt_ratio': 50.0, 'net_debt_ratio': 10.0, 'current_ratio': 180.0,
            'liabilities': 50_000, 'equity': 70_000, 'total_assets': 120_000,
        }]
        results = compute_owner_earnings(financials)
        assert results[0]['owner_earnings'] == int(10_000 * 0.8)
        assert results[0]['method'] == "순이익 기반 보수적 추정"

    def test_output_sorted_by_year(self, healthy_financials):
        results = compute_owner_earnings(healthy_financials[::-1])
        years = [r['year'] for r in results]
        assert years == sorted(years)

    def test_output_fields_present(self, healthy_financials):
        for r in compute_owner_earnings(healthy_financials):
            assert {'year', 'owner_earnings', 'method', 'oe_margin', 'fcf_ni_ratio'} <= r.keys()

    def test_oe_margin_positive_when_revenue_exists(self, healthy_financials):
        for r in compute_owner_earnings(healthy_financials):
            assert r['oe_margin'] is not None
            assert r['oe_margin'] > 0

    def test_fcf_ni_ratio_calculated(self, healthy_financials):
        for r in compute_owner_earnings(healthy_financials):
            assert r['fcf_ni_ratio'] is not None


# ─── DuPont 분해 ─────────────────────────────────────────────────────────────

class TestComputeDupont:
    def test_roe_decomposition_accuracy(self):
        # ROE = net_margin(15%) × asset_turnover(0.5) × leverage(2.0) = 15.0
        financials = [{
            'year': '2023', 'net_income': 15_000, 'revenue': 100_000, 'roe': 15.0,
            'total_assets': 200_000, 'equity': 100_000, 'operating_income': 20_000,
            'operating_margin': 20.0, 'fcf': 12_000, 'debt_ratio': 100.0,
            'net_debt_ratio': 5.0, 'current_ratio': 200.0, 'liabilities': 100_000,
        }]
        r = compute_dupont(financials)[0]
        assert r['net_margin_pct'] == pytest.approx(15.0, abs=0.01)
        assert r['asset_turnover'] == pytest.approx(0.5, abs=0.001)
        assert r['leverage'] == pytest.approx(2.0, abs=0.001)
        assert r['computed_roe'] == pytest.approx(15.0, abs=0.1)

    def test_zero_divisors_return_none(self):
        financials = [{
            'year': '2023', 'net_income': 10_000, 'revenue': 0, 'roe': 10.0,
            'total_assets': 0, 'equity': 0, 'operating_income': 5_000,
            'operating_margin': None, 'fcf': 8_000, 'debt_ratio': 50.0,
            'net_debt_ratio': 5.0, 'current_ratio': 200.0, 'liabilities': 30_000,
        }]
        r = compute_dupont(financials)[0]
        assert r['net_margin_pct'] is None
        assert r['asset_turnover'] is None
        assert r['leverage'] is None
        assert r['computed_roe'] is None

    def test_output_sorted_by_year(self, healthy_financials):
        results = compute_dupont(healthy_financials[::-1])
        years = [r['year'] for r in results]
        assert years == sorted(years)

    def test_output_fields_present(self, healthy_financials):
        for r in compute_dupont(healthy_financials):
            assert {'year', 'roe', 'net_margin_pct', 'asset_turnover', 'leverage', 'computed_roe'} <= r.keys()

    def test_computed_roe_close_to_actual(self, healthy_financials):
        for r in compute_dupont(healthy_financials):
            if r['computed_roe'] is not None and r['roe'] is not None:
                # 기말 자본 기준이라 평균 자본 기반 실제 ROE와 15%p 이내 오차 허용
                assert abs(r['computed_roe'] - r['roe']) < 15


# ─── YoY 하이라이트 ───────────────────────────────────────────────────────────

class TestComputeYoyHighlights:
    def test_single_record_returns_empty(self):
        financials = [{'year': '2023', 'revenue': 100_000, 'operating_income': 10_000,
                       'net_income': 8_000, 'fcf': 6_000, 'roe': 12.0, 'debt_ratio': 80.0}]
        assert compute_yoy_highlights(financials) == []

    def test_large_revenue_increase_detected(self, healthy_financials):
        # 2022→2023: 158000→200000 ≈ +26.6% ≥ 15%
        highlights = compute_yoy_highlights(healthy_financials)
        assert any("매출" in h and "증가" in h for h in highlights)

    def test_small_change_not_reported(self):
        financials = [
            {'year': '2022', 'revenue': 100_000, 'operating_income': 10_000,
             'net_income': 8_000, 'fcf': 6_000, 'roe': 12.0, 'debt_ratio': 80.0},
            {'year': '2023', 'revenue': 105_000, 'operating_income': 10_200,
             'net_income': 8_100, 'fcf': 6_100, 'roe': 12.2, 'debt_ratio': 79.5},
        ]
        assert compute_yoy_highlights(financials) == []

    def test_roe_change_3pct_detected(self):
        financials = [
            {'year': '2022', 'revenue': 100_000, 'operating_income': 10_000,
             'net_income': 8_000, 'fcf': 6_000, 'roe': 10.0, 'debt_ratio': 80.0},
            {'year': '2023', 'revenue': 100_000, 'operating_income': 10_000,
             'net_income': 8_000, 'fcf': 6_000, 'roe': 15.0, 'debt_ratio': 80.0},
        ]
        highlights = compute_yoy_highlights(financials)
        assert any("ROE" in h for h in highlights)

    def test_debt_ratio_change_10pct_detected(self):
        financials = [
            {'year': '2022', 'revenue': 100_000, 'operating_income': 10_000,
             'net_income': 8_000, 'fcf': 6_000, 'roe': 12.0, 'debt_ratio': 100.0},
            {'year': '2023', 'revenue': 100_000, 'operating_income': 10_000,
             'net_income': 8_000, 'fcf': 6_000, 'roe': 12.0, 'debt_ratio': 130.0},
        ]
        highlights = compute_yoy_highlights(financials)
        assert any("부채비율" in h for h in highlights)

    def test_uses_latest_two_years_only(self, healthy_financials):
        highlights = compute_yoy_highlights(healthy_financials)
        # 2023년 기준 하이라이트만 포함돼야 함
        for h in highlights:
            assert "2023" in h

    def test_revenue_decline_detected(self, declining_financials):
        highlights = compute_yoy_highlights(declining_financials)
        assert any("매출" in h and "감소" in h for h in highlights)
