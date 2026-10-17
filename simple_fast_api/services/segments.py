"""사업보고서 연결 영업부문 표에서 손익과 비중을 검증·계산합니다."""
import asyncio
import io
import re
import warnings
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from fastapi import HTTPException

from cache import segment_cache
from config import (DART_LIST_URL, DART_DOCUMENT_URL, DART_VIEWER_URL, YEAR_RANGE,
                    SEGMENT_PARSER_VERSION, SEGMENT_DOCUMENT_TIMEOUT, SEGMENT_CONTEXT_CHARS,
                    SEGMENT_MAX_TABLE_ROWS, SEGMENT_MAX_TABLE_COLUMNS,
                    SEGMENT_UNIT_MULTIPLIERS, SEGMENT_TOTAL_LABELS)
from services.dart import _dart_get, _dart_get_raw
from utils import fmt_krw


def _compact(text: str) -> str:
    return re.sub(r'\s+', '', text)


def _amount(text: str, scale: int) -> int | None:
    value = _compact(text).replace(',', '').replace('−', '-').replace('△', '-')
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
        return None
    try:
        number = Decimal(value) * scale
        return int(number) if number == number.to_integral_value() else None
    except InvalidOperation:
        return None


def _grid(table) -> list[list[str]]:
    cells, rows = {}, []
    source = [r for r in table.find_all('tr') if r.find_parent('table') is table]
    if len(source) > SEGMENT_MAX_TABLE_ROWS:
        return []
    for r, row in enumerate(source):
        c = 0
        for cell in row.find_all(['td', 'th', 'te'], recursive=False):
            while (r, c) in cells:
                c += 1
            try:
                rs, cs = int(cell.get('rowspan', 1)), int(cell.get('colspan', 1))
            except (ValueError, TypeError):
                return []
            if not 1 <= rs <= SEGMENT_MAX_TABLE_ROWS or not 1 <= cs <= SEGMENT_MAX_TABLE_COLUMNS or c + cs > SEGMENT_MAX_TABLE_COLUMNS:
                return []
            for dr in range(rs):
                for dc in range(cs):
                    cells[r + dr, c + dc] = cell.get_text(' ', strip=True)
            c += cs
        width = max((col + 1 for rr, col in cells if rr == r), default=0)
        rows.append([cells.get((r, col), '') for col in range(width)])
    return rows


def _context(table) -> str:
    parts = []
    for sibling in table.previous_siblings:
        if getattr(sibling, 'name', None) == 'table':
            text = sibling.get_text(' ', strip=True)
            if len(text) > 150:
                continue
        else:
            text = sibling.get_text(' ', strip=True) if hasattr(sibling, 'get_text') else str(sibling).strip()
        if text:
            parts.append(text)
        if sum(map(len, parts)) >= SEGMENT_CONTEXT_CHARS:
            break
    # 가까운 문구부터 보존해 전기 표를 앞의 당기 표로 오인하지 않습니다.
    return ' '.join(parts)[:SEGMENT_CONTEXT_CHARS]


def _matrix(table, scale: int) -> dict | None:
    rows = _grid(table)
    profit_idx = next((i for i, r in enumerate(rows) if r and
        _compact(r[0]) in ('영업이익', '영업이익(손실)', '영업손익', '부문영업이익', '부문손익')), None)
    if profit_idx is None:
        return None
    profit = rows[profit_idx]
    width = len(profit)
    headers = rows[:profit_idx]
    total_cols = [c for c in range(1, width) if any(
        c < len(r) and _compact(r[c]) in SEGMENT_TOTAL_LABELS + ('부문합계',)
        for r in headers)]
    if not total_cols:
        return None
    total_col = total_cols[-1]
    # 두 개 이상의 중간 합계가 있으면 이중 합산 위험이 있어 지원하지 않습니다.
    if len(total_cols) > 1 or total_col != width - 1:
        return None
    total = _amount(profit[total_col], scale)
    if total is None:
        return None
    aliases = next((r for r in headers if r and '보고부문' in _compact(r[0]) and any(w in r[0] for w in ('명칭', '약칭'))), None)
    head_count = len(table.find('thead').find_all('tr')) if table.find('thead') else 1
    names = []
    for c in range(1, total_col):
        name = aliases[c] if aliases and c < len(aliases) else ''
        if not name:
            candidates = [r[c] for r in rows[:head_count] if c < len(r) and r[c].strip()]
            name = candidates[-1] if candidates else ''
        if not name or len(name) > 90 or name in names or _amount(name, 1) is not None:
            return None
        names.append(name)
    values = [_amount(profit[c], scale) for c in range(1, total_col)]
    if len(names) < 2 or any(v is None for v in values):
        return None
    tolerance = scale * (len(values) + 1) // 2
    if abs(sum(values) - total) > tolerance:
        return None
    revenue = next((r for r in rows if r and _compact(r[0]) in ('매출액', '외부고객매출액', '외부매출액')), None)
    rev_values = [_amount(revenue[c], scale) for c in range(1, total_col)] if revenue and len(revenue) == width else []
    rev_total = _amount(revenue[total_col], scale) if revenue and len(revenue) == width else None
    if not rev_values or any(v is None for v in rev_values) or rev_total is None or abs(sum(rev_values) - rev_total) > tolerance:
        rev_values, rev_total = [], None
    segments = []
    for i, (name, value) in enumerate(zip(names, values)):
        segments.append({'name': name, 'operating_income': value,
            'operating_income_share': round(value / total * 100, 2) if total > 0 else None,
            'revenue': rev_values[i] if rev_values else None,
            'revenue_share': round(rev_values[i] / rev_total * 100, 2) if rev_values and rev_total and rev_total > 0 else None,
            'is_adjustment': any(word in name for word in ('조정', '제거'))})
    return {'segments': segments, 'total_operating_income': total, 'total_revenue': rev_total,
            'rounding_difference': total - sum(values), 'source_unit_krw': scale}


def _parse_segment_candidates(document: bytes, fiscal_year: int) -> list[dict]:
    """연결·당기/전기·금액단위와 합계를 확인한 부문 표만 추출합니다."""
    text = None
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            text = document.decode(encoding)
            break
        except UnicodeError:
            continue
    if text is None:
        return []
    # DART의 비정형 XML은 XML 파서가 중간에 잘라낼 수 있어 관대한 HTML 파서를 사용합니다.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(text, 'lxml')
    periods = {}
    for index, table in enumerate(soup.find_all('table')):
        content = table.get_text(' ', strip=True)
        if '영업이익' not in content and '영업손익' not in content:
            continue
        context = _context(table)
        basis = re.search(r'연결|별도|개별', context)
        if basis is None or basis.group() != '연결' or not re.search(r'(?:부문|세그먼트).{0,30}연결|연결.{0,30}(?:부문|세그먼트)', context):
            continue
        period = re.search(r'전전기|전기|당기', context)
        unit = re.search(r'단위\s*[:：]\s*([^\s,)]+)', context)
        if period is None or unit is None or unit.group(1) not in SEGMENT_UNIT_MULTIPLIERS:
            continue
        year = fiscal_year - {'당기': 0, '전기': 1, '전전기': 2}[period.group()]
        parsed = _matrix(table, SEGMENT_UNIT_MULTIPLIERS[unit.group(1)])
        if parsed is None:
            continue
        parsed.update(year=year, fs_div='CFS', table_index=index)
        if year in periods and periods[year]['segments'] != parsed['segments']:
            # 서로 다른 표가 같은 기간을 주장하면 어느 쪽도 자동 선택하지 않습니다.
            periods[year]['ambiguous'] = True
        else:
            periods.setdefault(year, parsed)
    return list(periods.values())


def parse_segment_document(document: bytes, fiscal_year: int) -> list[dict]:
    """연결·기간·단위·합계가 검증되고 서로 상충하지 않는 부문 표를 반환합니다."""
    return [p for p in _parse_segment_candidates(document, fiscal_year) if not p.get('ambiguous')]


def fetch_segment_report(corp_code: str) -> dict:
    """최신 정정 사업보고서의 연결 영업부문 표와 원문 출처를 수집합니다."""
    now = datetime.now()
    listing = _dart_get(DART_LIST_URL, {'corp_code': corp_code, 'pblntf_detail_ty': 'A001',
        'last_reprt_at': 'Y', 'bgn_de': f'{now.year - YEAR_RANGE}0101',
        'end_de': now.strftime('%Y%m%d'), 'sort': 'date', 'sort_mth': 'desc', 'page_count': 100})
    if listing.get('status') not in ('000', '013'):
        raise HTTPException(502, 'DART 사업보고서 목록을 조회하지 못했습니다.')
    reports = []
    for row in listing.get('list', []):
        match = re.search(r'사업보고서\s*\((\d{4})\.(\d{2})\)', row.get('report_nm', ''))
        if match:
            reports.append((int(match[1]), int(match[2]), row))
    if not reports:
        raise HTTPException(404, '사업부별 손익을 조회할 사업보고서가 없습니다.')
    year, month, report = max(reports, key=lambda r: (r[0], r[1], r[2].get('rcept_dt', '')))
    receipt = report['rcept_no']
    archive = _dart_get_raw(DART_DOCUMENT_URL, {'rcept_no': receipt}, timeout=SEGMENT_DOCUMENT_TIMEOUT)
    periods = []
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        for name in bundle.namelist():
            if name.lower().endswith(('.xml', '.html', '.htm')) and not name.startswith('__'):
                periods.extend(_parse_segment_candidates(bundle.read(name), year))
    # ZIP에 본문·첨부가 따로 있어도 같은 기간의 상충 배분표를 자동 선택하지 않습니다.
    grouped = {}
    for period in periods:
        grouped.setdefault(period['year'], []).append(period)
    periods = [group[0] for group in grouped.values() if all(
        not p.get('ambiguous') and p['segments'] == group[0]['segments'] and p['total_operating_income'] == group[0]['total_operating_income']
        for p in group)]
    if not periods:
        raise HTTPException(404, '연결 기준·기간·단위·합계가 확인되는 사업부별 손익 표를 찾지 못했습니다. 수치를 추정하지 않습니다.')
    return {'periods': periods, 'fiscal_year': year, 'fiscal_month': month,
        'parser_version': SEGMENT_PARSER_VERSION, 'report_name': report['report_nm'],
        'provenance': {'source': DART_VIEWER_URL + receipt, 'receipt_no': receipt,
            'filed_at': report.get('rcept_dt'), 'retrieved_at': datetime.now(timezone.utc).isoformat()}}


async def segment_data(company: str, corp_code: str, year: int | None = None) -> tuple[dict, bool]:
    """원문과 연간 연결 영업이익이 일치하는 사업부별 비중을 캐시합니다."""
    async def load() -> dict:
        from services.company_data import annual_data
        try:
            report = await asyncio.to_thread(fetch_segment_report, corp_code)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, 'DART 사업부별 손익 원문을 가져오거나 해석하지 못했습니다.') from None
        annual, _ = await annual_data(company, corp_code, 'financials')
        verified = []
        for period in report['periods']:
            row = next((r for r in annual['financials'] if r['year'] == period['year'] and r.get('fs_div') == 'CFS'), None)
            if row is None or row.get('operating_income') is None:
                continue
            tolerance = period['source_unit_krw'] * (len(period['segments']) + 1)
            if abs(row['operating_income'] - period['total_operating_income']) <= tolerance:
                if period['total_revenue'] is None or row.get('revenue') is None or abs(row['revenue'] - period['total_revenue']) > tolerance:
                    period['total_revenue'] = None
                    for segment in period['segments']:
                        segment['revenue'], segment['revenue_share'] = None, None
                verified.append(period)
        if not verified:
            raise HTTPException(404, '사업부별 손익 합계가 연결 재무제표와 일치하지 않아 비중을 제공하지 않습니다.')
        return {**report, 'periods': verified, 'company_name': company}
    # 파서 버전이 바뀌면 기존 결과를 재검증합니다.
    current = await segment_cache.get(company)
    if current and current.get('parser_version') != SEGMENT_PARSER_VERSION:
        await segment_cache.clear(company)
    report, cached = await segment_cache.get_or_create(company, load)
    wanted = year if year is not None else report['fiscal_year']
    selected = next((r for r in report['periods'] if r['year'] == wanted), None)
    if selected is None:
        raise HTTPException(404, f'{wanted}년 연결 사업부별 손익 표를 검증하지 못했습니다. 확인된 연도: {sorted(r["year"] for r in report["periods"])}')
    return {**report, **selected, 'periods': None}, cached


def is_segment_question(message: str, history: list[dict] | None = None) -> bool:
    """사업부별 손익 질문과 직전 상담을 잇는 연도·비중 질문을 식별합니다."""
    text = _compact(message)
    topic = bool(re.search(r'사업(?:영역|부|부문|별)|부문별|영업부문', text))
    metric = bool(re.search(r'영업이익|영업손익|이익|매출|비중|기여', text))
    if topic and metric:
        return True
    previous = _compact(' '.join(str(r.get('text', '')) for r in (history or [])[-4:]))
    return bool(re.search(r'사업(?:영역|부|부문|별)|부문별|영업부문', previous) and
                re.fullmatch(r'(?:그럼|그러면|그중|전년|재작년|작년|올해|금년|\d{4}년?|[1-4]분기|상반기|하반기|반기|[Qq][1-4]|[1-4][Qq]|비중|매출|영업이익|의미|분석|해석|설명|왜|이유|원인|100%|넘어|넘나요|이|의|를|해줘|가|도|은|는|\s|[?.!]|알려줘|보여줘)+', message))


def resolve_segment_request(message: str, history: list[dict], latest_year: int | None) -> tuple[int | None, bool]:
    """상대 연도를 달력·직전 기준연도로 구분하고 후속 질문의 지표를 유지합니다."""
    previous_year, previous_revenue = latest_year, False
    for item in reversed(history):
        match = re.search(r'(\d{4})년\s*사업부별\s*(매출|영업이익)', str(item.get('text', '')))
        if match and item.get('role') == 'model':
            previous_year, previous_revenue = int(match[1]), match[2] == '매출'
            break
    explicit = re.search(r'((?:19|20)\d{2})\s*년?', message)
    year = int(explicit[1]) if explicit else latest_year if any(w in message for w in ('최신', '최근')) else previous_year
    if not explicit:
        if '재작년' in message:
            year = datetime.now().year - 2
        elif '작년' in message:
            year = datetime.now().year - 1
        elif '올해' in message or '금년' in message:
            year = datetime.now().year
        elif '전년' in message and previous_year is not None:
            year = previous_year - 1
    revenue = True if '매출' in message and '이익' not in message else False if '이익' in message else previous_revenue
    return year, revenue


def format_segment_answer(data: dict, revenue: bool = False) -> str:
    """검증한 금액·분모·음수 비중과 공시 기준을 한국어로 표시합니다."""
    metric = 'revenue' if revenue else 'operating_income'
    label = '매출' if revenue else '영업이익'
    total = data['total_revenue'] if revenue else data['total_operating_income']
    if total is None:
        return '사업부별 매출은 합계를 검증하지 못해 비중을 제공하지 않습니다.'
    lines = [f"{data['company_name']} {data['year']}년 사업부별 {label} (연간·연결 기준)",
             f'분모: 공시된 연결 {label} 합계 {fmt_krw(total)} ({total:,}원)']
    for row in data['segments']:
        share = row[metric + '_share']
        shown = f'{share:.2f}%' if share is not None else '산출하지 않음'
        lines.append(f"• {row['name']}: {fmt_krw(row[metric])} / {shown}")
    if total <= 0:
        lines.append('합계가 0 또는 음수여서 기여 비중을 산출하지 않았습니다.')
    else:
        lines.append('비중 = 사업부 금액 ÷ 위 합계 × 100. 적자는 음수로 표시하며 흑자 부문의 합은 100%를 넘을 수 있습니다.')
    lines.append('금액 표시는 조·억 단위로 반올림하며, 비중은 원문 금액으로 계산합니다. 기타·연결조정은 표에 기재된 항목 그대로 포함합니다. 반올림으로 비중 합계는 100%와 다를 수 있습니다.')
    lines.extend([f"출처: {data['report_name']} / 결산 {data['fiscal_year']}.{data['fiscal_month']:02d}",
                  f"공시일: {data['provenance']['filed_at']} / 조회시각: {data['provenance']['retrieved_at']}",
                  data['provenance']['source']])
    return '\n'.join(lines)


def explain_segment_contribution(data: dict, revenue: bool = False) -> str:
    """모델의 재계산 없이 양수·음수 항목과 기여 비중의 의미를 설명합니다."""
    metric = 'revenue' if revenue else 'operating_income'
    total = data['total_revenue'] if revenue else data['total_operating_income']
    if total is None or total <= 0:
        return '검증된 양수 합계가 없어 비중의 크기로 기여도를 비교하지 않습니다.'
    positive = [r for r in data['segments'] if r[metric] is not None and r[metric] > 0]
    negative = [r for r in data['segments'] if r[metric] is not None and r[metric] < 0]
    lines = []
    if positive:
        top = max(positive, key=lambda r: r[metric])
        lines.append(f"공시 표에서 가장 큰 양수 기여 항목은 {top['name']}({top[metric + '_share']:.2f}%)입니다.")
    if negative:
        ratio = sum(r[metric] for r in positive) / total * 100
        lines.append(f"음수 항목 {len(negative)}개가 합계를 줄이므로 양수 항목의 비중 합은 {ratio:.2f}%로 100%를 넘습니다. 각 항목을 모두 더한 순합계가 분모입니다.")
    lines.append('비중은 전체 금액에 대한 기여도이며, 사업부 자체의 영업이익률과 다릅니다. 손익 변동 원인·경쟁력·전망은 이 표만으로 확인할 수 없습니다.')
    return '\n'.join(lines)
