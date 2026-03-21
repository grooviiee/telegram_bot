"""
Telegram 봇 모듈.
- 커맨드 핸들러: /배당, /수익성, /재무건전성, /즐겨찾기추가, /즐겨찾기삭제, /즐겨찾기
- 알림 발송: send_daily_notification() (스케줄러에서 호출)
"""

import os
import asyncio
import html
import aiohttp
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

import database

# -------------------------------------------------------------------
# 설정
# -------------------------------------------------------------------

API_BASE: str = os.getenv("API_BASE_URL", "http://localhost:8000")

_session: aiohttp.ClientSession | None = None

def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
    return _session

async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None

ANALYSIS_TYPE_MAP = {
    "dividend": "dividend",
    "profit":   "profitability",
    "health":   "financial-health",
}
ANALYSIS_LABEL = {
    "dividend": "배당 분석",
    "profitability": "수익성 & 성장성",
    "financial-health": "재무 건전성",
}

# -------------------------------------------------------------------
# 내부 HTTP 헬퍼
# -------------------------------------------------------------------

async def _get(path: str) -> tuple[dict, int]:
    """로컬 FastAPI 서버에 GET 요청."""
    session = get_session()
    async with session.get(f"{API_BASE}{path}") as resp:
        return await resp.json(), resp.status


# -------------------------------------------------------------------
# 응답 포맷터
# -------------------------------------------------------------------

def _e(text) -> str:
    """HTML 특수문자 이스케이프."""
    return html.escape(str(text))


def fmt_dividend(company: str, items: list, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    rows = "\n".join(f"{d['year']}년  {d['dividend']:>10,}원" for d in items)
    return (
        f"📊 <b>{_e(company)} 배당 분석</b>{cache_tag}\n"
        f"<pre>{rows}</pre>"
    )


def fmt_profitability(company: str, items: list, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    header = f"{'연도':<4}  {'매출(억)':>9}  {'영업이익(억)':>11}  {'이익률':>6}  {'ROE':>6}"
    sep = "─" * 48
    rows = []
    for d in items:
        rev = f"{round(d['revenue'] / 1e8):,}" if d.get("revenue") else "N/A"
        oi  = f"{round(d['operating_income'] / 1e8):,}" if d.get("operating_income") else "N/A"
        mg  = f"{d['operating_margin']:.1f}%" if d.get("operating_margin") else "N/A"
        roe = f"{d['roe']:.1f}%" if d.get("roe") else "N/A"
        rows.append(f"{d['year']:<4}  {rev:>9}  {oi:>11}  {mg:>6}  {roe:>6}")
    return (
        f"📈 <b>{_e(company)} 수익성 &amp; 성장성</b>{cache_tag}\n"
        f"<pre>{header}\n{sep}\n" + "\n".join(rows) + "</pre>"
    )


def fmt_financial_health(company: str, items: list, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    header = f"{'연도':<4}  {'부채비율':>6}  {'유동비율':>6}  {'FCF(억)':>9}"
    sep = "─" * 33
    rows = []
    for d in items:
        debt = f"{d['debt_ratio']:.1f}%" if d.get("debt_ratio") else "N/A"
        curr = f"{d['current_ratio']:.1f}%" if d.get("current_ratio") else "N/A"
        fcf  = f"{round(d['fcf'] / 1e8):,}" if d.get("fcf") else "N/A"
        rows.append(f"{d['year']:<4}  {debt:>6}  {curr:>6}  {fcf:>9}")
    return (
        f"🏦 <b>{_e(company)} 재무 건전성</b>{cache_tag}\n"
        f"<pre>{header}\n{sep}\n" + "\n".join(rows) + "</pre>"
    )


# -------------------------------------------------------------------
# 커맨드 핸들러
# -------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 <b>DART 재무분석 봇</b>입니다.\n\n"
        "📊 /dividend [회사명] — 5개년 배당금\n"
        "📈 /profit [회사명] — 매출·영업이익·ROE\n"
        "🏦 /health [회사명] — 부채비율·FCF\n\n"
        "⭐ /fav_add [회사명] [dividend|profit|health]\n"
        "📋 /favs — 내 즐겨찾기 목록\n"
        "🗑 /fav_del [회사명] [dividend|profit|health]\n\n"
        "<i>매일 오전 9시(KST) 즐겨찾기 요약 알림을 받습니다.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_dividend(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /dividend [회사명]\n예: /dividend 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(f"⏳ <i>'{_e(company)}' 배당 데이터 조회 중...</i>", parse_mode=ParseMode.HTML)
    data, status = await _get(f"/dividend-data/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
        return
    text = fmt_dividend(data["company_name"], data["dividend_data"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_profitability(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /profit [회사명]\n예: /profit 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(f"⏳ <i>'{_e(company)}' 수익성 데이터 조회 중...</i>", parse_mode=ParseMode.HTML)
    data, status = await _get(f"/financials/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
        return
    text = fmt_profitability(data["company_name"], data["financials"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_financial_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /health [회사명]\n예: /health 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(f"⏳ <i>'{_e(company)}' 재무 건전성 데이터 조회 중...</i>", parse_mode=ParseMode.HTML)
    data, status = await _get(f"/financials/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
        return
    text = fmt_financial_health(data["company_name"], data["financials"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_add_favorite(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if len(ctx.args) < 2 or ctx.args[-1] not in ANALYSIS_TYPE_MAP:
        await update.message.reply_text(
            "사용법: /fav_add [회사명] [분석유형]\n"
            "분석유형: dividend | profit | health\n"
            "예: /fav_add 삼성전자 dividend"
        )
        return
    analysis_type = ANALYSIS_TYPE_MAP[ctx.args[-1]]
    company = " ".join(ctx.args[:-1])
    user = update.effective_user
    added = await database.add_favorite(user.id, user.username or "", company, analysis_type)
    label = ANALYSIS_LABEL[analysis_type]
    if added:
        await update.message.reply_text(f"⭐ '{company} ({label})'을 즐겨찾기에 추가했습니다.")
    else:
        await update.message.reply_text("이미 즐겨찾기에 있는 항목입니다.")


async def cmd_remove_favorite(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if len(ctx.args) < 2 or ctx.args[-1] not in ANALYSIS_TYPE_MAP:
        await update.message.reply_text(
            "사용법: /fav_del [회사명] [분석유형]\n"
            "예: /fav_del 삼성전자 dividend"
        )
        return
    analysis_type = ANALYSIS_TYPE_MAP[ctx.args[-1]]
    company = " ".join(ctx.args[:-1])
    removed = await database.remove_favorite(update.effective_user.id, company, analysis_type)
    label = ANALYSIS_LABEL[analysis_type]
    if removed:
        await update.message.reply_text(f"🗑 '{company} ({label})'을 즐겨찾기에서 삭제했습니다.")
    else:
        await update.message.reply_text("즐겨찾기에 없는 항목입니다.")


async def cmd_list_favorites(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    favs = await database.get_user_favorites(update.effective_user.id)
    if not favs:
        await update.message.reply_text(
            "즐겨찾기가 없습니다.\n/즐겨찾기추가 명령어로 추가해보세요."
        )
        return
    lines = ["⭐ <b>내 즐겨찾기</b>\n"]
    for f in favs:
        label = ANALYSIS_LABEL.get(f["analysis_type"], f["analysis_type"])
        lines.append(f"• {_e(f['company'])} — {label}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# -------------------------------------------------------------------
# 일일 알림 발송 (APScheduler에서 호출)
# -------------------------------------------------------------------

async def _build_user_message(user_id: int, items: list) -> tuple[int, str | None]:
    """사용자 한 명에 대한 즐겨찾기 메시지를 비동기로 빌드합니다."""
    async def _fetch_item(company: str, analysis_type: str) -> str | None:
        try:
            if analysis_type == "dividend":
                data, status = await _get(f"/dividend-data/{company}")
                if status == 200 and data.get("dividend_data"):
                    latest = data["dividend_data"][-1]
                    return (
                        f"📊 <b>{_e(company)}</b> 배당금: "
                        f"{latest['dividend']:,}원 ({latest['year']}년)"
                    )
            elif analysis_type in ("profitability", "financial-health"):
                data, status = await _get(f"/financials/{company}")
                if status == 200 and data.get("financials"):
                    latest = data["financials"][-1]
                    if analysis_type == "profitability":
                        mg = f"{latest['operating_margin']:.1f}%" if latest.get("operating_margin") else "N/A"
                        roe = f"{latest['roe']:.1f}%" if latest.get("roe") else "N/A"
                        return f"📈 <b>{_e(company)}</b> 영업이익률: {mg}, ROE: {roe} ({latest['year']}년)"
                    else:
                        debt = f"{latest['debt_ratio']:.1f}%" if latest.get("debt_ratio") else "N/A"
                        return f"🏦 <b>{_e(company)}</b> 부채비율: {debt} ({latest['year']}년)"
        except Exception as e:
            print(f"[알림] {company} 데이터 조회 오류: {e}")
        return None

    results = await asyncio.gather(*[_fetch_item(company, analysis_type) for company, analysis_type in items])
    lines = ["🔔 <b>오늘의 즐겨찾기 현황</b>\n"] + [r for r in results if r]
    if len(lines) > 1:
        return user_id, "\n".join(lines)
    return user_id, None


async def send_daily_notification(bot: Bot) -> None:
    """즐겨찾기 사용자 전원에게 오전 9시(KST) 최신 데이터 요약 발송."""
    grouped = await database.get_all_favorites_grouped()
    if not grouped:
        return

    print(f"[알림] {len(grouped)}명에게 일일 알림 발송 시작")

    # 모든 사용자 메시지를 동시에 빌드
    messages = await asyncio.gather(
        *[_build_user_message(user_id, items) for user_id, items in grouped.items()]
    )

    # 순차 발송
    for user_id, text in messages:
        if text:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                print(f"[알림] user {user_id} 메시지 발송 오류: {e}")

    print("[알림] 일일 알림 발송 완료")


# -------------------------------------------------------------------
# 봇 애플리케이션 팩토리
# -------------------------------------------------------------------

def create_bot_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("dividend",  cmd_dividend))
    app.add_handler(CommandHandler("profit",    cmd_profitability))
    app.add_handler(CommandHandler("health",    cmd_financial_health))
    app.add_handler(CommandHandler("fav_add",   cmd_add_favorite))
    app.add_handler(CommandHandler("fav_del",   cmd_remove_favorite))
    app.add_handler(CommandHandler("favs",      cmd_list_favorites))
    return app
