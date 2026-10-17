"""AI 분석 라우트 (리포트, 챗봇, 내부자 거래)."""
import asyncio
import json
import re
from config import (GEMINI_API_KEY, DART_ELESTOCK_URL, AI_PROVIDER, GEMINI_MODEL,
                    OLLAMA_MODEL, AI_MAX_QUESTION_CHARS, AI_EVIDENCE_RULES, OLLAMA_MAX_OUTPUT_TOKENS)
from cache import insider_cache, insider_ai_cache
from services.company_data import gather_company_data, provenance
from services.ai_policy import cached_inference
from services.factual import answer_factual
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from utils import call_gemini
from services.local_ai import ollama_status
from services.report_retrieval import answer_from_report
from services.segments import (segment_data, is_segment_question, format_segment_answer,
                               resolve_segment_request, explain_segment_contribution)

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


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=AI_MAX_QUESTION_CHARS)


@router.get('/ai/status')
async def ai_status() -> dict:
    """비밀키 없이 현재 AI 제공자와 로컬 모델 상태를 표시합니다."""
    if AI_PROVIDER == 'ollama':
        return await ollama_status()
    return {'provider': AI_PROVIDER, 'model': GEMINI_MODEL, 'available': bool(GEMINI_API_KEY)}


@router.post('/ask')
async def ask(req: AskRequest) -> dict:
    """공시 조회 없이 일반 질문을 현재 AI 제공자에 전달합니다."""
    if not req.message.strip():
        raise HTTPException(422, '질문을 입력해주세요.')
    if AI_PROVIDER != 'ollama' and not GEMINI_API_KEY:
        raise HTTPException(503, 'AI가 설정되지 않았습니다.')
    answer = await call_gemini(req.message, system_instruction=AI_EVIDENCE_RULES +
        '\n일반 개념 설명을 제공합니다. 기업의 실적·최신 뉴스·공시를 조회했다고 주장하지 마세요.',
        generation_config={'temperature': .2, 'maxOutputTokens': OLLAMA_MAX_OUTPUT_TOKENS})
    if not answer or answer.startswith('(AI 응답 생성 실패)'):
        raise HTTPException(502, 'AI 응답을 생성하지 못했습니다. /ai로 상태를 확인해주세요.')
    return {'answer': answer, 'provider': AI_PROVIDER,
            'model': OLLAMA_MODEL if AI_PROVIDER == 'ollama' else GEMINI_MODEL, 'ai_used': True}


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
    message: str = Field(min_length=1, max_length=AI_MAX_QUESTION_CHARS)
    history: list[dict] = Field(default_factory=list, max_length=30)
    mode: str = "general"


@router.post("/chat/{company_name}")
async def chat(company_name: str, req: ChatRequest):
    """공시 데이터를 컨텍스트로 Gemini AI와 멀티턴 상담을 수행합니다."""
    await database.record_search(company_name)
    corp_code = await resolve_corp_code(company_name)
    if is_segment_question(req.message, req.history):
        if re.search(r'분기|반기|\d\s*[Qq]|[Qq]\s*\d', req.message):
            return JSONResponse(content={'answer': '현재 사업부별 손익은 연간 사업보고서 기준입니다. 분기·반기 수치를 연간 수치로 대신하지 않습니다.', 'ai_used': False})
        year, revenue = resolve_segment_request(req.message, req.history, None)
        if year is None and '전년' in req.message:
            latest, _ = await segment_data(company_name, corp_code)
            year, revenue = resolve_segment_request(req.message, req.history, latest['year'])
        result, cached = await segment_data(company_name, corp_code, year)
        answer = format_segment_answer(result, revenue)
        if any(word in req.message for word in ('왜', '이유', '원인', '해석', '분석', '의미')):
            answer += '\n\n[계산 해설]\n' + explain_segment_contribution(result, revenue)
        return JSONResponse(content={'answer': answer, 'ai_used': False,
                                     'cached': cached, 'segment_data': result})
    factual = await answer_factual(company_name, corp_code, req.message)
    if factual is not None:
        return JSONResponse(content={"answer": factual, "mode": req.mode, "ai_used": False})
    if AI_PROVIDER != 'ollama' and not GEMINI_API_KEY:
        raise HTTPException(503, 'AI 분석 키가 설정되지 않았습니다.')
    # 계산 도구가 필요한 상담은 기존 경로로, 서술형 질문은 전체 공시 근거 검색으로 처리합니다.
    if not re.search(r'내재가치|적정\s*주가|DCF|듀퐁|DuPont|분기|ROE.*분해', req.message, re.IGNORECASE):
        return JSONResponse(content=await answer_from_report(company_name, corp_code, req.message, req.history))
    data = await gather_company_data(corp_code, company_name)
    business_sections = data['business_sections']
    financials = data['financials']
    dividends = data['dividends']
    valuation = data['valuation']
    filings = data['recent_filings']

    buffett_mode = req.mode == "buffett"
    system_context = build_system_context(
        company_name, business_sections, financials, dividends, valuation, filings,
        buffett_mode=buffett_mode, question=req.message,
    )

    quality = data['data_quality']
    context_quality = ({'warnings': quality['warnings'],
                        'financials_source': quality['sources'].get('financials')}
                       if AI_PROVIDER == 'ollama' else quality)
    system_context += "\n" + json.dumps(context_quality, ensure_ascii=False)

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
