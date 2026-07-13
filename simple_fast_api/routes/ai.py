"""AI 분석 라우트 (리포트, 챗봇, 내부자 거래)."""
import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import database
from cache import (
    dividend_cache, financials_cache, business_cache,
    valuation_cache, report_cache, buffett_report_cache,
)
from services.dart import (
    resolve_corp_code, fetch_dart_financials, fetch_business_overview,
    fetch_filing_list, fetch_insider_trading,
)
from services.report import generate_report, generate_buffett_report
from services.chat import build_system_context, chat_with_gemini, create_tool_executor
from services.insider import summarize_insider_data, build_insider_text, analyze_insider_with_gemini
from services.scoring import compute_investment_score

router = APIRouter()


async def _fetch_recent_filings(corp_code: str) -> list[dict]:
    """최근 공시 목록을 비동기로 조회합니다."""
    current_year = datetime.now().year
    bgn_de = f"{current_year - 1}0101"
    filings = await asyncio.to_thread(fetch_filing_list, corp_code, bgn_de)
    return filings or []


async def _gather_company_data(corp_code: str, company_name: str) -> dict:
    """리포트/챗에 필요한 데이터를 병렬 조회합니다."""
    current_year = datetime.now().year

    biz_result, filings, fin_all = await asyncio.gather(
        asyncio.to_thread(fetch_business_overview, corp_code, company_name),
        _fetch_recent_filings(corp_code),
        asyncio.gather(
            *[asyncio.to_thread(fetch_dart_financials, corp_code, str(y))
              for y in range(current_year - 1, current_year - 6, -1)],
            return_exceptions=True,
        ),
        return_exceptions=True,
    )

    return {
        'business_sections': biz_result.get('sections', []) if isinstance(biz_result, dict) else [],
        'recent_filings': filings if isinstance(filings, list) else [],
        'financials': [f for f in (fin_all if isinstance(fin_all, (list, tuple)) else []) if isinstance(f, dict)],
        'dividends': (await dividend_cache.get(company_name) or {}).get('dividend_data', []),
        'valuation': await valuation_cache.get(company_name),
    }


@router.get("/report/{company_name}")
async def get_report(company_name: str):
    """Gemini AI를 이용해 종합 투자 리포트를 생성합니다."""
    await database.record_search(company_name)
    cached = await report_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    data = await _gather_company_data(corp_code, company_name)

    report_text = await generate_report(
        company_name, data['business_sections'], data['financials'],
        data['dividends'], data['valuation'], data['recent_filings'],
    )

    result = {'company_name': company_name, 'report': report_text}
    await report_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/buffett-report/{company_name}")
async def get_buffett_report(company_name: str):
    """워렌 버핏 투자 철학을 적용한 종합 투자 리포트를 생성합니다."""
    await database.record_search(company_name)
    cached = await buffett_report_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await resolve_corp_code(company_name)
    data = await _gather_company_data(corp_code, company_name)

    report_text = await generate_buffett_report(
        company_name, data['business_sections'], data['financials'],
        data['dividends'], data['valuation'], data['recent_filings'],
    )

    result = {'company_name': company_name, 'report': report_text, 'mode': 'buffett'}
    await buffett_report_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    mode: str = "general"


@router.post("/chat/{company_name}")
async def chat(company_name: str, req: ChatRequest):
    """공시 데이터를 컨텍스트로 Gemini AI와 멀티턴 상담을 수행합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    current_year = datetime.now().year

    # 캐시 우선 사용
    biz_cached = await business_cache.get(company_name)
    fin_cached = await financials_cache.get(company_name)

    tasks = []
    need_biz = biz_cached is None
    need_fin = fin_cached is None

    if need_biz:
        tasks.append(asyncio.to_thread(fetch_business_overview, corp_code, company_name))
    if need_fin:
        tasks.append(asyncio.gather(
            *[asyncio.to_thread(fetch_dart_financials, corp_code, str(y))
              for y in range(current_year - 1, current_year - 6, -1)],
            return_exceptions=True,
        ))
    tasks.append(_fetch_recent_filings(corp_code))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    idx = 0
    if need_biz:
        biz_cached = results[idx] if isinstance(results[idx], dict) else {}
        idx += 1
    if need_fin:
        fin_all = results[idx] if isinstance(results[idx], (list, tuple)) else []
        fin_cached = {'financials': [f for f in fin_all if isinstance(f, dict)]}
        idx += 1
    filings = results[idx] if isinstance(results[idx], list) else []

    business_sections = (biz_cached or {}).get('sections', [])
    financials = (fin_cached or {}).get('financials', [])
    dividends = (await dividend_cache.get(company_name) or {}).get('dividend_data', [])
    valuation = await valuation_cache.get(company_name)

    buffett_mode = req.mode == "buffett"
    system_context = build_system_context(
        company_name, business_sections, financials, dividends, valuation, filings,
        buffett_mode=buffett_mode,
    )

    # Function Calling 도구 실행기 생성
    tool_executor = create_tool_executor(corp_code, company_name, financials, valuation)

    answer = await chat_with_gemini(
        system_context, req.history, req.message, company_name,
        buffett_mode=buffett_mode,
        tool_executor=tool_executor,
    )
    return JSONResponse(content={"answer": answer, "mode": req.mode})


@router.get("/insider/{company_name}")
async def get_insider_trading(company_name: str):
    """임원/주요주주 내부자 거래 현황 및 AI 분석을 반환합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    year = str(datetime.now().year - 1)

    raw = await asyncio.to_thread(fetch_insider_trading, corp_code, year)

    holdings = raw.get('holdings', [])
    recent_filings = raw.get('recent_filings', [])

    if not holdings and not recent_filings:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 내부자 거래 데이터를 찾을 수 없습니다.")

    summary = summarize_insider_data(holdings)
    message_text = build_insider_text(company_name, year, summary, recent_filings)
    ai_analysis = await analyze_insider_with_gemini(company_name, year, summary, recent_filings)

    return {
        "company": company_name,
        "year": year,
        "summary": summary,
        "recent_filings": recent_filings,
        "message_text": message_text,
        "ai_analysis": ai_analysis,
    }


@router.get("/score/{company_name}")
async def get_investment_score(company_name: str):
    """정량 투자 스코어를 계산하여 반환합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    data = await _gather_company_data(corp_code, company_name)

    score_data = compute_investment_score(
        data['financials'], data['dividends'], data['valuation'],
    )

    # 시그널 텍스트에서 긍정/부정/중립 분류
    positive_keywords = [
        '고성장', '상회', '우수', '저평가', '안정적', '순현금', '증가',
        '개선', '15% 이상', '급증', '높은 영업이익률',
    ]
    negative_keywords = [
        '역성장', '하락', '주의', '악화', '고평가', '높음', '미만',
        '미달', '부족', '마이너스', '급감',
    ]

    def classify_signal(text: str) -> str:
        if any(kw in text for kw in positive_keywords):
            return "positive"
        if any(kw in text for kw in negative_keywords):
            return "negative"
        return "neutral"

    signals = [
        {"text": s, "type": classify_signal(s)}
        for s in score_data['key_signals']
    ]

    return {
        "company_name": company_name,
        "total_score": score_data['total_score'],
        "total_grade": score_data['total_grade'],
        "categories": score_data['categories'],
        "key_signals": signals,
    }
