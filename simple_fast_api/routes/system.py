"""시스템 라우트 (캐시 관리, Webhook, 헬스체크)."""
import asyncio
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update

import database
from config import WEBHOOK_SECRET_TOKEN
from cache import (
    dividend_cache, financials_cache, dividend_json_cache, business_cache,
    quarterly_financials_cache, quarterly_dividend_cache, valuation_cache,
    report_cache, buffett_report_cache, events_cache, insider_cache,
)
from services.cache_warmup import warm_popular_companies, TOP_N

router = APIRouter()

# bot_app 참조는 main.py에서 app.state에 설정합니다.


@router.get("/cache/status")
async def cache_status():
    """서버에 저장된 캐시 현황을 반환합니다."""
    keys = [
        "dividend_data", "financials", "analyze_dividends_json", "business_overview",
        "quarterly_financials", "quarterly_dividend", "valuation", "report", "buffett_report",
        "events", "insider",
    ]
    caches = [
        dividend_cache, financials_cache, dividend_json_cache, business_cache,
        quarterly_financials_cache, quarterly_dividend_cache, valuation_cache,
        report_cache, buffett_report_cache, events_cache, insider_cache,
    ]
    infos = await asyncio.gather(*[c.info() for c in caches])
    return JSONResponse(content=dict(zip(keys, infos)))


@router.delete("/cache/clear")
async def cache_clear(company_name: str = None):
    """캐시를 초기화합니다."""
    caches = [
        dividend_cache, financials_cache, dividend_json_cache, business_cache,
        quarterly_financials_cache, quarterly_dividend_cache, valuation_cache,
        report_cache, buffett_report_cache, events_cache, insider_cache,
    ]
    if company_name:
        results = await asyncio.gather(*[c.clear(company_name) for c in caches])
        if not any(results):
            raise HTTPException(status_code=404, detail=f"'{company_name}'의 캐시 데이터가 없습니다.")
        return {"message": f"'{company_name}'의 캐시가 삭제되었습니다."}
    else:
        await asyncio.gather(*[c.clear() for c in caches])
        return {"message": "전체 캐시가 삭제되었습니다."}


@router.get("/cache/popular")
async def popular_companies():
    """검색 횟수 상위 종목 목록을 반환합니다 (캐시 워밍업 대상 확인용)."""
    companies = await database.get_top_searched_companies(TOP_N)
    return {"top_n": TOP_N, "companies": companies}


@router.post("/cache/warmup")
async def trigger_cache_warmup():
    """인기 종목 캐시 워밍업을 즉시 실행합니다 (평소엔 매일 05:30 KST 자동 실행)."""
    await warm_popular_companies()
    return {"message": "캐시 워밍업이 완료되었습니다."}


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(request: Request):
    """Telegram이 메시지를 밀어주는 Webhook 엔드포인트."""
    if WEBHOOK_SECRET_TOKEN:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(incoming, WEBHOOK_SECRET_TOKEN):
            raise HTTPException(status_code=403, detail="Forbidden")
    bot_app = request.app.state.bot_app
    if not bot_app:
        raise HTTPException(status_code=503, detail="봇이 비활성화 상태입니다.")
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


@router.get("/", include_in_schema=False)
async def root():
    return {"message": "DART Report Analyzer with Gemini. /docs 에서 API 문서를 확인하세요."}
