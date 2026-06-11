import pytest


@pytest.fixture
def healthy_financials():
    """5개년 지속 성장 우량 기업 재무 데이터 (rev CAGR ≈ 19%, ni CAGR ≈ 27%)"""
    return [
        {
            'year': '2019', 'revenue': 100_000, 'operating_income': 15_000,
            'net_income': 10_000, 'roe': 12.0, 'operating_margin': 15.0,
            'fcf': 8_000, 'debt_ratio': 80.0, 'net_debt_ratio': 20.0,
            'current_ratio': 180.0, 'liabilities': 120_000, 'equity': 150_000,
            'total_assets': 270_000, 'eps': 5_000, 'net_debt': 30_000,
        },
        {
            'year': '2020', 'revenue': 115_000, 'operating_income': 18_000,
            'net_income': 12_500, 'roe': 14.0, 'operating_margin': 15.7,
            'fcf': 10_000, 'debt_ratio': 75.0, 'net_debt_ratio': 16.0,
            'current_ratio': 190.0, 'liabilities': 112_500, 'equity': 162_000,
            'total_assets': 274_500, 'eps': 5_800, 'net_debt': 26_000,
        },
        {
            'year': '2021', 'revenue': 135_000, 'operating_income': 22_500,
            'net_income': 16_000, 'roe': 16.5, 'operating_margin': 16.7,
            'fcf': 13_000, 'debt_ratio': 68.0, 'net_debt_ratio': 12.0,
            'current_ratio': 205.0, 'liabilities': 105_000, 'equity': 178_000,
            'total_assets': 283_000, 'eps': 7_000, 'net_debt': 21_000,
        },
        {
            'year': '2022', 'revenue': 158_000, 'operating_income': 28_000,
            'net_income': 20_500, 'roe': 19.0, 'operating_margin': 17.7,
            'fcf': 17_000, 'debt_ratio': 60.0, 'net_debt_ratio': 7.0,
            'current_ratio': 218.0, 'liabilities': 97_000, 'equity': 195_000,
            'total_assets': 292_000, 'eps': 8_800, 'net_debt': 14_000,
        },
        {
            'year': '2023', 'revenue': 200_000, 'operating_income': 38_000,
            'net_income': 26_000, 'roe': 22.0, 'operating_margin': 19.0,
            'fcf': 23_000, 'debt_ratio': 52.0, 'net_debt_ratio': 2.0,
            'current_ratio': 235.0, 'liabilities': 88_000, 'equity': 220_000,
            'total_assets': 308_000, 'eps': 10_500, 'net_debt': 5_000,
        },
    ]


@pytest.fixture
def declining_financials():
    """5개년 지속 하락 부실 기업 재무 데이터 (rev CAGR ≈ -16%, 적자 전환)"""
    return [
        {
            'year': '2019', 'revenue': 200_000, 'operating_income': 15_000,
            'net_income': 10_000, 'roe': 8.0, 'operating_margin': 7.5,
            'fcf': 2_000, 'debt_ratio': 250.0, 'net_debt_ratio': 120.0,
            'current_ratio': 80.0, 'liabilities': 350_000, 'equity': 140_000,
            'total_assets': 490_000, 'eps': 3_000, 'net_debt': 168_000,
        },
        {
            'year': '2020', 'revenue': 170_000, 'operating_income': 10_000,
            'net_income': 6_000, 'roe': 5.5, 'operating_margin': 5.9,
            'fcf': -1_000, 'debt_ratio': 280.0, 'net_debt_ratio': 140.0,
            'current_ratio': 75.0, 'liabilities': 380_000, 'equity': 135_000,
            'total_assets': 515_000, 'eps': 2_000, 'net_debt': 189_000,
        },
        {
            'year': '2021', 'revenue': 150_000, 'operating_income': 6_000,
            'net_income': 2_000, 'roe': 2.0, 'operating_margin': 4.0,
            'fcf': -3_000, 'debt_ratio': 310.0, 'net_debt_ratio': 160.0,
            'current_ratio': 70.0, 'liabilities': 400_000, 'equity': 129_000,
            'total_assets': 529_000, 'eps': 700, 'net_debt': 206_000,
        },
        {
            'year': '2022', 'revenue': 130_000, 'operating_income': 3_000,
            'net_income': -2_000, 'roe': -1.5, 'operating_margin': 2.3,
            'fcf': -6_000, 'debt_ratio': 360.0, 'net_debt_ratio': 185.0,
            'current_ratio': 65.0, 'liabilities': 430_000, 'equity': 120_000,
            'total_assets': 550_000, 'eps': -700, 'net_debt': 222_000,
        },
        {
            'year': '2023', 'revenue': 100_000, 'operating_income': 1_000,
            'net_income': -5_000, 'roe': -4.0, 'operating_margin': 1.0,
            'fcf': -9_000, 'debt_ratio': 420.0, 'net_debt_ratio': 210.0,
            'current_ratio': 55.0, 'liabilities': 470_000, 'equity': 112_000,
            'total_assets': 582_000, 'eps': -1_800, 'net_debt': 235_000,
        },
    ]


@pytest.fixture
def healthy_dividends():
    """5개년 지속 증가 배당 데이터 (CAGR ≈ 22%)"""
    return [
        {'year': '2019', 'dividend': 500},
        {'year': '2020', 'dividend': 600},
        {'year': '2021', 'dividend': 750},
        {'year': '2022', 'dividend': 900},
        {'year': '2023', 'dividend': 1_100},
    ]


@pytest.fixture
def sample_valuation():
    """적정 밸류에이션 샘플 (PER 10.5x, PBR 0.9x)"""
    return {'per': 10.5, 'pbr': 0.9, 'psr': 0.8, 'ev_ebit': 9.0}
