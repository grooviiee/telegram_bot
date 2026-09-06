"""공통 기업 데이터 수집과 출처 관리. 조회 순서와 무관한 분석 입력을 제공합니다."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException

from cache import financials_cache, dividend_cache, business_cache, valuation_cache, filings_cache
from config import (YEAR_RANGE, DART_FINANCIALS_URL, DART_DIVIDEND_URL,
                    DART_LIST_URL, DART_DOCUMENT_URL, ANALYSIS_POLICY_VERSION)
from services.dart import (fetch_dart_financials, fetch_dividend_per_share,
                           fetch_business_overview, fetch_filing_list, resolve_corp_code)
from services.valuation import fetch_valuation


def provenance(source: str, years: list[int] | None = None) -> dict:
    """출처와 조회시각, 재무 기준연도를 분리하여 반환합니다."""
    return {'source': source, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'fiscal_years': years or []}


async def annual_data(company: str, corp_code: str, kind: str) -> tuple[dict, bool]:
    """6개년 후보에서 유효한 최근 5개년을 수집하고 중복 요청을 합칩니다."""
    is_fin = kind == 'financials'
    cache = financials_cache if is_fin else dividend_cache
    key = 'financials' if is_fin else 'dividend_data'
    fetcher = fetch_dart_financials if is_fin else fetch_dividend_per_share

    async def load() -> dict:
        years = list(range(datetime.now().year - 1, datetime.now().year - YEAR_RANGE - 2, -1))
        results = await asyncio.gather(
            *[asyncio.to_thread(fetcher, corp_code, str(y)) for y in years],
            return_exceptions=True,
        )
        rows = []
        missing = []
        for year, value in zip(years, results):
            if isinstance(value, Exception) or value is None:
                missing.append(year)
            elif is_fin:
                rows.append(value)
            else:
                rows.append({'year': year, 'dividend': value})
        rows = sorted(rows[:YEAR_RANGE], key=lambda r: r['year'])
        if not rows:
            raise HTTPException(404, f"'{company}'의 {kind} 데이터를 찾을 수 없습니다.")
        meta = provenance(DART_FINANCIALS_URL if is_fin else DART_DIVIDEND_URL, [r['year'] for r in rows])
        meta['unavailable_years'] = missing
        if not is_fin:
            meta['source'] = [DART_FINANCIALS_URL, DART_DIVIDEND_URL]
        return {'company_name': company, key: rows, 'provenance': meta}

    return await cache.get_or_create(company, load)


async def valuation_data(company: str, corp_code: str | None = None,
                         financials: list[dict] | None = None) -> tuple[dict, bool]:
    """공통 재무 스냅샷과 시세 TTL로 밸류에이션의 입력 일관성을 보장합니다."""
    if financials is None:
        corp_code = corp_code or await resolve_corp_code(company)
        annual, _ = await annual_data(company, corp_code, 'financials')
        financials = annual['financials']
    fingerprint = input_fingerprint({'financials': financials})
    async with valuation_cache.lock(company):
        cached = await valuation_cache.get(company)
        if cached and cached.get('financials_fingerprint') == fingerprint:
            return cached, True
        result = await asyncio.to_thread(fetch_valuation, company, financials)
        result['provenance'] = provenance('yfinance + DART', [result['latest_year']])
        result['financials_fingerprint'] = fingerprint
        await valuation_cache.set(company, result)
        return result, False


async def business_data(company: str, corp_code: str) -> tuple[dict, bool]:
    """사업 내용을 캐시하고 수집 출처를 기록합니다."""
    async def load() -> dict:
        result = await asyncio.to_thread(fetch_business_overview, corp_code, company)
        result['provenance'] = provenance(DART_DOCUMENT_URL)
        return result
    return await business_cache.get_or_create(company, load)


async def recent_filings(company: str, corp_code: str) -> tuple[dict, bool]:
    """공시 목록을 단기 캐시로 재사용합니다."""
    async def load() -> dict:
        rows = await asyncio.to_thread(fetch_filing_list, corp_code, f'{datetime.now().year - 1}0101', strict=True)
        return {'filings': rows or [], 'provenance': provenance(DART_LIST_URL)}
    return await filings_cache.get_or_create(company, load)


async def gather_company_data(corp_code: str, company: str, *, narrative: bool = True) -> dict:
    """점수·리포트·챗에서 동일한 재무·배당·시세 입력과 누락 정보를 사용합니다."""
    annual = await annual_data(company, corp_code, 'financials')
    tasks = {
        'dividends': annual_data(company, corp_code, 'dividends'),
        'valuation': valuation_data(company, corp_code, annual[0]['financials']),
    }
    if narrative:
        tasks.update(business=business_data(company, corp_code), filings=recent_filings(company, corp_code))
    values = await asyncio.gather(*tasks.values(), return_exceptions=True)
    available = {k: v[0] for k, v in zip(tasks, values) if not isinstance(v, Exception)}
    available['financials'] = annual[0]
    warnings = [f'{k}: 데이터 조회 불가 (0 또는 무배당을 의미하지 않음)' for k in tasks if k not in available]
    for k, v in available.items():
        if v.get('provenance', {}).get('unavailable_years'):
            warnings.append(f"{k}: 일부 연도 누락 {v['provenance']['unavailable_years']}")
    financials = available['financials']['financials']
    if financials[-1].get('fcf') is None:
        warnings.append('FCF 데이터 부족: 영업현금흐름이나 순이익으로 대체하지 않습니다.')
    valuation = available.get('valuation')
    if valuation and valuation.get('ev_ebit') is None:
        warnings.append('EV/EBIT 계산에 필요한 데이터 부족 또는 영업이익 비양수: 평가하지 않습니다.')
    if len({f.get('fs_div') for f in financials}) > 1:
        warnings.append('연결·개별 재무제표가 혼재하여 연도 간 비교에 주의가 필요합니다.')
    return {
        'financials': financials,
        'dividends': available.get('dividends', {}).get('dividend_data', []),
        'valuation': available.get('valuation'),
        'business_sections': available.get('business', {}).get('sections', []),
        'recent_filings': available.get('filings', {}).get('filings', []),
        'data_quality': {'warnings': warnings, 'sources': {k: v.get('provenance') for k, v in available.items()}},
    }


def input_fingerprint(data: dict) -> str:
    """조회시각을 제외한 실제 입력과 분석 정책 버전의 해시를 계산합니다."""
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k not in ('retrieved_at', 'cached')}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    payload = json.dumps([ANALYSIS_POLICY_VERSION, clean(data)], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
