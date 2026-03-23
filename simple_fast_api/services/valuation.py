"""주가 기반 밸류에이션 지표 계산 모듈."""
import xml.etree.ElementTree as ET
import yfinance as yf
from services.dart import REPORTS_DIR, fetch_dart_financials, get_corp_code


def get_stock_code(company_name: str) -> str | None:
    """corpCode.xml에서 종목코드(stock_code)를 반환합니다."""
    import os, zipfile, requests
    from services.dart import DART_API_KEY, CORP_CODE_URL

    corp_code_path = os.path.join(REPORTS_DIR, 'CORPCODE.xml')
    if not os.path.exists(corp_code_path):
        res = requests.get(CORP_CODE_URL, params={'crtfc_key': DART_API_KEY}, timeout=30)
        res.raise_for_status()
        with zipfile.ZipFile(__import__('io').BytesIO(res.content)) as z:
            z.extractall(REPORTS_DIR)

    root = ET.parse(corp_code_path).getroot()
    for item in root.findall('.//list'):
        if item.find('corp_name').text == company_name:
            code = item.find('stock_code').text
            return code.strip() if code and code.strip() else None
    return None


def fetch_valuation(company_name: str) -> dict:
    """
    yfinance + DART 데이터를 결합해 밸류에이션 지표를 반환합니다.

    반환 지표:
    - market_cap   : 시가총액 (원)
    - price        : 현재 주가 (원)
    - shares       : 발행주식수
    - per          : 주가수익비율 (주가 / EPS)
    - pbr          : 주가순자산비율 (시가총액 / 자본총계)
    - psr          : 주가매출비율 (시가총액 / 매출액)
    - ev           : 기업가치 EV (시가총액 + 순부채)
    - ev_ebit      : EV / 영업이익
    - financials   : 최근 3개년 지표 이력 (per, pbr, psr)
    """
    from datetime import datetime
    from fastapi import HTTPException

    # 1. 종목코드 조회
    stock_code = get_stock_code(company_name)
    if not stock_code:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 상장 종목코드를 찾을 수 없습니다.")

    # 2. yfinance로 현재 주가 / 시가총액 / 발행주식수
    ticker_ks = yf.Ticker(f'{stock_code}.KS')
    info = ticker_ks.info
    price = info.get('currentPrice') or info.get('regularMarketPrice')
    if not price:
        ticker_kq = yf.Ticker(f'{stock_code}.KQ')
        info = ticker_kq.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
    if not price:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 주가 정보를 가져올 수 없습니다.")

    shares = info.get('sharesOutstanding')
    market_cap = price * shares if shares else info.get('marketCap')

    # 3. DART 최근 3개년 재무 데이터
    corp_code = get_corp_code(company_name)
    current_year = datetime.now().year
    yearly = []
    for y in range(current_year - 1, current_year - 4, -1):
        f = fetch_dart_financials(corp_code, str(y))
        if f:
            yearly.append(f)

    if not yearly:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 재무 데이터를 찾을 수 없습니다.")

    latest = yearly[0]
    equity      = latest.get('equity')
    revenue     = latest.get('revenue')
    op_income   = latest.get('operating_income')
    eps         = latest.get('eps')
    net_debt    = latest.get('net_debt')  # 이자부부채 - 현금

    # 4. 현재 시점 밸류에이션
    def safe_round(a, b, digits=2):
        return round(a / b, digits) if a and b else None

    per = safe_round(price, eps) if eps and eps > 0 else None
    pbr = safe_round(market_cap, equity) if market_cap and equity else None
    psr = safe_round(market_cap, revenue) if market_cap and revenue else None
    ev  = (market_cap + net_debt) if (market_cap and net_debt is not None) else market_cap
    ev_ebit = safe_round(ev, op_income) if ev and op_income and op_income > 0 else None

    # 5. 연도별 이력 (주가 추정: EPS * PER은 순환논리라 당기 BPS/EPS 기준)
    history = []
    for f in yearly:
        y_eps    = f.get('eps')
        y_eq     = f.get('equity')
        y_rev    = f.get('revenue')
        y_op     = f.get('operating_income')
        y_nd     = f.get('net_debt')
        y_per    = safe_round(price, y_eps) if y_eps and y_eps > 0 else None
        y_pbr    = safe_round(market_cap, y_eq) if market_cap and y_eq else None
        y_psr    = safe_round(market_cap, y_rev) if market_cap and y_rev else None
        y_ev     = (market_cap + y_nd) if (market_cap and y_nd is not None) else market_cap
        y_ev_ebit = safe_round(y_ev, y_op) if y_ev and y_op and y_op > 0 else None
        history.append({
            'year': f['year'],
            'per': y_per, 'pbr': y_pbr, 'psr': y_psr,
            'ev_ebit': y_ev_ebit,
            'eps': y_eps, 'equity': y_eq, 'revenue': y_rev,
        })

    return {
        'company_name': company_name,
        'stock_code': stock_code,
        'price': price,
        'shares': shares,
        'market_cap': market_cap,
        'per': per,
        'pbr': pbr,
        'psr': psr,
        'ev': ev,
        'ev_ebit': ev_ebit,
        'latest_year': latest['year'],
        'history': history,
    }
