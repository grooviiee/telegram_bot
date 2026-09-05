"""DART Open API 호출 전용 헬퍼 함수."""
import asyncio, io, re, zipfile, requests
from datetime import datetime, timedelta
from fastapi import HTTPException
from bs4 import BeautifulSoup

from config import (
    DART_API_KEY, DART_BASE_URL, DART_CORP_CODE_URL, DART_LIST_URL,
    DART_FINANCIALS_URL, DART_DIVIDEND_URL, DART_ELESTOCK_URL,
    DART_DOCUMENT_URL, REPORTS_DIR, FS_DIV_ORDER, QUARTER_REPRT_CODE,
    ANNUAL_REPRT_CODE,
)


# ── DART API 공통 헬퍼 ──────────────────────────────────────────────────────

def _dart_get(url: str, extra_params: dict, timeout: int = 15) -> dict:
    """DART API GET 요청을 수행합니다. crtfc_key를 자동으로 추가합니다.

    Returns:
        응답 JSON dict. 네트워크 오류 시 예외를 그대로 전파합니다.
    """
    params = {'crtfc_key': DART_API_KEY, **extra_params}
    res = requests.get(url, params=params, timeout=timeout)
    res.raise_for_status()
    return res.json()


def _dart_get_raw(url: str, extra_params: dict, timeout: int = 15) -> bytes:
    """DART API GET 요청의 원본 바이트를 반환합니다."""
    params = {'crtfc_key': DART_API_KEY, **extra_params}
    res = requests.get(url, params=params, timeout=timeout)
    res.raise_for_status()
    return res.content


def _fetch_with_fs_fallback(url: str, params: dict, fs_order: list[str] | None = None) -> tuple[dict | None, str]:
    """연결(CFS) → 개별(OFS) 순으로 재무제표를 조회합니다.

    Returns:
        (accounts_dict, fs_div) 또는 (None, "") — accounts_dict는 {account_nm: item}
    """
    if fs_order is None:
        fs_order = FS_DIV_ORDER
    for fs_div in fs_order:
        try:
            data = _dart_get(url, {**params, 'fs_div': fs_div})
            if data.get('status') == '000' and data.get('list'):
                accounts = {item['account_nm']: item for item in data['list']}
                return accounts, fs_div
        except Exception as e:
            print(f"재무 데이터 조회 오류 ({params.get('bsns_year')}, {fs_div}): {type(e).__name__}")
    return None, ""


# ── 금액 파싱 ────────────────────────────────────────────────────────────────

def parse_dart_amount(value_str: str) -> int | None:
    """DART API 금액 문자열을 정수로 변환합니다. 회계 괄호 표기법도 처리합니다."""
    if not value_str or value_str.strip() == '':
        return None
    cleaned = value_str.replace(',', '').replace(' ', '')
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


def _parse_int(raw: str) -> int:
    """DART 정수 문자열 파싱 (콤마, '-' 처리)."""
    if not raw or raw.strip() in ('-', ''):
        return 0
    try:
        return int(raw.replace(',', ''))
    except ValueError:
        return 0


# ── 재무 지표 계산 ───────────────────────────────────────────────────────────

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
    short_borrow     = get_account_value(accounts, '단기차입금')
    current_long     = get_account_value(accounts, '유동성장기부채')
    bonds            = get_account_value(accounts, '사채')
    long_borrow      = get_account_value(accounts, '장기차입금')
    interest_bearing = sum([short_borrow, current_long, bonds, long_borrow]) if all(x is not None for x in [short_borrow, current_long, bonds, long_borrow]) else None

    capex = abs(capex_raw) if capex_raw is not None else None
    operating_margin = round(operating_income / revenue * 100, 2) if revenue and operating_income is not None else None
    roe              = round(net_income / equity * 100, 2)           if equity and net_income is not None       else None
    debt_ratio       = round(liabilities / equity * 100, 2)          if equity and liabilities is not None      else None
    current_ratio    = round(current_assets / current_liab * 100, 2) if current_liab and current_assets is not None else None
    fcf              = (op_cash_flow - capex) if (op_cash_flow is not None and capex is not None) else None
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


# ── 재무제표 조회 ────────────────────────────────────────────────────────────

def fetch_dart_financials(corp_code: str, year: str) -> dict | None:
    """DART fnlttSinglAcntAll API로 특정 연도의 재무제표를 조회합니다."""
    accounts, fs_div = _fetch_with_fs_fallback(
        DART_FINANCIALS_URL,
        {'corp_code': corp_code, 'bsns_year': year, 'reprt_code': ANNUAL_REPRT_CODE},
    )
    if accounts is None:
        return None
    return _accounts_to_metrics(accounts, int(year), fs_div)


def fetch_dart_financials_q(corp_code: str, year: str, quarter: str) -> dict | None:
    """특정 연도/분기의 재무제표를 조회합니다."""
    reprt_code = QUARTER_REPRT_CODE.get(quarter)
    if not reprt_code:
        return None
    accounts, fs_div = _fetch_with_fs_fallback(
        DART_FINANCIALS_URL,
        {'corp_code': corp_code, 'bsns_year': year, 'reprt_code': reprt_code},
    )
    if accounts is None:
        return None
    result = _accounts_to_metrics(accounts, int(year), fs_div)
    result['quarter'] = quarter
    result['label'] = year[-2:] + quarter
    return result


# ── 배당 조회 ────────────────────────────────────────────────────────────────

def _fetch_dividend_common(corp_code: str, year: str, reprt_code: str) -> int | None:
    """재무제표(fnlttSinglAcntAll) → alotMatter 순으로 주당 배당금을 조회합니다."""
    # 1순위: 재무제표에서 배당 계정 조회 (OFS 우선 — 개별 기준이 배당에 적합)
    accounts, _ = _fetch_with_fs_fallback(
        DART_FINANCIALS_URL,
        {'corp_code': corp_code, 'bsns_year': year, 'reprt_code': reprt_code},
        fs_order=['OFS', 'CFS'],
    )
    if accounts is not None:
        amount = get_account_value(
            accounts, '주당 현금배당금', '주당현금배당금', '현금배당금(주당)', '주당배당금',
        )
        if amount is not None and amount >= 0:
            return amount

    # 2순위: alotMatter API
    try:
        data = _dart_get(DART_DIVIDEND_URL, {
            'corp_code': corp_code, 'bsns_year': year, 'reprt_code': reprt_code,
        }, timeout=10)
        if data.get('status') == '000' and data.get('list'):
            for item in data['list']:
                se = item.get('se', '')
                if '주당' in se and ('현금' in se or '배당' in se):
                    amount = parse_dart_amount(item.get('thstrm', '') or '')
                    if amount is not None and amount >= 0:
                        return amount
    except Exception as e:
        print(f"alotMatter 배당 조회 오류 ({year}): {type(e).__name__}")

    return None


def fetch_dividend_per_share(corp_code: str, year: str) -> int | None:
    """연간 주당 현금배당금을 조회합니다."""
    return _fetch_dividend_common(corp_code, year, ANNUAL_REPRT_CODE)


def fetch_dividend_per_share_q(corp_code: str, year: str, quarter: str) -> int | None:
    """특정 분기의 주당 배당금을 조회합니다."""
    reprt_code = QUARTER_REPRT_CODE.get(quarter)
    if not reprt_code:
        return None
    return _fetch_dividend_common(corp_code, year, reprt_code)


# ── 회사 코드 조회 ───────────────────────────────────────────────────────────

def _load_corp_xml_root():
    """corpCode.xml을 로드하고 ElementTree root를 반환합니다."""
    import os
    import xml.etree.ElementTree as ET
    corp_code_path = os.path.join(REPORTS_DIR, "corpCode.xml")
    if not os.path.exists(corp_code_path):
        try:
            content = _dart_get_raw(DART_CORP_CODE_URL, {})
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                z.extractall(REPORTS_DIR)
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"DART 회사 코드 목록 다운로드 실패: {type(e).__name__}")
    try:
        return ET.parse(corp_code_path).getroot()
    except ET.ParseError as e:
        raise HTTPException(status_code=500, detail=f"corpCode.xml 파싱 실패: {type(e).__name__}")


def get_corp_code(company_name: str) -> str:
    """회사 이름을 기반으로 DART 고유의 회사 코드를 조회합니다.

    매칭 우선순위:
      1. 완전 일치 (대소문자 구분)
      2. 완전 일치 (대소문자 무시)
      3. 상장사 중 부분 일치 (대소문자 무시) — 단 1건일 때만 자동 선택
    """
    root = _load_corp_xml_root()
    query_lower = company_name.lower()

    exact, iexact, partial = None, None, []
    for item in root.findall('.//list'):
        name_el = item.find('corp_name')
        stock_el = item.find('stock_code')
        if name_el is None:
            continue
        name = name_el.text or ''
        stock = (stock_el.text or '').strip() if stock_el is not None else ''
        code = item.find('corp_code').text

        if name == company_name:
            exact = code
            break
        if name.lower() == query_lower and iexact is None:
            iexact = (code, name)
        if stock and query_lower in name.lower():
            partial.append((code, name))

    if exact:
        return exact
    if iexact:
        return iexact[0]
    if len(partial) == 1:
        return partial[0][0]

    raise HTTPException(status_code=404, detail=f"'{company_name}' 회사 코드를 찾을 수 없음.")


async def resolve_corp_code(company_name: str) -> str:
    """get_corp_code(동기, XML 파싱)를 이벤트 루프를 막지 않고 실행한다."""
    return await asyncio.to_thread(get_corp_code, company_name)


def search_similar_companies(query: str, max_results: int = 5) -> list[str]:
    """쿼리와 유사한 상장 기업명 목록을 반환합니다 (상장사만, stock_code 보유 기준)."""
    try:
        root = _load_corp_xml_root()
    except Exception:
        return []

    query_lower = query.lower()
    starts_with, contains = [], []
    for item in root.findall('.//list'):
        name_el = item.find('corp_name')
        stock_el = item.find('stock_code')
        if name_el is None:
            continue
        name = name_el.text or ''
        stock = (stock_el.text or '').strip() if stock_el is not None else ''
        if not stock:
            continue
        if name.lower() == query_lower:
            continue
        name_lower = name.lower()
        if name_lower.startswith(query_lower):
            starts_with.append(name)
        elif query_lower in name_lower:
            contains.append(name)

    results = starts_with + contains
    seen, unique = set(), []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique[:max_results]


# ── 사업의 내용 추출 ─────────────────────────────────────────────────────────

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
    """Return minimal HTML for a table (structural tags only, keep colspan/rowspan)."""
    from bs4 import Tag, NavigableString
    ALLOWED = {'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col'}
    KEEP_ATTRS = {
        'td':  {'colspan', 'rowspan'},
        'th':  {'colspan', 'rowspan'},
        'col': {'span'},
    }

    def _clean(node) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ''
        if node.name not in ALLOWED:
            return ''.join(_clean(c) for c in node.children)
        inner = ''.join(_clean(c) for c in node.children)
        attrs_str = ''
        for attr in KEEP_ATTRS.get(node.name, set()):
            val = node.get(attr)
            if val and str(val) not in ('1', ''):
                attrs_str += f' {attr}="{val}"'
        return f'<{node.name}{attrs_str}>{inner}</{node.name}>'

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
    list_data = _dart_get(DART_LIST_URL, {
        'corp_code': corp_code,
        'pblntf_detail_ty': 'A001',
        'bgn_de': f"{current_year - 3}0101",
        'end_de': f"{current_year}1231",
        'sort': 'date',
        'sort_mth': 'desc',
        'page_count': 5,
    })
    if list_data.get('status') != '000' or not list_data.get('list'):
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 사업보고서를 찾을 수 없습니다.")

    report = list_data['list'][0]
    rcept_no  = report['rcept_no']
    report_nm = report.get('report_nm', '사업보고서')
    report_year = report.get('rcept_dt', '')[:4] or str(current_year - 1)

    # 2. 보고서 문서 zip 다운로드
    doc_content = _dart_get_raw(DART_DOCUMENT_URL, {'rcept_no': rcept_no}, timeout=120)

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

    with zipfile.ZipFile(io.BytesIO(doc_content)) as z:
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

                next_pats = [p for _, p, _ in SECTION_DEFS[i + 1:]] + END_PATTERNS
                for np in next_pats:
                    nm = re.search(np, text[start + 80:])
                    if nm:
                        candidate = start + 80 + nm.start()
                        if candidate < end:
                            end = candidate

                section_text = text[start:end].strip()

                if len(section_text) > 80 and num not in sections_found:
                    if len(section_text) > 8000:
                        section_text = section_text[:8000] + '\n\n... (이하 생략)'
                    blocks = _text_to_blocks(section_text, tables_store)
                    sections_found[num] = blocks

            if sections_found:
                break

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


# ── 보고서 다운로드 ──────────────────────────────────────────────────────────

def download_reports_logic(company_name: str, corp_code: str):
    """주어진 회사 코드에 대해 최근 5년간의 보고서를 검색하고 다운로드합니다."""
    import os
    print(f"'{company_name}'의 보고서 다운로드를 시작합니다...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5 * 365)
    try:
        data = _dart_get(DART_LIST_URL, {
            'corp_code': corp_code,
            'bgn_de': start_date.strftime('%Y%m%d'),
            'end_de': end_date.strftime('%Y%m%d'),
            'pblntf_ty': 'A',
            'pblntf_detail_ty': ['A001', 'A002', 'A003'],
            'page_no': 1,
            'page_count': 100,
        })
        if data.get('status') != '000' or not data.get('list'):
            return
        for report in data['list']:
            report_nm, rcept_no = report.get('report_nm', 'N/A'), report.get('rcept_no')
            if any(k in report_nm for k in ['사업보고서', '분기보고서', '반기보고서']):
                doc_content = _dart_get_raw(DART_DOCUMENT_URL, {'rcept_no': rcept_no})
                file_name = f"{company_name}_{report_nm.replace(' ', '_')}_{report.get('rcept_dt')}.zip"
                with open(os.path.join(REPORTS_DIR, file_name), 'wb') as f:
                    f.write(doc_content)
                print(f" -> 성공: '{file_name}' 저장 완료.")
    except Exception as e:
        print(f"보고서 다운로드 중 오류 발생: {type(e).__name__}")


# ── 공시 목록 조회 ───────────────────────────────────────────────────────────

def fetch_filing_list(corp_code: str, bgn_de: str, *, strict: bool = False) -> list[dict]:
    """특정 날짜 이후의 공시 목록을 반환합니다."""
    try:
        data = _dart_get(DART_LIST_URL, {
            'corp_code': corp_code,
            'bgn_de': bgn_de,
            'sort': 'date',
            'sort_mth': 'desc',
            'page_count': 10,
        })
        if data.get('status') != '000':
            if strict and data.get('status') != '013':
                raise HTTPException(502, 'DART 공시 목록 조회에 실패했습니다.')
            return []
        return data.get('list', [])
    except Exception as e:
        if strict:
            raise HTTPException(502, 'DART 공시 목록 조회에 실패했습니다.') from None
        print('[DART] 공시 목록 조회 실패')
        return []


# ── 내부자 거래 조회 ─────────────────────────────────────────────────────────

def fetch_insider_trading(corp_code: str, year: str) -> dict:
    """임원/주요주주 소유주식 현황 및 최근 신고 내역을 반환합니다."""
    # 1. 사업보고서 기준 보유 현황 (elestock)
    holdings = []
    for reprt_code in ['11011', '11014', '11012', '11013']:
        try:
            data = _dart_get(DART_ELESTOCK_URL, {
                'corp_code': corp_code,
                'bsns_year': year,
                'reprt_code': reprt_code,
            })
            if data.get('status') == '000' and data.get('list'):
                for item in data['list']:
                    change = _parse_int(item.get('sp_stock_lmp_irds_cnt', '0'))
                    shares = _parse_int(item.get('sp_stock_lmp_cnt', '0'))
                    if shares == 0 and change == 0:
                        continue
                    holdings.append({
                        'name': item.get('repror', ''),
                        'role': item.get('isu_exctv_ofcps', ''),
                        'is_registered': item.get('isu_exctv_rgist_at', '') == '등기임원',
                        'is_major_shareholder': item.get('isu_main_shrholdr', '-') != '-',
                        'shares': shares,
                        'change': change,
                        'rate': item.get('sp_stock_lmp_rate', '0'),
                        'rcept_dt': item.get('rcept_dt', ''),
                    })
                break
        except Exception as e:
            print(f"[DART] elestock 조회 오류 ({reprt_code}): {type(e).__name__}")

    # 2. 최근 3개월 내부자 신고 공시 목록 (D002)
    recent_filings = []
    bgn_de = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    try:
        list_data = _dart_get(DART_LIST_URL, {
            'corp_code': corp_code,
            'pblntf_detail_ty': 'D002',
            'bgn_de': bgn_de,
            'sort': 'date',
            'sort_mth': 'desc',
            'page_count': 20,
        })
        if list_data.get('status') == '000':
            for item in list_data.get('list', []):
                report_nm = item.get('report_nm', '')
                if '[기재정정]' in report_nm:
                    continue
                recent_filings.append({
                    'rcept_dt': item.get('rcept_dt', ''),
                    'report_nm': report_nm,
                    'filer': item.get('flr_nm', ''),
                    'rcept_no': item.get('rcept_no', ''),
                })
    except Exception as e:
        print(f"[DART] 내부자 공시 목록 조회 오류: {type(e).__name__}")

    return {
        'holdings': holdings,
        'recent_filings': recent_filings,
        'year': year,
    }
