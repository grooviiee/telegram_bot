"""시스템 라우트 (캐시 관리, Webhook, 헬스체크)."""
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update

from config import WEBHOOK_SECRET_TOKEN
from cache import (
    dividend_cache, financials_cache, dividend_json_cache, business_cache,
    quarterly_financials_cache, quarterly_dividend_cache, valuation_cache,
    report_cache, buffett_report_cache,
)

router = APIRouter()

# bot_app 참조는 main.py에서 app.state에 설정합니다.


@router.get("/cache/status")
async def cache_status():
    """서버에 저장된 캐시 현황을 반환합니다."""
    return JSONResponse(content={
        "dividend_data": dividend_cache.info(),
        "financials": financials_cache.info(),
        "analyze_dividends_json": dividend_json_cache.info(),
        "business_overview": business_cache.info(),
        "quarterly_financials": quarterly_financials_cache.info(),
        "quarterly_dividend": quarterly_dividend_cache.info(),
        "valuation": valuation_cache.info(),
        "report": report_cache.info(),
        "buffett_report": buffett_report_cache.info(),
    })


@router.delete("/cache/clear")
async def cache_clear(company_name: str = None):
    """캐시를 초기화합니다."""
    if company_name:
        removed = any([
            dividend_cache.clear(company_name),
            financials_cache.clear(company_name),
            dividend_json_cache.clear(company_name),
            business_cache.clear(company_name),
            report_cache.clear(company_name),
            buffett_report_cache.clear(company_name),
        ])
        if not removed:
            raise HTTPException(status_code=404, detail=f"'{company_name}'의 캐시 데이터가 없습니다.")
        return {"message": f"'{company_name}'의 캐시가 삭제되었습니다."}
    else:
        dividend_cache.clear()
        financials_cache.clear()
        dividend_json_cache.clear()
        business_cache.clear()
        report_cache.clear()
        buffett_report_cache.clear()
        return {"message": "전체 캐시가 삭제되었습니다."}


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
