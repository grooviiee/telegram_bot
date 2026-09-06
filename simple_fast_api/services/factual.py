"""단순 수치 질문은 정규식과 계산 결과로 답하고 해석 질문만 AI로 넘깁니다."""
import re
from config import YEAR_RANGE
from utils import fmt_krw
from services.company_data import annual_data, valuation_data


async def answer_factual(company: str, corp_code: str, message: str) -> str | None:
    """지원하는 단일 지표 조회에만 응답하고 모호한 질문은 None을 반환합니다."""
    if message.strip().rstrip('!.?') in ('안녕', '안녕하세요', '도움말', '고마워', '감사합니다'):
        return '매출·배당·ROE 같은 수치는 AI 없이 조회합니다. 예: "2025년 매출 알려줘". 원인·위험·사업 경쟁력 해석이 필요하면 질문해주세요.'
    # 전체 문장이 일치해야 하므로 '왜', 비교, 전망 등 해석 요청을 가로채지 않습니다.
    match = re.fullmatch(
        r'\s*(?:(\d{4})년?\s*|(최근|최신)\s*)?'
        r'(매출액?|영업이익|당기순이익|순이익|ROE|부채비율|영업이익률|FCF|배당금?|PER|PBR|PSR|현재가)'
        r'\s*(?:(?:은|는|이|가)\s*)?(?:얼마(?:야|인가요|예요)?|알려\s*줘|조회|보여\s*줘)?[?.!？]*\s*',
        message, re.IGNORECASE,
    )
    if not match:
        return None
    year, _, label = match.groups()
    label = label.upper()
    if label in ('PER', 'PBR', 'PSR', '현재가'):
        if year:
            return '과거 시세 기준 밸류에이션은 제공하지 않습니다. 현재가 기준 PER/PBR/PSR을 조회할 수 있습니다.'
        data, _ = await valuation_data(company)
        key = {'PER': 'per', 'PBR': 'pbr', 'PSR': 'psr', '현재가': 'price'}[label]
        value = data.get(key)
        shown = '데이터 없음' if value is None else fmt_krw(value) if key == 'price' else f'{value}배'
        return f"{company} {label}: {shown}\n출처: yfinance + DART, 재무 기준 {data['latest_year']}년\n조회시각: {data['provenance']['retrieved_at']} (시세 체결시각 아님)"
    dividend = label.startswith('배당')
    data, _ = await annual_data(company, corp_code, 'dividends' if dividend else 'financials')
    rows = data['dividend_data' if dividend else 'financials']
    row = next((r for r in rows if r['year'] == int(year)), None) if year else rows[-1]
    if row is None:
        return f'{company} {year}년 데이터가 조회되지 않았습니다. 유효한 최근 {YEAR_RANGE}개년만 제공합니다.'
    key = {'매출': 'revenue', '매출액': 'revenue', '영업이익': 'operating_income',
           '당기순이익': 'net_income', '순이익': 'net_income', 'ROE': 'roe',
           '부채비율': 'debt_ratio', '영업이익률': 'operating_margin', 'FCF': 'fcf',
           '배당': 'dividend', '배당금': 'dividend'}[label]
    value = row.get(key)
    shown = '데이터 없음 (0을 의미하지 않음)' if value is None else f'{value}%' if key in ('roe', 'debt_ratio', 'operating_margin') else fmt_krw(value)
    return f"{company} {row['year']}년 {label}: {shown}\n출처: DART ({row.get('fs_div', '배당 공시')})\n조회시각: {data['provenance']['retrieved_at']}"
