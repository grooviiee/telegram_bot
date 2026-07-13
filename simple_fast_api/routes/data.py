"""DART 데이터 조회 라우트 (배당, 재무, 사업개요, 밸류에이션)."""
import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import database
from cache import (
    dividend_cache, financials_cache, business_cache,
    quarterly_financials_cache, quarterly_dividend_cache, valuation_cache,
)
from services.dart import (
    get_corp_code, resolve_corp_code, fetch_dart_financials, fetch_dividend_per_share,
    fetch_dart_financials_q, fetch_dividend_per_share_q,
    fetch_business_overview, download_reports_logic,
)
from services.valuation import fetch_valuation

router = APIRouter()


class CompanyRequest(BaseModel):
    company_name: str


@router.post("/download-reports/", status_code=202)
async def trigger_download(request: CompanyRequest, background_tasks: BackgroundTasks):
    """보고서 다운로드 작업을 시작합니다."""
    corp_code = get_corp_code(request.company_name)
    background_tasks.add_task(download_reports_logic, request.company_name, corp_code)
    return {"message": f"'{request.company_name}'의 보고서 다운로드 작업이 시작되었습니다."}


@router.get("/dividend-data/{company_name}")
async def get_dividend_data(company_name: str):
    """최근 5년간 주당 현금배당금을 조회합니다."""
    await database.record_search(company_name)
    cached = await dividend_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    current_year = datetime.now().year
    candidate_years = [str(current_year - i) for i in range(1, 7)]

    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dividend_per_share, corp_code, year) for year in candidate_years],
        return_exceptions=True,
    )

    dividend_data = []
    for year, amount in zip(candidate_years, results):
        if isinstance(amount, Exception) or amount is None:
            continue
        dividend_data.append({'year': int(year), 'dividend': amount})
        if len(dividend_data) >= 5:
            break

    if not dividend_data:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 배당금 정보를 찾을 수 없습니다.")

    dividend_data.sort(key=lambda x: x['year'])
    result = {'company_name': company_name, 'dividend_data': dividend_data}
    await dividend_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/financials/{company_name}")
async def get_financials(company_name: str):
    """최근 5년간 수익성·성장성·재무건전성 지표를 조회합니다."""
    await database.record_search(company_name)
    cached = await financials_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    current_year = datetime.now().year
    candidate_years = [str(current_year - i) for i in range(1, 7)]

    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dart_financials, corp_code, year) for year in candidate_years],
        return_exceptions=True,
    )

    financials = [r for r in results if r and not isinstance(r, Exception)][:5]
    if not financials:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 재무 데이터를 찾을 수 없습니다.")

    financials.sort(key=lambda x: x['year'])
    result = {'company_name': company_name, 'financials': financials}
    await financials_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/business-overview/{company_name}")
async def get_business_overview(company_name: str):
    """최신 사업보고서의 '사업의 내용' 1~4항을 반환합니다."""
    await database.record_search(company_name)
    cached = await business_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    result = await asyncio.to_thread(fetch_business_overview, corp_code, company_name)

    await business_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/financials-quarterly/{company_name}")
async def get_financials_quarterly(company_name: str):
    """최근 5개년 분기별 재무 지표를 조회합니다."""
    await database.record_search(company_name)
    cached = await quarterly_financials_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    current_year = datetime.now().year
    targets = [
        (str(current_year - i), q)
        for i in range(5, 0, -1)
        for q in ['Q1', 'Q2', 'Q3', 'Q4']
    ]

    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dart_financials_q, corp_code, year, quarter)
          for year, quarter in targets],
        return_exceptions=True,
    )

    financials = [r for r in results if r is not None and not isinstance(r, Exception)]
    if not financials:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 분기 재무 데이터를 찾을 수 없습니다.")

    financials.sort(key=lambda x: (x['year'], x.get('quarter', 'Q4')))
    result = {'company_name': company_name, 'period': 'quarterly', 'financials': financials}
    await quarterly_financials_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/dividend-data-quarterly/{company_name}")
async def get_dividend_data_quarterly(company_name: str):
    """최근 5개년 분기별 배당금을 조회합니다."""
    await database.record_search(company_name)
    cached = await quarterly_dividend_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    current_year = datetime.now().year
    targets = [
        (str(current_year - i), q)
        for i in range(5, 0, -1)
        for q in ['Q1', 'Q2', 'Q3', 'Q4']
    ]

    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dividend_per_share_q, corp_code, year, quarter)
          for year, quarter in targets],
        return_exceptions=True,
    )

    dividend_data = []
    for (year, quarter), amount in zip(targets, results):
        if isinstance(amount, Exception) or amount is None or amount <= 0:
            continue
        dividend_data.append({
            'year': int(year), 'quarter': quarter,
            'label': year[-2:] + quarter, 'dividend': amount,
        })

    dividend_data.sort(key=lambda x: (x['year'], x['quarter']))
    result = {'company_name': company_name, 'period': 'quarterly', 'dividend_data': dividend_data}
    await quarterly_dividend_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/valuation/{company_name}")
async def get_valuation_endpoint(company_name: str):
    """현재 주가 기반 밸류에이션 지표를 반환합니다."""
    await database.record_search(company_name)
    cached = await valuation_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    result = await asyncio.to_thread(fetch_valuation, company_name)
    await valuation_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})
