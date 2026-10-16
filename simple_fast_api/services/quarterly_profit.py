"""텔레그램 수익성 그래프용 단일 분기 실적을 수집합니다."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from cache import quarterly_profit_cache
from config import (DART_FINANCIALS_URL, FS_DIV_ORDER, QUARTER_REPRT_CODE,
                    PROFIT_CHART_QUARTERS, PROFIT_LOOKBACK_YEARS,
                    PROFIT_FETCH_CONCURRENCY, TRENDING_TIMEZONE)
from services.dart import _dart_get, parse_dart_amount


def fetch_profit_period(corp_code: str, year: int, quarter: int) -> dict | None:
    """손익계산서의 3개월 금액과 누적 금액을 연결 우선으로 조회합니다."""
    names = {
        'revenue': ('매출액', '수익(매출액)', '영업수익', '순매출액'),
        'operating_income': ('영업이익', '영업이익(손실)'),
    }
    for fs_div in FS_DIV_ORDER:
        data = _dart_get(DART_FINANCIALS_URL, {
            'corp_code': corp_code, 'bsns_year': str(year),
            'reprt_code': QUARTER_REPRT_CODE[f'Q{quarter}'], 'fs_div': fs_div,
        })
        if data.get('status') == '013':
            continue
        if data.get('status') != '000':
            raise RuntimeError('DART 재무 조회 실패')
        accounts = {row['account_nm']: row for row in data.get('list', [])
                    if row.get('sj_div') in ('IS', 'CIS')}
        if not accounts:
            continue
        result = {'year': year, 'quarter': quarter, 'fs_div': fs_div}
        for key, aliases in names.items():
            account = next((accounts[name] for name in aliases if name in accounts), {})
            amount = parse_dart_amount(account.get('thstrm_amount', ''))
            cumulative = parse_dart_amount(account.get('thstrm_add_amount', ''))
            result[key] = amount
            result[f'{key}_cumulative'] = amount if quarter in (1, 4) else cumulative
        if any(result[key] is not None for key in names):
            return result
    return None


def build_profit_series(periods: list[dict]) -> list[dict]:
    """4분기를 분리하고 누락 분기를 유지한 최근 12분기 시계열을 만듭니다."""
    indexed = {(r['year'], r['quarter']): r for r in periods}
    converted = {}
    for (year, quarter), raw in indexed.items():
        row = dict(raw)
        if quarter == 4:
            previous = indexed.get((year, 3), {})
            for key in ('revenue', 'operating_income'):
                annual, cumulative = raw.get(key), previous.get(f'{key}_cumulative')
                row[key] = (annual - cumulative if annual is not None and cumulative is not None
                            and raw['fs_div'] == previous.get('fs_div') else None)
        revenue, income = row.get('revenue'), row.get('operating_income')
        row['operating_margin'] = round(income / revenue * 100, 2) if revenue and income is not None else None
        converted[(year, quarter)] = row
    if not converted:
        return []
    latest = max(y * 4 + q - 1 for y, q in converted)
    rows = []
    for index in range(latest - PROFIT_CHART_QUARTERS + 1, latest + 1):
        year, zero_quarter = divmod(index, 4)
        quarter = zero_quarter + 1
        row = dict(converted.get((year, quarter), {'year': year, 'quarter': quarter}))
        previous = converted.get((year - 1, quarter), {})
        revenue, old = row.get('revenue'), previous.get('revenue')
        row['revenue_yoy'] = (round((revenue / old - 1) * 100, 2)
                              if revenue is not None and old is not None and old > 0
                              and row.get('fs_div') == previous.get('fs_div') else None)
        row['label'] = f'{year} Q{quarter}'
        rows.append(row)
    return rows


async def quarterly_profit_data(company: str, corp_code: str) -> tuple[dict, bool]:
    """최근 분기 수익성 실적을 수집하고 회사명 단위로 캐싱합니다."""
    async def load() -> dict:
        now = datetime.now(ZoneInfo(TRENDING_TIMEZONE))
        current_quarter = (now.month - 1) // 3 + 1
        targets = [(year, quarter) for year in range(now.year - PROFIT_LOOKBACK_YEARS, now.year + 1)
                   for quarter in range(1, 5) if (year, quarter) < (now.year, current_quarter)]
        semaphore = asyncio.Semaphore(PROFIT_FETCH_CONCURRENCY)

        async def fetch(year: int, quarter: int) -> dict | None:
            async with semaphore:
                return await asyncio.to_thread(fetch_profit_period, corp_code, year, quarter)

        values = await asyncio.gather(*(fetch(y, q) for y, q in targets), return_exceptions=True)
        if any(isinstance(value, Exception) for value in values):
            # 인증·통신 실패를 공시 부재로 간주하거나 부분 결과로 캐싱하지 않습니다.
            raise HTTPException(502, 'DART 분기 실적 조회에 실패했습니다. 잠시 후 다시 시도해주세요.')
        rows = build_profit_series([value for value in values if value is not None])
        if not any(row.get('revenue') is not None or row.get('operating_income') is not None for row in rows):
            raise HTTPException(404, f"'{company}'의 분기 실적을 찾을 수 없습니다.")
        return {'company_name': company, 'financials': rows, 'period': 'quarterly',
                'source': DART_FINANCIALS_URL, 'collected_at': now.isoformat()}

    return await quarterly_profit_cache.get_or_create(company, load)
