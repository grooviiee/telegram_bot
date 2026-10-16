"""소유상황보고서 원문의 거래 사유를 확인하여 내부자 매매를 집계합니다."""
import asyncio
import io
import re
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from fastapi import HTTPException

from cache import insider_trend_cache, insider_document_cache
from config import (DART_LIST_URL, DART_DOCUMENT_URL, DART_VIEWER_URL,
                    INSIDER_TREND_YEARS, INSIDER_FETCH_CONCURRENCY,
                    INSIDER_FILING_TYPE, INSIDER_TRADE_REASONS, TRENDING_TIMEZONE,
                    INSIDER_NON_TRADE_REASONS, INSIDER_REQUESTS_PER_SECOND,
                    INSIDER_FAILURE_THRESHOLD, INSIDER_PARTIAL_RETRY_SECONDS,
                    INSIDER_PARSER_VERSION)
from services.dart import _dart_get, _dart_get_raw, parse_dart_amount

_document_slots = asyncio.Semaphore(INSIDER_FETCH_CONCURRENCY)
_rate_lock = asyncio.Lock()
_last_request = 0.0


async def _wait_document_slot() -> None:
    """기업을 통틀어 원문 API 호출 빈도를 제한합니다."""
    global _last_request
    async with _rate_lock:
        loop = asyncio.get_running_loop()
        delay = 1 / INSIDER_REQUESTS_PER_SECOND - (loop.time() - _last_request)
        if delay > 0:
            await asyncio.sleep(delay)
        _last_request = loop.time()


def fetch_insider_filings(corp_code: str, start: date, end: date) -> list[dict]:
    """정정본을 반영한 최종 소유상황보고서 목록을 페이지 끝까지 수집합니다."""
    page, receipts = 1, {}
    while True:
        result = _dart_get(DART_LIST_URL, {
            'corp_code': corp_code, 'bgn_de': start.strftime('%Y%m%d'),
            'end_de': end.strftime('%Y%m%d'), 'pblntf_detail_ty': INSIDER_FILING_TYPE,
            'last_reprt_at': 'Y', 'page_no': page, 'page_count': 100,
            'sort': 'date', 'sort_mth': 'asc',
        }, timeout=30)
        if result.get('status') == '013':
            break
        if result.get('status') != '000':
            raise RuntimeError('DART 내부자 공시 목록 조회 실패')
        for row in result.get('list', []):
            if not re.fullmatch(r'\d{14}', row.get('rcept_no', '')):
                raise ValueError('공시 접수번호 누락')
            receipts[row['rcept_no']] = row
        if page >= int(result.get('total_page', 1)):
            break
        page += 1
    return list(receipts.values())


def parse_insider_document(xml: bytes) -> dict:
    """표준 원문 필드의 거래 사유·변동일·주식수로 실제 매수·매도를 분리합니다."""
    soup = BeautifulSoup(xml, 'xml')
    reasons = soup.find_all(attrs={'AUNIT': 'RPT_RSN'})
    if not reasons:
        raise ValueError('지원하지 않는 내부자 공시 양식')
    trades, excluded, invalid = [], 0, 0
    for node in reasons:
        row = node.find_parent('TR')
        if row is None:
            invalid += 1
            continue
        reason = re.sub(r'[\s()+\-]', '', node.get_text())
        side = INSIDER_TRADE_REASONS.get(reason)
        if side is None:
            if any(excluded_reason in reason for excluded_reason in INSIDER_NON_TRADE_REASONS):
                excluded += 1
            elif '매수' in reason or '매도' in reason:
                invalid += 1
            else:
                excluded += 1
            continue
        kind = row.find(attrs={'AUNIT': 'STR_KND'})
        # 전환사채·신주인수권 등 주식 이외 증권은 주식 수량에 합산하지 않습니다.
        security = re.sub(r'\s+', '', kind.get_text()) if kind else ''
        if security not in ('보통주', '우선주', '의결권있는주식', '의결권없는주식'):
            excluded += 1
            continue
        when = row.find(attrs={'AUNIT': 'MDF_DM'})
        amount = row.find(attrs={'ACODE': 'MDF_STK_CNT'})
        raw_date = (when.get('AUNITVALUE') or when.get_text()) if when else ''
        digits = re.sub(r'\D', '', raw_date)
        quantity = parse_dart_amount(amount.get_text()) if amount else None
        try:
            traded_on = datetime.strptime(digits, '%Y%m%d').date()
        except ValueError:
            invalid += 1
            continue
        if quantity is None or (side == 'buy' and quantity < 0) or (side == 'sell' and quantity > 0):
            invalid += 1
            continue
        trades.append({'date': traded_on.isoformat(), 'side': side, 'shares': abs(quantity),
                       'reason': node.get_text(strip=True), 'security': security})
    return {'trades': trades, 'excluded_rows': excluded, 'invalid_rows': invalid,
            'parser_version': INSIDER_PARSER_VERSION}


def fetch_insider_document(receipt: str) -> dict:
    """원문 ZIP의 본문 XML만 파싱하며 파일을 디스크에 풀지 않습니다."""
    content = _dart_get_raw(DART_DOCUMENT_URL, {'rcept_no': receipt}, timeout=30)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        # 본문 이름은 접수번호.xml이며 첨부 XML은 중복 집계하지 않습니다.
        names = [name for name in archive.namelist() if name.rsplit('/', 1)[-1] == f'{receipt}.xml']
        if not names:
            names = [name for name in archive.namelist() if name.lower().endswith('.xml')]
        if len(names) != 1:
            raise ValueError('공시 본문 XML을 식별할 수 없음')
        return parse_insider_document(archive.read(names[0]))


def aggregate_insider_trades(documents: list[dict], start: date, end: date,
                             complete: bool) -> tuple[list[dict], list[dict]]:
    """거래일 기준 월별·연별 주식 매매 수량을 집계합니다."""
    months = {}
    for year in range(start.year, end.year + 1):
        for month in range(1, 13):
            key = f'{year:04d}-{month:02d}'
            if start.strftime('%Y-%m') <= key <= end.strftime('%Y-%m'):
                months[key] = {'month': key, 'buy': 0, 'sell': 0}
    for document in documents:
        for trade in document['trades']:
            when = date.fromisoformat(trade['date'])
            if start <= when <= end:
                months[trade['date'][:7]][trade['side']] += trade['shares']
    annual = []
    for year in range(start.year, end.year + 1):
        entries = [row for key, row in months.items() if key.startswith(str(year))]
        annual.append({'year': year, 'buy': sum(r['buy'] for r in entries),
                       'sell': sum(r['sell'] for r in entries), 'partial_year': year == end.year})
    if not complete:
        # 확인되지 않은 거래를 0으로 표현하지 않습니다. 양수도 확인된 수량의 하한입니다.
        for row in [*months.values(), *annual]:
            for side in ('buy', 'sell'):
                if row[side] == 0:
                    row[side] = None
    return list(months.values()), annual


async def insider_trend_data(company: str, corp_code: str) -> tuple[dict, bool]:
    """올해 포함 3개년의 확인된 내부자 주식 매매와 수집 범위를 반환합니다."""
    async with insider_trend_cache.lock(company):
        today = datetime.now(ZoneInfo(TRENDING_TIMEZONE)).date()
        cached = await insider_trend_cache.get(company)
        if cached is not None and cached.get('end_date') == today.isoformat():
            collected = datetime.fromisoformat(cached['collected_at'])
            age = (datetime.now(ZoneInfo(TRENDING_TIMEZONE)) - collected).total_seconds()
            if cached['coverage_complete'] or age < INSIDER_PARTIAL_RETRY_SECONDS:
                return cached, True
        start = date(today.year - INSIDER_TREND_YEARS + 1, 1, 1)
        try:
            filings = await asyncio.to_thread(fetch_insider_filings, corp_code, start, today)
        except Exception:
            if cached is not None:
                return {**cached, 'refresh_failed': True}, True
            raise HTTPException(502, 'DART 내부자 공시 목록을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.') from None
        if not filings:
            raise HTTPException(404, f"'{company}'의 최근 3개년 내부자 신고가 없습니다.")
        consecutive_failures = 0

        async def fetch(filing: dict) -> dict:
            nonlocal consecutive_failures
            receipt = filing['rcept_no']
            async def load() -> dict:
                nonlocal consecutive_failures
                async with _document_slots:
                    if consecutive_failures >= INSIDER_FAILURE_THRESHOLD:
                        raise RuntimeError('원문 연속 오류로 수집 일시 중단')
                    await _wait_document_slot()
                    try:
                        result = await asyncio.to_thread(fetch_insider_document, receipt)
                        consecutive_failures = 0
                        return result
                    except Exception:
                        consecutive_failures += 1
                        raise
            result, _ = await insider_document_cache.get_or_create(f'{INSIDER_PARSER_VERSION}:{receipt}', load)
            return {**result, 'rcept_no': receipt}

        results = await asyncio.gather(*(fetch(f) for f in filings), return_exceptions=True)
        documents = [r for r in results if not isinstance(r, Exception)]
        failed = len(results) - len(documents)
        invalid = sum(r['invalid_rows'] for r in documents)
        complete = failed == 0 and invalid == 0
        if not documents:
            raise HTTPException(502, '내부자 공시 원문을 읽지 못했습니다. 잠시 후 다시 시도해주세요.')
        monthly, annual = aggregate_insider_trades(documents, start, today, complete)
        result = {
            'company_name': company, 'start_date': start.isoformat(), 'end_date': today.isoformat(),
            'monthly': monthly, 'annual': annual, 'coverage_complete': complete,
            'filings_total': len(filings), 'filings_parsed': len(documents), 'filings_failed': failed,
            'excluded_rows': sum(r['excluded_rows'] for r in documents), 'invalid_rows': invalid,
            'source': DART_DOCUMENT_URL, 'date_basis': 'transaction_date',
            'collected_at': datetime.now(ZoneInfo(TRENDING_TIMEZONE)).isoformat(),
            'recent_sources': [{'url': DART_VIEWER_URL + f['rcept_no'], 'receipt': f['rcept_no']}
                               for f in filings[-3:]],
        }
        # 부분 결과도 수집 범위를 보존하고 짧은 재시도 간격 후 실패한 원문만 재수집합니다.
        await insider_trend_cache.set(company, result)
        return result, False
