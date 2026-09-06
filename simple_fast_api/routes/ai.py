"""AI 분석 라우트 (리포트, 챗봇, 내부자 거래)."""
import asyncio
import json
from config import GEMINI_API_KEY, DART_ELESTOCK_URL
from cache import insider_cache, insider_ai_cache
from services.company_data import gather_company_data, provenance
from services.ai_policy import cached_inference
from services.factual import answer_factual
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import database
from cache import (
    report_cache, buffett_report_cache, events_cache,
)
from services.dart import (
    resolve_corp_code, fetch_insider_trading,
)
from services.report import generate_report, generate_buffett_report
from services.chat import build_system_context, chat_with_gemini, create_tool_executor
from services.insider import summarize_insider_data, build_insider_text, analyze_insider_with_gemini
from services.scoring import cached_investment_score
from services.events import analyze_price_events

router = APIRouter()


async def _report_response(company_name: str, buffett: bool) -> JSONResponse:
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    data = await gather_company_data(corp_code, company_name)
    generator = generate_buffett_report if buffett else generate_report
    cache = buffett_report_cache if buffett else report_cache

    async def generate() -> str:
        return await generator(company_name, data['business_sections'], data['financials'],
                               data['dividends'], data['valuation'], data['recent_filings'],
                               data_quality=data['data_quality'])

    text, cached = await cached_inference(cache, company_name, data, generate)
    quality = data['data_quality']
    lines = ['[분석 데이터 기준]']
    for name, source in quality['sources'].items():
        lines.append(f"- {name}: {source['source']} / 기준연도 {source['fiscal_years']} / 조회 {source['retrieved_at']}")
    lines.extend(f'- {warning}' for warning in quality['warnings'])
    return JSONResponse(content={'company_name': company_name,
        'report': '\n'.join(lines) + '\n\n' + text,
        'mode': 'buffett' if buffett else 'general', 'cached': cached,
        'ai_used': not cached, 'data_quality': quality})


@router.get("/report/{company_name}")
async def get_report(company_name: str) -> JSONResponse:
    """명시적으로 요청된 종합 해석만 AI로 생성합니다."""
    return await _report_response(company_name, False)


@router.get("/buffett-report/{company_name}")
async def get_buffett_report(company_name: str) -> JSONResponse:
    """명시적으로 요청된 버핏 관점 해석만 AI로 생성합니다."""
    return await _report_response(company_name, True)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    mode: str = "general"


@router.post("/chat/{company_name}")
async def chat(company_name: str, req: ChatRequest):
    """공시 데이터를 컨텍스트로 Gemini AI와 멀티턴 상담을 수행합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    factual = await answer_factual(company_name, corp_code, req.message)
    if factual is not None:
        return JSONResponse(content={"answer": factual, "mode": req.mode, "ai_used": False})
    if not GEMINI_API_KEY:
        raise HTTPException(503, 'AI 분석 키가 설정되지 않았습니다.')
    data = await gather_company_data(corp_code, company_name)
    business_sections = data['business_sections']
    financials = data['financials']
    dividends = data['dividends']
    valuation = data['valuation']
    filings = data['recent_filings']

    buffett_mode = req.mode == "buffett"
    system_context = build_system_context(
        company_name, business_sections, financials, dividends, valuation, filings,
        buffett_mode=buffett_mode,
    )

    system_context += "\n" + json.dumps(data["data_quality"], ensure_ascii=False)

    # Function Calling 도구 실행기 생성
    tool_executor = create_tool_executor(corp_code, company_name, financials, valuation)

    answer = await chat_with_gemini(
        system_context, req.history, req.message, company_name,
        buffett_mode=buffett_mode,
        tool_executor=tool_executor,
    )
    if not answer or answer.startswith('(AI 응답 생성 실패)'):
        raise HTTPException(502, 'AI 분석 생성에 실패했습니다.')
    return JSONResponse(content={"answer": answer, "mode": req.mode, "ai_used": True,
                                 "data_quality": data['data_quality']})


@router.get("/insider/{company_name}")
async def get_insider_trading(company_name: str, ai_analysis: bool = False):
    """임원/주요주주 내부자 거래 현황 및 AI 분석을 반환합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    year = str(datetime.now().year - 1)

    async def load() -> dict:
        result = await asyncio.to_thread(fetch_insider_trading, corp_code, year)
        if not result.get('holdings') and not result.get('recent_filings'):
            raise HTTPException(404, f"'{company_name}'의 내부자 데이터를 찾을 수 없습니다.")
        result['provenance'] = provenance(DART_ELESTOCK_URL)
        return result
    raw, cached = await insider_cache.get_or_create(company_name, load)

    holdings = raw.get('holdings', [])
    recent_filings = raw.get('recent_filings', [])

    if not holdings and not recent_filings:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 내부자 거래 데이터를 찾을 수 없습니다.")

    summary = summarize_insider_data(holdings)
    message_text = build_insider_text(company_name, year, summary, recent_filings)
    analysis_text = ''
    ai_used = False
    if ai_analysis:
        async def generate() -> str:
            return await analyze_insider_with_gemini(company_name, year, summary, recent_filings)
        analysis_text, hit = await cached_inference(insider_ai_cache, company_name, raw, generate)
        ai_used = not hit

    return {
        "company": company_name,
        "year": year,
        "summary": summary,
        "recent_filings": recent_filings,
        "message_text": message_text,
        "ai_analysis": analysis_text,
        "ai_used": ai_used, "cached": cached, "provenance": raw["provenance"],
    }


@router.get("/score/{company_name}")
async def get_investment_score(company_name: str):
    """정량 투자 스코어를 계산하여 반환합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    data = await gather_company_data(corp_code, company_name, narrative=False)

    score_data, cached = await cached_investment_score(company_name, data)

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
        if "평가 불가" in text:
            return "neutral"
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
        "missing_categories": score_data['missing_categories'],
        "coverage": score_data['coverage'],
        "data_quality": data['data_quality'],
        "cached": cached, "ai_used": False,
    }


@router.get("/events/{company_name}")
async def get_price_events(company_name: str):
    """수집된 뉴스에서 주요 사건을 선별하며 주가 인과관계를 단정하지 않습니다."""
    await database.record_search(company_name)
    async def load() -> dict:
        return await analyze_price_events(company_name)
    result, cached = await events_cache.get_or_create(company_name, load)
    return JSONResponse(content={**result, 'cached': cached})
