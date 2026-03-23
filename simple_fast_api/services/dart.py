"""DART Open API 호출 전용 헬퍼 함수."""
import io, os, re, zipfile, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import HTTPException
from bs4 import BeautifulSoup

load_dotenv(override=True)
DART_API_KEY: str = os.getenv("DART_API_KEY", "")
REPORTS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dart_reports")
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
os.makedirs(REPORTS_DIR, exist_ok=True)

_QUARTER_REPRT_CODE: dict[str, str] = {
    'Q1': '11013',
    'Q2': '11012',
    'Q3': '11014',
    'Q4': '11011',
}


def parse_dart_amount(value_str: str) -> int | None:
    """DART API 금액 문자열을 정수로 변환합니다. 회계 괄호 표기법도 처리합니다."""
    if not value_str or value_str.strip() == '':
        return None
    cleaned = value_str.replace(',', '').replace(' ', '')
    # 회계 표기법: (1234) → -1234
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        return int(cleaned)
    except ValueError:
        return None


def get_account_value(accounts: dict, *names: str) -> int | None:
    """여러 후보 계정명 중 첫 번째 매칭되는 당기 금액을 반환합니다."""
    for name in names:
        if name in accounts:
            val = accounts[name].get('thstrm_amount', '') or ''
            return parse_dart_amount(val)
    return None


def _accounts_to_metrics(accounts: dict, year: int, fs_div: str) -> dict:
    """DART 계정 딕셔너리에서 재무 지표를 계산하여 반환합니다."""
    revenue          = get_account_value(accounts, '매출액', '수익(매출액)', '영업수익', '순매출액')
    operating_income = get_account_value(accounts, '영업이익', '영업이익(손실)')
    net_income       = get_account_value(accounts, '당기순이익', '당기순이익(손실)', '당기순손익')
    total_assets     = get_account_value(accounts, '자산총계')
    equity           = get_account_value(accounts, '자본총계')
    liabilities      = get_account_value(accounts, '부채총계')
    current_assets   = get_account_value(accounts, '유동자산')
    current_liab     = get_account_value(accounts, '유동부채')
    op_cash_flow     = get_account_value(accounts, '영업활동현금흐름', '영업활동으로인한현금흐름')
    capex_raw        = get_account_value(accounts, '유형자산의 취득', '유형자산취득', '유형자산의취득')
    eps              = get_account_value(accounts, '기본주당순이익(손실)', '기본주당이익(손실)', '기본주당순이익', '주당이익')
    cash             = get_account_value(accounts, '현금및현금성자산')
    # 이자부부채: 단기차입금 + 유동성장기부채 + 사채 + 장기차입금 (공시 보고서 기준)
    short_borrow     = get_account_value(accounts, '단기차입금')
    current_long     = get_account_value(accounts, '유동성장기부채')
    bonds            = get_account_value(accounts, '사채')
    long_borrow      = get_account_value(accounts, '장기차입금')
    interest_bearing = sum(x for x in [short_borrow, current_long, bonds, long_borrow] if x is not None) or None

    capex = abs(capex_raw) if capex_raw is not None else None
    operating_margin = round(operating_income / revenue * 100, 2) if revenue and operating_income else None
    roe              = round(net_income / equity * 100, 2)           if equity and net_income       else None
    debt_ratio       = round(liabilities / equity * 100, 2)          if equity and liabilities      else None
    current_ratio    = round(current_assets / current_liab * 100, 2) if current_liab and current_assets else None
    fcf              = (op_cash_flow - capex) if (op_cash_flow is not None and capex is not None) else op_cash_flow
    # 순부채 = 이자부부채 - 현금 (음수이면 순현금 보유)
    net_debt         = (interest_bearing - cash) if (interest_bearing is not None and cash is not None) else None
    net_debt_ratio   = round(net_debt / equity * 100, 2) if (equity and net_debt is not None) else None
    return {
        'year': year, 'fs_div': fs_div,
        'revenue': revenue, 'operating_income': operating_income, 'net_income': net_income,
        'total_assets': total_assets, 'equity': equity, 'liabilities': liabilities,
        'current_assets': current_assets, 'current_liabilities': current_liab,
        'op_cash_flow': op_cash_flow, 'capex': capex, 'eps': eps, 'cash': cash,
        'operating_margin': operating_margin, 'roe': roe, 'debt_ratio': debt_ratio,
        'current_ratio': current_ratio, 'fcf': fcf, 'net_debt': net_debt,
        'net_debt_ratio': net_debt_ratio,
    }


def fetch_dart_financials(corp_code: str, year: str) -> dict | None:
    """DART fnlttSinglAcntAll API로 특정 연도의 재무제표를 조회합니다. 연결 → 개별 순으로 시도합니다."""
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

    for fs_div in ['CFS', 'OFS']:
        params = {
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'bsns_year': year,
            'reprt_code': '11011',  # 사업보고서
            'fs_div': fs_div,
        }
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            data = res.json()

            if data.get('status') == '000' and data.get('list'):
                accounts = {item['account_nm']: item for item in data['list']}
                return _accounts_to_metrics(accounts, int(year), fs_div)
        except Exception as e:
            print(f"재무 데이터 조회 오류 ({year}, {fs_div}): {e}")

    return None


def fetch_dart_financials_q(corp_code: str, year: str, quarter: str) -> dict | None:
    """특정 연도/분기의 재무제표를 조회합니다. 연결 → 개별 순으로 시도합니다."""
    reprt_code = _QUARTER_REPRT_CODE.get(quarter)
    if not reprt_code:
        return None
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    for fs_div in ['CFS', 'OFS']:
        params = {
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'bsns_year': year,
            'reprt_code': reprt_code,
            'fs_div': fs_div,
        }
        try:
            res = requests.get(url, params=params, timeout=15)
            res.raise_for_status()
            data = res.json()
            if data.get('status') == '000' and data.get('list'):
                accounts = {item['account_nm']: item for item in data['list']}
                result = _accounts_to_metrics(accounts, int(year), fs_div)
                result['quarter'] = quarter
                result['label'] = year[-2:] + quarter  # 예: "23Q2"
                return result
        except Exception as e:
            print(f"분기 재무 데이터 조회 오류 ({year} {quarter}, {fs_div}): {e}")
    return None


def fetch_dividend_per_share_q(corp_code: str, year: str, quarter: str) -> int | None:
    """특정 연도/분기의 주당 배당금을 조회합니다."""
    reprt_code = _QUARTER_REPRT_CODE.get(quarter)
    if not reprt_code:
        return None

    # 1순위: 재무제표에서 배당 계정 조회
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    for fs_div in ['OFS', 'CFS']:
        try:
            res = requests.get(url, params={
                'crtfc_key': DART_API_KEY,
                'corp_code': corp_code,
                'bsns_year': year,
                'reprt_code': reprt_code,
                'fs_div': fs_div,
            }, timeout=10)
            data = res.json()
            if data.get('status') == '000' and data.get('list'):
                accounts = {item['account_nm']: item for item in data['list']}
                amount = get_account_value(
                    accounts,
                    '주당 현금배당금', '주당현금배당금',
                    '현금배당금(주당)', '주당배당금',
                )
                if amount and amount > 0:
                    return amount
        except Exception as e:
            print(f"분기 배당 fnlttSinglAcntAll 조회 오류 ({year} {quarter}, {fs_div}): {e}")

    # 2순위: alotMatter
    try:
        res2 = requests.get("https://opendart.fss.or.kr/api/alotMatter.json", params={
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'bsns_year': year,
            'reprt_code': reprt_code,
        }, timeout=10)
        data2 = res2.json()
        if data2.get('status') == '000' and data2.get('list'):
            for item in data2['list']:
                se = item.get('se', '')
                if '주당' in se and ('현금' in se or '배당' in se):
                    amount = parse_dart_amount(item.get('thstrm', '') or '')
                    if amount and amount > 0:
                        return amount
    except Exception as e:
        print(f"분기 배당 alotMatter 조회 오류 ({year} {quarter}): {e}")

    return None


def fetch_dividend_per_share(corp_code: str, year: str) -> int | None:
    """
    DART API에서 주당 현금배당금을 직접 조회합니다. Gemini/파일 다운로드 불필요.
    1순위: fnlttSinglAcntAll (재무제표 계정 직접 조회)
    2순위: alotMatter (배당에 관한 사항 전용 API)
    """
    # 1순위: 재무제표에서 배당 계정 조회
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    for fs_div in ['OFS', 'CFS']:
        try:
            res = requests.get(url, params={
                'crtfc_key': DART_API_KEY,
                'corp_code': corp_code,
                'bsns_year': year,
                'reprt_code': '11011',
                'fs_div': fs_div,
            }, timeout=10)
            data = res.json()
            if data.get('status') == '000' and data.get('list'):
                accounts = {item['account_nm']: item for item in data['list']}
                amount = get_account_value(
                    accounts,
                    '주당 현금배당금', '주당현금배당금',
                    '현금배당금(주당)', '주당배당금',
                )
                if amount and amount > 0:
                    return amount
        except Exception as e:
            print(f"fnlttSinglAcntAll 배당 조회 오류 ({year}, {fs_div}): {e}")

    # 2순위: 배당에 관한 사항 전용 API
    try:
        res2 = requests.get("https://opendart.fss.or.kr/api/alotMatter.json", params={
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'bsns_year': year,
            'reprt_code': '11011',
        }, timeout=10)
        data2 = res2.json()
        if data2.get('status') == '000' and data2.get('list'):
            for item in data2['list']:
                se = item.get('se', '')
                if '주당' in se and ('현금' in se or '배당' in se):
                    amount = parse_dart_amount(item.get('thstrm', '') or '')
                    if amount and amount > 0:
                        return amount
    except Exception as e:
        print(f"alotMatter 배당 조회 오류 ({year}): {e}")

    return None


def get_corp_code(company_name: str) -> str:
    """회사 이름을 기반으로 DART 고유의 회사 코드를 조회합니다."""
    corp_code_path = os.path.join(REPORTS_DIR, "corpCode.xml")
    if not os.path.exists(corp_code_path):
        try:
            res = requests.get(f"{CORP_CODE_URL}?crtfc_key={DART_API_KEY}")
            res.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                z.extractall(REPORTS_DIR)
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"DART 회사 코드 목록 다운로드 실패: {e}")
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(corp_code_path).getroot()
        for item in root.findall('.//list'):
            if company_name == item.find('corp_name').text: return item.find('corp_code').text
    except ET.ParseError as e:
        raise HTTPException(status_code=500, detail=f"corpCode.xml 파싱 실패: {e}")
    raise HTTPException(status_code=404, detail=f"'{company_name}' 회사 코드를 찾을 수 없음.")


def _is_data_table(table_elem) -> bool:
    """True if table looks like a data table (has <th>, or 2+ rows × 2+ cols)."""
    if table_elem.find('th'):
        return True
    rows = table_elem.find_all('tr')
    if len(rows) >= 2:
        for row in rows[:5]:
            if len(row.find_all(['td', 'th'])) >= 2:
                return True
    return False


def _clean_table_html(table_elem) -> str:
    """Return minimal HTML for a table (structural tags only, no attrs)."""
    from bs4 import Tag, NavigableString
    ALLOWED = {'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col'}

    def _clean(node) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ''
        if node.name not in ALLOWED:
            return ''.join(_clean(c) for c in node.children)
        inner = ''.join(_clean(c) for c in node.children)
        return f'<{node.name}>{inner}</{node.name}>'

    return _clean(table_elem)


def _text_to_blocks(section_text: str, tables_store: list[str]) -> list[dict]:
    """Split section text (which may contain __T{i}__ markers) into blocks."""
    parts = re.split(r'(__T\d+__)', section_text)
    blocks: list[dict] = []
    for part in parts:
        m = re.match(r'__T(\d+)__', part)
        if m:
            idx = int(m.group(1))
            if idx < len(tables_store):
                blocks.append({'type': 'table', 'html': tables_store[idx]})
        else:
            # Clean up text
            lines = [l.strip() for l in part.split('\n')]
            cleaned: list[str] = []
            prev_blank = False
            for line in lines:
                if line == '':
                    if not prev_blank:
                        cleaned.append('')
                    prev_blank = True
                else:
                    cleaned.append(line)
                    prev_blank = False
            text = '\n'.join(cleaned).strip()
            if text:
                blocks.append({'type': 'text', 'content': text})
    return blocks


def fetch_business_overview(corp_code: str, company_name: str) -> dict:
    """최신 사업보고서에서 '사업의 내용' 1~4항 텍스트를 추출합니다."""
    current_year = datetime.now().year

    # 1. 최신 사업보고서 접수번호 조회
    res = requests.get(
        "https://opendart.fss.or.kr/api/list.json",
        params={
            'crtfc_key': DART_API_KEY,
            'corp_code': corp_code,
            'pblntf_detail_ty': 'A001',   # 사업보고서
            'bgn_de': f"{current_year - 3}0101",
            'end_de': f"{current_year}1231",
            'sort': 'date',
            'sort_mth': 'desc',
            'page_count': 5,
        },
        timeout=15,
    )
    res.raise_for_status()
    list_data = res.json()
    if list_data.get('status') != '000' or not list_data.get('list'):
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 사업보고서를 찾을 수 없습니다.")

    report = list_data['list'][0]
    rcept_no  = report['rcept_no']
    report_nm = report.get('report_nm', '사업보고서')
    report_year = report.get('rcept_dt', '')[:4] or str(current_year - 1)

    # 2. 보고서 문서 zip 다운로드
    doc_res = requests.get(
        "https://opendart.fss.or.kr/api/document.xml",
        params={'crtfc_key': DART_API_KEY, 'rcept_no': rcept_no},
        timeout=120,
    )
    doc_res.raise_for_status()

    # 3. zip에서 '사업의 내용' HTML 탐색 및 1~4항 추출
    SECTION_DEFS = [
        (1, r'1\s*[.)]\s*사업의\s*개요',        '사업의 개요'),
        (2, r'2\s*[.)]\s*주요\s*제품',           '주요 제품 및 서비스'),
        (3, r'3\s*[.)]\s*원재료',                '원재료 및 생산설비'),
        (4, r'4\s*[.)]\s*매출\s*(및|&)\s*수주',  '매출 및 수주상황'),
    ]
    END_PATTERNS = [
        r'5\s*[.)]\s*위험관리',
        r'5\s*[.)]\s*주요계약',
        r'[Ⅲ3]\s*[.)]\s*재무',
        r'제\s*3\s*장',
    ]

    sections_found: dict[int, list[dict]] = {}

    with zipfile.ZipFile(io.BytesIO(doc_res.content)) as z:
        html_files = sorted(f for f in z.namelist()
                            if f.lower().endswith(('.html', '.htm', '.xml'))
                            and not f.startswith('__'))

        for fname in html_files:
            with z.open(fname) as f:
                raw = f.read()

            for enc in ('euc-kr', 'utf-8', 'cp949'):
                try:
                    content = raw.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                continue

            if '사업의 내용' not in content:
                continue

            # Replace data tables with markers; layout tables → plain text
            soup = BeautifulSoup(content, 'html.parser')
            tables_store: list[str] = []
            for table in soup.find_all('table'):
                if _is_data_table(table):
                    marker = f'\n__T{len(tables_store)}__\n'
                    tables_store.append(_clean_table_html(table))
                    table.replace_with(marker)
                else:
                    table.replace_with(table.get_text('\n'))

            text = soup.get_text('\n')

            for i, (num, pattern, _) in enumerate(SECTION_DEFS):
                m = re.search(pattern, text)
                if not m:
                    continue

                start = m.start()
                end   = len(text)

                # 다음 항 또는 종료 패턴에서 자르기
                next_pats = [p for _, p, _ in SECTION_DEFS[i + 1:]] + END_PATTERNS
                for np in next_pats:
                    nm = re.search(np, text[start + 80:])
                    if nm:
                        candidate = start + 80 + nm.start()
                        if candidate < end:
                            end = candidate

                section_text = text[start:end].strip()

                # 너무 짧으면 실제 내용이 없는 것으로 간주
                if len(section_text) > 80 and num not in sections_found:
                    if len(section_text) > 8000:
                        section_text = section_text[:8000] + '\n\n... (이하 생략)'
                    blocks = _text_to_blocks(section_text, tables_store)
                    sections_found[num] = blocks

            if sections_found:
                break   # 첫 번째로 내용이 담긴 파일에서 완료

    if not sections_found:
        raise HTTPException(status_code=404,
                            detail=f"'{company_name}'의 사업의 내용을 추출할 수 없습니다.")

    sections = [
        {'number': num, 'title': title, 'blocks': sections_found[num]}
        for num, _, title in SECTION_DEFS
        if num in sections_found
    ]

    return {
        'company_name': company_name,
        'report_name': report_nm,
        'report_year': report_year,
        'rcept_no': rcept_no,
        'sections': sections,
    }


def download_reports_logic(company_name: str, corp_code: str):
    """주어진 회사 코드에 대해 최근 5년간의 보고서를 검색하고 다운로드합니다."""
    print(f"'{company_name}'의 보고서 다운로드를 시작합니다...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5 * 365)
    list_url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        'crtfc_key': DART_API_KEY, 'corp_code': corp_code,
        'bgn_de': start_date.strftime('%Y%m%d'), 'end_de': end_date.strftime('%Y%m%d'),
        'pblntf_ty': 'A', 'pblntf_detail_ty': ['A001', 'A002', 'A003'],
        'page_no': 1, 'page_count': 100
    }
    try:
        res = requests.get(list_url, params=params)
        res.raise_for_status()
        data = res.json()
        if data.get('status') != '000' or not data.get('list'): return
        for report in data['list']:
            report_nm, rcept_no = report.get('report_nm', 'N/A'), report.get('rcept_no')
            if any(k in report_nm for k in ['사업보고서', '분기보고서', '반기보고서']):
                download_url = "https://opendart.fss.or.kr/api/document.xml"
                doc_res = requests.get(download_url, params={'crtfc_key': DART_API_KEY, 'rcept_no': rcept_no})
                doc_res.raise_for_status()
                file_name = f"{company_name}_{report_nm.replace(' ', '_')}_{report.get('rcept_dt')}.zip"
                with open(os.path.join(REPORTS_DIR, file_name), 'wb') as f: f.write(doc_res.content)
                print(f" -> 성공: '{file_name}' 저장 완료.")
    except Exception as e:
        print(f"보고서 다운로드 중 오류 발생: {e}")
