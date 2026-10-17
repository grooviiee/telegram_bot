"""
Telegram 봇 모듈.
- 커맨드 핸들러: /analysis, /business, /dividend, /profit, /health,
                 /valuation, /report, /buffett, /score, /chat(/end),
                 /fav_add, /fav_del, /favs
- 알림 발송: send_daily_notification() (스케줄러에서 호출)
"""

import os
import re
import asyncio
import html
import logging
import aiohttp
from telegram import Update, Bot, BotCommand, MenuButtonCommands, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden

import database
from config import (TELEGRAM_BOT_TOKEN, TELEGRAM_COMMANDS, TRENDING_SEND_HOUR,
                    TRENDING_SEND_MINUTE, INSIDER_REQUEST_TIMEOUT,
                    AI_HTTP_TIMEOUT, AI_MAX_QUESTION_CHARS)
from services import github_trending
from utils import fmt_krw
from services.profit_chart import render_profit_chart
from services.insider_chart import render_insider_chart

# -------------------------------------------------------------------
# 설정
# -------------------------------------------------------------------

API_BASE: str = os.getenv("API_BASE_URL", "http://localhost:8000")

# ConversationHandler 상태
CHAT_ACTIVE = 1

_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
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
    "dividend":        "배당 분석",
    "profitability":   "수익성 & 성장성",
    "financial-health":"재무 건전성",
}

# -------------------------------------------------------------------
# 내부 HTTP 헬퍼
# -------------------------------------------------------------------

async def _get(path: str, timeout: int | None = None) -> tuple[dict, int]:
    """로컬 FastAPI 서버에 GET 요청."""
    session = get_session()
    request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout is not None else session.timeout
    async with session.get(f"{API_BASE}{path}", timeout=request_timeout) as resp:
        return await resp.json(), resp.status


async def _post(path: str, payload: dict) -> tuple[dict, int]:
    """로컬 FastAPI 서버에 POST 요청."""
    session = get_session()
    async with session.post(f"{API_BASE}{path}", json=payload,
                            timeout=aiohttp.ClientTimeout(total=AI_HTTP_TIMEOUT)) as resp:
        return await resp.json(), resp.status


async def _send_long(update: Update, text: str, parse_mode=ParseMode.HTML) -> None:
    """4096자를 초과하는 메시지를 여러 번으로 나눠 전송합니다."""
    limit = 4096
    while text:
        chunk, text = text[:limit], text[limit:]
        await update.message.reply_text(chunk, parse_mode=parse_mode)


# -------------------------------------------------------------------
# HTML 이스케이프 / Markdown → HTML 변환
# -------------------------------------------------------------------

def _e(text) -> str:
    return html.escape(str(text))


def _md_to_html(text: str) -> str:
    """AI 리포트의 간단한 Markdown을 Telegram HTML로 변환합니다."""
    lines = []
    for line in text.split('\n'):
        # ### 헤더
        if line.startswith('### '):
            line = f"<b>{_e(line[4:])}</b>"
        # ## 헤더
        elif line.startswith('## '):
            line = f"\n<b>▌ {_e(line[3:])}</b>"
        # 구분선
        elif line.strip() == '---':
            line = '─' * 30
        # 리스트
        elif re.match(r'^[-*] ', line):
            line = '• ' + _e(line[2:])
        else:
            # **bold**
            line = re.sub(r'\*\*(.+?)\*\*', lambda m: f"<b>{_e(m.group(1))}</b>", _e(line))
        lines.append(line)
    return '\n'.join(lines)


# -------------------------------------------------------------------
# 응답 포맷터
# -------------------------------------------------------------------

def _fmt_krw(v) -> str:
    """Telegram 표시용 KRW 포매터 (조/억 단위에서 '원' 생략)."""
    text = fmt_krw(v)
    return text.replace("조원", "조").replace("억원", "억")


def fmt_dividend(company: str, items: list, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    rows = "\n".join(f"{d['year']}년  {d['dividend']:>10,}원" for d in items)
    return (
        f"📊 <b>{_e(company)} 배당 분석</b>{cache_tag}\n"
        f"<pre>{rows}</pre>"
    )


def fmt_profitability(company: str, items: list, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    header = f"{'연도':<4}  {'매출(억)':>8}  {'영업이익(억)':>10}  {'이익률':>6}  {'ROE':>6}"
    sep = "─" * 46
    rows = []
    for d in items:
        rev = f"{round(d['revenue'] / 1e8):,}" if d.get("revenue") else "N/A"
        oi  = f"{round(d['operating_income'] / 1e8):,}" if d.get("operating_income") else "N/A"
        mg  = f"{d['operating_margin']:.1f}%" if d.get("operating_margin") else "N/A"
        roe = f"{d['roe']:.1f}%" if d.get("roe") else "N/A"
        rows.append(f"{d['year']:<4}  {rev:>8}  {oi:>10}  {mg:>6}  {roe:>6}")
    return (
        f"📈 <b>{_e(company)} 수익성 &amp; 성장성</b>{cache_tag}\n"
        f"<pre>{header}\n{sep}\n" + "\n".join(rows) + "</pre>"
    )


def fmt_financial_health(company: str, items: list, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    header = f"{'연도':<4}  {'부채비율':>6}  {'순부채비율':>8}  {'유동비율':>6}  {'FCF(억)':>8}"
    sep = "─" * 42
    rows = []
    for d in items:
        debt    = f"{d['debt_ratio']:.1f}%" if d.get("debt_ratio") else "N/A"
        net_d   = f"{d['net_debt_ratio']:.1f}%" if d.get("net_debt_ratio") else "N/A"
        curr    = f"{d['current_ratio']:.1f}%" if d.get("current_ratio") else "N/A"
        fcf     = f"{round(d['fcf'] / 1e8):,}" if d.get("fcf") else "N/A"
        rows.append(f"{d['year']:<4}  {debt:>6}  {net_d:>8}  {curr:>6}  {fcf:>8}")
    return (
        f"🏦 <b>{_e(company)} 재무 건전성</b>{cache_tag}\n"
        f"<pre>{header}\n{sep}\n" + "\n".join(rows) + "</pre>"
    )


def fmt_analysis(company: str, items: list, cached: bool) -> str:
    """종합 분석 — 핵심 지표 요약."""
    cache_tag = " <i>(캐시)</i>" if cached else ""
    if not items:
        return f"📋 <b>{_e(company)} 종합 분석</b>{cache_tag}\n데이터 없음"

    latest = items[-1]
    lines = [f"📋 <b>{_e(company)} 종합 분석</b>{cache_tag}",
             f"<i>기준: {latest['year']}년 (최근 {len(items)}개년)</i>\n"]

    lines.append("<b>[ 수익성 ]</b>")
    lines.append(f"  매출액   : {_fmt_krw(latest.get('revenue'))}")
    lines.append(f"  영업이익 : {_fmt_krw(latest.get('operating_income'))}")
    lines.append(f"  당기순이익: {_fmt_krw(latest.get('net_income'))}")
    mg = f"{latest['operating_margin']:.1f}%" if latest.get("operating_margin") else "N/A"
    lines.append(f"  영업이익률: {mg}")
    roe = f"{latest['roe']:.1f}%" if latest.get("roe") else "N/A"
    lines.append(f"  ROE      : {roe}\n")

    lines.append("<b>[ 재무 건전성 ]</b>")
    debt = f"{latest['debt_ratio']:.1f}%" if latest.get("debt_ratio") else "N/A"
    net_d = f"{latest['net_debt_ratio']:.1f}%" if latest.get("net_debt_ratio") else "N/A"
    curr = f"{latest['current_ratio']:.1f}%" if latest.get("current_ratio") else "N/A"
    lines.append(f"  부채비율  : {debt}")
    lines.append(f"  순부채비율: {net_d}")
    lines.append(f"  유동비율  : {curr}")
    lines.append(f"  FCF      : {_fmt_krw(latest.get('fcf'))}\n")

    lines.append("<b>[ 배당 ]</b>")
    div = latest.get("dividend_per_share")
    lines.append(f"  주당배당금: {div:,}원" if div else "  주당배당금: N/A")

    return "\n".join(lines)


def fmt_valuation(company: str, data: dict, cached: bool) -> str:
    cache_tag = " <i>(캐시)</i>" if cached else ""
    price = data.get("price", 0)
    lines = [
        f"💹 <b>{_e(company)} 밸류에이션</b>{cache_tag}",
        f"<i>현재가: {price:,.0f}원 | 시가총액: {_fmt_krw(data.get('market_cap'))}</i>\n",
        "<b>[ 현재 지표 ]</b>",
        f"  PER    : {data['per']}x"   if data.get("per")     else "  PER    : N/A",
        f"  PBR    : {data['pbr']}x"   if data.get("pbr")     else "  PBR    : N/A",
        f"  PSR    : {data['psr']}x"   if data.get("psr")     else "  PSR    : N/A",
        f"  EV/EBIT: {data['ev_ebit']}x" if data.get("ev_ebit") else "  EV/EBIT: N/A",
    ]

    history = data.get("history", [])
    if history:
        lines.append("\n<b>[ 연도별 이력 ]</b>")
        header = f"{'연도':<4}  {'PER':>6}  {'PBR':>6}  {'PSR':>6}  {'EV/EBIT':>7}"
        sep = "─" * 38
        rows = []
        for h in history:
            per  = f"{h['per']}x"      if h.get("per")     else "N/A"
            pbr  = f"{h['pbr']}x"      if h.get("pbr")     else "N/A"
            psr  = f"{h['psr']}x"      if h.get("psr")     else "N/A"
            ev   = f"{h['ev_ebit']}x"  if h.get("ev_ebit") else "N/A"
            rows.append(f"{h['year']:<4}  {per:>6}  {pbr:>6}  {psr:>6}  {ev:>7}")
        lines.append(f"<pre>{header}\n{sep}\n" + "\n".join(rows) + "</pre>")

    return "\n".join(lines)


def fmt_business_text(company: str, sections: list, cached: bool) -> str:
    """사업 분석 — 텍스트 블록만 추출 (테이블 제외)."""
    cache_tag = " <i>(캐시)</i>" if cached else ""
    parts = [f"🏢 <b>{_e(company)} 사업 분석</b>{cache_tag}\n"]
    for sec in sections:
        parts.append(f"\n<b>{sec['number']}. {_e(sec['title'])}</b>")
        text_blocks = [
            b["content"] for b in sec.get("blocks", [])
            if b.get("type") == "text" and b.get("content")
        ]
        if text_blocks:
            combined = " ".join(text_blocks)
            # 500자로 요약
            if len(combined) > 500:
                combined = combined[:497] + "..."
            parts.append(_e(combined))
        else:
            parts.append("<i>(텍스트 내용 없음)</i>")
    return "\n".join(parts)


# -------------------------------------------------------------------
# 유사 기업 추천 (404 처리 공통 헬퍼)
# -------------------------------------------------------------------

async def _show_suggestions(msg, query: str, cmd: str) -> None:
    """검색 실패 시 유사 기업명 버튼을 보여줍니다."""
    from services.dart import search_similar_companies
    loop = asyncio.get_event_loop()
    suggestions = await loop.run_in_executor(None, search_similar_companies, query, 8)

    if not suggestions:
        await msg.edit_text(
            f"❌ <b>'{_e(query)}'</b> 기업을 찾을 수 없습니다.\n"
            "회사 정식 명칭으로 다시 시도해 주세요.",
            parse_mode=ParseMode.HTML,
        )
        return

    # 2열 배치
    rows = []
    for i in range(0, len(suggestions), 2):
        row = [InlineKeyboardButton(suggestions[i], callback_data=f"{cmd}|{suggestions[i]}")]
        if i + 1 < len(suggestions):
            row.append(InlineKeyboardButton(suggestions[i + 1], callback_data=f"{cmd}|{suggestions[i + 1]}"))
        rows.append(row)
    keyboard = InlineKeyboardMarkup(rows)
    await msg.edit_text(
        f"❌ <b>'{_e(query)}'</b> 기업을 찾을 수 없습니다.\n\n"
        "🔍 혹시 이 기업을 찾으셨나요?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def handle_suggest_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """추천 기업 버튼 클릭 시 해당 커맨드를 재실행합니다."""
    query = update.callback_query
    await query.answer()
    cmd, company = query.data.split("|", 1)

    await query.edit_message_text(
        f"⏳ <i>'{_e(company)}' 검색 중...</i>",
        parse_mode=ParseMode.HTML,
    )

    async def edit(text, **kw):
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, **kw)

    async def send_long(text):
        await query.delete_message()
        # update.effective_chat 사용
        chat_id = update.effective_chat.id
        chunks = []
        while len(text) > 4000:
            split = text.rfind("\n", 0, 4000)
            if split == -1:
                split = 4000
            chunks.append(text[:split])
            text = text[split:]
        chunks.append(text)
        for chunk in chunks:
            await ctx.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)

    if cmd == "analysis":
        data, status = await _get(f"/financials/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        await edit(fmt_analysis(data["company_name"], data["financials"], data.get("cached", False)))

    elif cmd == "business":
        data, status = await _get(f"/business/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        await edit(fmt_business(data.get("company_name", company), data.get("sections", [])))

    elif cmd == "dividend":
        data, status = await _get(f"/dividend-data/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        await edit(fmt_dividend(data["company_name"], data["dividend_data"]))

    elif cmd == "profit":
        await _send_profit_chart(query.message, company)

    elif cmd == "health":
        data, status = await _get(f"/financials/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        await edit(fmt_financial_health(data["company_name"], data["financials"]))

    elif cmd == "valuation":
        data, status = await _get(f"/valuation/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        text = (
            f"💹 <b>{_e(data['company_name'])} 밸류에이션</b>\n\n"
            + _md_to_html(data.get("valuation_text", ""))
        )
        await edit(text)

    elif cmd == "score":
        data, status = await _get(f"/score/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        name = _e(data["company_name"])
        score = data["total_score"]
        grade = data["total_grade"]
        cat_labels = {
            "growth": "성장성", "profitability": "수익성",
            "financial_health": "재무건전성", "dividend": "배당",
            "valuation": "밸류에이션",
        }
        lines = [f"📊 <b>{name} 정량 투자 스코어</b>\n", f"<b>종합: {score}점 / 100 ({grade})</b>\n" if score is not None else "<b>종합: 평가 불가</b>\n"]
        for key, cat in data.get("categories", {}).items():
            if cat['score'] is None:
                lines.append(f"  {cat_labels.get(key, key)}: 평가 불가")
                continue
            bar = "█" * round(cat["score"] / 10) + "░" * (10 - round(cat["score"] / 10))
            label = cat_labels.get(key, key)
            lines.append(f"  {label}: {bar} {cat['score']}점 ({cat['grade']})")
        signals = data.get("key_signals", [])
        if signals:
            lines.append("\n<b>핵심 시그널</b>")
            for s in signals:
                icon = "🟢" if s["type"] == "positive" else "🔴" if s["type"] == "negative" else "🟡"
                lines.append(f"  {icon} {s['text']}")
        await edit("\n".join(lines))

    elif cmd == "insider":
        ctx.application.create_task(_send_insider_chart(query.message, company), update=update)

    elif cmd in ("report", "buffett"):
        endpoint = {"report": "report", "buffett": "buffett-report"}[cmd]
        data, status = await _get(f"/{endpoint}/{company}")
        if status != 200:
            await edit(f"❌ {_e(data.get('detail', '조회 실패'))}")
            return
        if cmd == "report":
            text = f"🤖 <b>{_e(data['company_name'])} AI 종합 리포트</b>\n\n" + _md_to_html(data.get("report", ""))
        else:
            text = f"🧙 <b>{_e(data['company_name'])} 워렌 버핏 스타일 리포트</b>\n\n" + _md_to_html(data.get("report", ""))
        await send_long(text)


# -------------------------------------------------------------------
# 커맨드 핸들러
# -------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 <b>DART 재무분석 봇</b>에 오신 것을 환영합니다.\n"
        "공시 데이터 기반으로 기업 분석을 제공합니다.\n\n"
        "<b>── 기업 분석 ──</b>\n"
        "📋 /analysis [회사명] — 종합 분석 요약\n"
        "🏢 /business [회사명] — 사업의 내용\n"
        "📊 /dividend [회사명] — 5개년 배당금\n"
        "📈 /profit [회사명]   — 최근 3년 분기별 수익성 그래프\n"
        "🏦 /health [회사명]   — 재무 건전성\n"
        "💹 /valuation [회사명] — 밸류에이션 지표\n\n"
        "<b>── AI 분석 ──</b>\n"
        "🤖 /ask [질문] — 일반 AI 질문\n"
        "🖥 /ai — 모델·GPU 상태\n"
        "🤖 /report [회사명]  — AI 종합 투자 리포트\n"
        "🧙 /buffett [회사명] — 워렌 버핏 스타일 리포트\n"
        "📊 /score [회사명]   — 정량 투자 스코어 (0~100)\n"
        "🕵️ /insider [회사명] — 최근 3개년 매수·매도 그래프\n"
        "💬 /chat [회사명]    — AI 상담 시작\n"
        "          /end       — 상담 종료\n\n"
        "<b>── GitHub 핫 프로젝트 ──</b>\n"
        "🔥 /today — 오늘의 프로젝트 최대 3개\n"
        "🔔 /trend_on — 매일 09:00 KST 소개 신청 (개인 채팅)\n"
        "🔕 /trend_off — 소개 알림 해제\n\n"
        "<b>── 즐겨찾기 ──</b>\n"
        "⭐ /fav_add [회사명] [dividend|profit|health]\n"
        "🗑 /fav_del [회사명] [dividend|profit|health]\n"
        "📋 /favs — 내 즐겨찾기 목록\n\n"
        "<i>즐겨찾기 등록 시 매일 오전 9시(KST) 요약 알림을 받습니다.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_analysis(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /analysis [회사명]\n예: /analysis 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 종합 분석 중...</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/financials/{company}")
    if status != 200:
        await _show_suggestions(msg, company, "analysis")
        return
    text = fmt_analysis(data["company_name"], data["financials"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_business(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /business [회사명]\n예: /business 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 사업 분석 중... (최대 30초 소요)</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/business-overview/{company}")
    if status != 200:
        await _show_suggestions(msg, company, "business")
        return
    text = fmt_business_text(
        data["company_name"], data.get("sections", []), data.get("cached", False)
    )
    await msg.delete()
    await _send_long(update, text)


async def cmd_dividend(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /dividend [회사명]\n예: /dividend 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 배당 데이터 조회 중...</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/dividend-data/{company}")
    if status != 200:
        await _show_suggestions(msg, company, "dividend")
        return
    text = fmt_dividend(data["company_name"], data["dividend_data"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_profitability(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """최근 12분기 수익성·성장성을 그래프로 전송합니다."""
    if not ctx.args:
        await update.message.reply_text("사용법: /profit [회사명]\n예: /profit 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 수익성 데이터 조회 중...</i>", parse_mode=ParseMode.HTML
    )
    await _send_profit_chart(msg, company)


async def _send_profit_chart(msg, company: str) -> None:
    """직접 명령과 추천 기업 버튼에 동일한 그래프 응답을 제공합니다."""
    try:
        data, status = await _get(f"/profit-quarterly/{company}")
        if status == 404:
            await _show_suggestions(msg, company, "profit")
            return
        if status != 200:
            await msg.edit_text(f"❌ {_e(data.get('detail', '분기 실적 조회 실패'))}", parse_mode=ParseMode.HTML)
            return
        rows = data['financials']
        name = data['company_name']
        image = await asyncio.to_thread(render_profit_chart, name, rows)
        caption = (
            f"📈 <b>{_e(name)} 최근 3년 분기별 수익성·성장성</b>\n"
            f"{_e(rows[0]['label'])} ~ {_e(rows[-1]['label'])}\n"
            "① 매출·영업이익 (억원) ② 영업이익률 (%)\n"
            "③ 매출 성장률 (전년 동기 대비 %)\n"
            "출처: DART · 4분기 = 연간 − 3분기 누적\n"
            "빈 구간은 데이터 부족이며 0을 뜻하지 않습니다."
        )
        if len({r['fs_div'] for r in rows if r.get('fs_div')}) > 1:
            caption += '\n⚠️ 연결·개별 기준 혼재: 기준이 다른 분기의 성장률은 표시하지 않습니다.'
        with image:
            await msg.reply_photo(photo=image, caption=caption, parse_mode=ParseMode.HTML)
        await msg.delete()
    except Exception as exc:
        logging.getLogger(__name__).warning('분기 그래프 처리 실패 (%s)', type(exc).__name__)
        await msg.edit_text('분기 그래프를 생성하거나 전송하지 못했습니다. 잠시 후 /profit 명령을 다시 입력해주세요.')


async def cmd_financial_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /health [회사명]\n예: /health 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 재무 건전성 데이터 조회 중...</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/financials/{company}")
    if status != 200:
        await _show_suggestions(msg, company, "health")
        return
    text = fmt_financial_health(data["company_name"], data["financials"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_valuation(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /valuation [회사명]\n예: /valuation 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 밸류에이션 조회 중...</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/valuation/{company}")
    if status != 200:
        await _show_suggestions(msg, company, "valuation")
        return
    text = fmt_valuation(data["company_name"], data, data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /report [회사명]\n예: /report 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' AI 리포트 생성 중... (최대 60초 소요)</i>",
        parse_mode=ParseMode.HTML,
    )
    data, status = await _get(f"/report/{company}", timeout=AI_HTTP_TIMEOUT)
    if status != 200:
        await _show_suggestions(msg, company, "report")
        return
    header = f"🤖 <b>{_e(data['company_name'])} AI 종합 투자 리포트</b>\n\n"
    body = _md_to_html(data.get("report", ""))
    await msg.delete()
    await _send_long(update, header + body)


async def cmd_buffett_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /buffett [회사명]\n예: /buffett 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 버핏 리포트 생성 중... (최대 60초 소요)</i>",
        parse_mode=ParseMode.HTML,
    )
    data, status = await _get(f"/buffett-report/{company}", timeout=AI_HTTP_TIMEOUT)
    if status != 200:
        await _show_suggestions(msg, company, "buffett")
        return
    header = f"🧙 <b>{_e(data['company_name'])} 워렌 버핏 스타일 리포트</b>\n\n"
    body = _md_to_html(data.get("report", ""))
    await msg.delete()
    await _send_long(update, header + body)


# -------------------------------------------------------------------
# 투자 스코어
# -------------------------------------------------------------------

async def cmd_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """정량 투자 스코어 조회. /score [회사명]"""
    if not ctx.args:
        await update.message.reply_text("사용법: /score [회사명]\n예: /score 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 투자 스코어 계산 중...</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/score/{company}")
    if status != 200:
        await _show_suggestions(msg, company, "score")
        return

    name = _e(data["company_name"])
    score = data["total_score"]
    grade = data["total_grade"]

    cat_labels = {
        "growth": "성장성", "profitability": "수익성",
        "financial_health": "재무건전성", "dividend": "배당",
        "valuation": "밸류에이션",
    }
    lines = [f"📊 <b>{name} 정량 투자 스코어</b>\n"]
    lines.append(f"<b>종합: {score}점 / 100 ({grade})</b>\n" if score is not None else "<b>종합: 데이터 부족 — 평가 불가</b>\n")

    for key, cat in data.get("categories", {}).items():
        if cat['score'] is None:
            lines.append(f"  {cat_labels.get(key, key)}: 평가 불가")
            continue
        bar = "█" * round(cat["score"] / 10) + "░" * (10 - round(cat["score"] / 10))
        label = cat_labels.get(key, key)
        lines.append(f"  {label}: {bar} {cat['score']}점 ({cat['grade']})")

    signals = data.get("key_signals", [])
    if signals:
        lines.append("\n<b>핵심 시그널</b>")
        for s in signals:
            icon = "🟢" if s["type"] == "positive" else "🔴" if s["type"] == "negative" else "🟡"
            lines.append(f"  {icon} {s['text']}")

    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


# -------------------------------------------------------------------
# 내부자 거래 현황
# -------------------------------------------------------------------

async def cmd_insider(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """최근 3개년 내부자 매수·매도 추이를 그래프로 제공합니다."""
    if not ctx.args:
        await update.message.reply_text("사용법: /insider [회사명]\n예: /insider 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 최근 3개년 내부자 공시 원문을 확인 중입니다. 최초 조회는 수 분 걸릴 수 있습니다.</i>",
        parse_mode=ParseMode.HTML,
    )
    ctx.application.create_task(_send_insider_chart(msg, company), update=update)


async def _send_insider_chart(msg, company: str) -> None:
    """원문에서 확인한 매매 수량 그래프와 연간 합계를 전송합니다."""
    try:
        data, status = await _get(f"/insider-trend/{company}", timeout=INSIDER_REQUEST_TIMEOUT)
        if status == 404:
            await _show_suggestions(msg, company, 'insider')
            return
        if status != 200:
            await msg.edit_text(f"❌ {_e(data.get('detail', '내부자 공시 조회 실패'))}", parse_mode=ParseMode.HTML)
            return
        caption = [f"🕵️ <b>{_e(data['company_name'])} 내부자 주식 매수·매도</b>",
                   f"{data['start_date']} ~ {data['end_date']} · 거래일 기준"]
        for row in data['annual']:
            buy = f"{row['buy']:,}주" if row['buy'] is not None else '미확인'
            sell = f"{row['sell']:,}주" if row['sell'] is not None else '미확인'
            caption.append(f"{row['year']}년{' (진행 중)' if row['partial_year'] else ''}: 매수 {buy} / 매도 {sell}")
        caption.extend([
            f"출처: DART 최종 공시 {data['filings_parsed']:,}/{data['filings_total']:,}건 확인",
            '주식 매수·매도 사유가 명시된 건만 합산 · 증여·상속·보상 등 제외',
        ])
        if not data['coverage_complete']:
            caption.append(f"⚠️ 원문 {data['filings_failed']}건·행 {data['invalid_rows']}건 미확인. 수량은 확인분만의 하한입니다.")
        if data.get('refresh_failed'):
            caption.append('⚠️ DART 연결 실패로 마지막 수집 시점의 결과를 표시합니다.')
        caption.append(f"<a href=\"{_e(data['recent_sources'][-1]['url'])}\">최근 공시 원문</a>")
        image = await asyncio.to_thread(render_insider_chart, data)
        with image:
            await msg.reply_photo(photo=image, caption='\n'.join(caption), parse_mode=ParseMode.HTML)
        await msg.delete()
    except Exception as exc:
        logging.getLogger(__name__).warning('내부자 그래프 처리 실패 (%s)', type(exc).__name__)
        await msg.edit_text('내부자 그래프를 가져오지 못했습니다. 공시가 많은 기업은 최초 수집에 시간이 걸립니다. 잠시 후 /insider 명령을 다시 입력해주세요.')


# -------------------------------------------------------------------
# AI 상담 (ConversationHandler)
# -------------------------------------------------------------------

async def cmd_ai(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """현재 AI 모델과 GPU 적재 상태를 표시합니다."""
    try:
        data, status = await _get('/ai/status')
        if status != 200:
            raise RuntimeError('status')
        state = '연결됨' if data.get('available') else '연결되지 않음'
        gpu = data.get('gpu_bytes', 0)
        detail = f'GPU 메모리: {gpu / 1024 ** 3:.2f} GiB' if gpu else 'GPU: 현재 적재된 모델 없음'
        await update.message.reply_text(
            f"AI: {_e(data.get('provider'))}\n모델: {_e(data.get('model'))}\n상태: {state}\n{detail}",
            parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text('AI 상태를 확인하지 못했습니다. 서버 연결을 확인해주세요.')


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """기업 조회 없이 일반 질문을 AI에 전달합니다."""
    question = ' '.join(ctx.args).strip()
    if not question or len(question) > AI_MAX_QUESTION_CHARS:
        await update.message.reply_text(f'사용법: /ask 영업이익률이 뭐야?\n질문은 {AI_MAX_QUESTION_CHARS}자 이내로 입력해주세요.')
        return
    previous = ctx.user_data.get('ask_task')
    if previous and not previous.done():
        await update.message.reply_text('앞선 질문에 답변하는 중입니다. 잠시 기다려주세요.')
        return
    pending = await update.message.reply_text('⏳ AI 답변 생성 중...')

    async def respond() -> None:
        try:
            data, status = await _post('/ask', {'message': question})
            if status != 200:
                await pending.edit_text(str(data.get('detail', 'AI 응답 생성에 실패했습니다.')))
                return
            await pending.delete()
            await _send_long(update, _md_to_html(data['answer']))
        except Exception:
            await pending.edit_text('AI 연결에 실패했습니다. /ai로 상태를 확인해주세요.')
        finally:
            ctx.user_data.pop('ask_task', None)

    ctx.user_data['ask_task'] = ctx.application.create_task(respond(), update=update)


async def cmd_chat_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """AI 상담 시작. /chat [회사명]"""
    if not ctx.args:
        await update.message.reply_text(
            "사용법: /chat [회사명]\n예: /chat 삼성전자\n\n상담 종료: /end"
        )
        return ConversationHandler.END

    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 공시 데이터 불러오는 중...</i>", parse_mode=ParseMode.HTML
    )
    # 기업 유효성 확인
    data, status = await _get(f"/financials/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '기업을 찾을 수 없습니다.'))}", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    resolved = data.get("company_name", company)
    ctx.user_data["chat_company"] = resolved
    ctx.user_data["chat_history"] = []

    await msg.edit_text(
        f"💬 <b>{_e(resolved)} AI 상담</b>\n\n"
        "DART 공시 데이터와 워렌 버핏의 투자 철학을 바탕으로 답변드립니다.\n"
        "무엇이든 질문해 보세요!\n\n"
        "<i>상담 종료: /end</i>",
        parse_mode=ParseMode.HTML,
    )
    return CHAT_ACTIVE


async def handle_chat_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """CHAT_ACTIVE 상태에서 사용자 메시지 처리."""
    company = ctx.user_data.get("chat_company", "")
    history = ctx.user_data.get("chat_history", [])
    user_msg = update.message.text.strip()

    typing_msg = await update.message.reply_text(
        "⏳ <i>공시 근거를 찾고 답변을 작성하고 있습니다. 첫 질문은 색인 준비로 시간이 더 걸릴 수 있습니다.</i>", parse_mode=ParseMode.HTML
    )

    payload = {
        "message": user_msg,
        "history": history,
        "mode": "buffett",
    }
    data, status = await _post(f"/chat/{company}", payload)

    if status != 200:
        await typing_msg.edit_text(
            f"❌ {_e(data.get('detail', '오류가 발생했습니다.'))}", parse_mode=ParseMode.HTML
        )
        return CHAT_ACTIVE

    answer = data.get("answer", "")

    # 대화 이력 갱신 (마지막 10턴만 유지)
    history.append({"role": "user",  "text": user_msg})
    history.append({"role": "model", "text": answer})
    ctx.user_data["chat_history"] = history[-30:]

    await typing_msg.delete()
    await _send_long(update, _md_to_html(answer))
    return CHAT_ACTIVE


async def cmd_chat_end(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """AI 상담 종료."""
    company = ctx.user_data.pop("chat_company", "")
    ctx.user_data.pop("chat_history", None)
    name = f"'{_e(company)}' " if company else ""
    await update.message.reply_text(
        f"💬 {name}AI 상담이 종료되었습니다. 또 궁금한 점이 있으면 언제든지 /chat 으로 시작하세요.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# -------------------------------------------------------------------
# 즐겨찾기 커맨드
# -------------------------------------------------------------------

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
            "즐겨찾기가 없습니다.\n/fav_add 명령어로 추가해보세요."
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
                        mg  = f"{latest['operating_margin']:.1f}%" if latest.get("operating_margin") else "N/A"
                        roe = f"{latest['roe']:.1f}%" if latest.get("roe") else "N/A"
                        return f"📈 <b>{_e(company)}</b> 영업이익률: {mg}, ROE: {roe} ({latest['year']}년)"
                    else:
                        debt = f"{latest['debt_ratio']:.1f}%" if latest.get("debt_ratio") else "N/A"
                        return f"🏦 <b>{_e(company)}</b> 부채비율: {debt} ({latest['year']}년)"
        except Exception as e:
            print(f"[알림] {company} 데이터 조회 오류: {e}")
        return None

    results = await asyncio.gather(
        *[_fetch_item(company, analysis_type) for company, analysis_type in items]
    )
    lines = ["🔔 <b>오늘의 즐겨찾기 현황</b>\n"] + [r for r in results if r]
    if len(lines) > 1:
        return user_id, "\n".join(lines)
    return user_id, None


async def send_filing_alerts(bot: Bot) -> None:
    """즐겨찾기 종목의 새 공시를 감지하여 사용자에게 알림을 발송합니다."""
    from services.dart import get_corp_code
    from services.filing_alert import check_new_filings, build_filing_alert_message
    from fastapi import HTTPException

    watched = await database.get_all_watched_companies()
    if not watched:
        return

    print(f"[공시알림] {len(watched)}개 종목 공시 체크 시작")

    for item in watched:
        company = item["company"]
        try:
            corp_code = await asyncio.to_thread(get_corp_code, company)
        except HTTPException:
            print(f"[공시알림] {company} 회사코드 조회 실패, 건너뜀")
            continue
        except Exception as e:
            print(f"[공시알림] {company} 회사코드 오류: {e}")
            continue

        try:
            new_filings = await check_new_filings(corp_code, company)
        except Exception as e:
            print(f"[공시알림] {company} 공시 체크 오류: {e}")
            continue

        if not new_filings:
            continue

        user_ids = await database.get_users_watching_company(company)
        print(f"[공시알림] {company} 새 공시 {len(new_filings)}건 → {len(user_ids)}명에게 발송")

        for filing in new_filings:
            try:
                text = await build_filing_alert_message(company, filing)
            except Exception as e:
                print(f"[공시알림] {company} 메시지 생성 오류: {e}")
                continue

            for user_id in user_ids:
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    print(f"[공시알림] user {user_id} 발송 오류: {e}")

    print("[공시알림] 공시 체크 완료")


async def send_daily_notification(bot: Bot) -> None:
    grouped = await database.get_all_favorites_grouped()
    if not grouped:
        return
    print(f"[알림] {len(grouped)}명에게 일일 알림 발송 시작")
    messages = await asyncio.gather(
        *[_build_user_message(user_id, items) for user_id, items in grouped.items()]
    )
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

async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """현재 채팅에 오늘의 GitHub 소개를 발송합니다."""
    chat_id = update.effective_chat.id
    try:
        await deliver_trending(ctx.bot, chat_id, scheduled=False)
    except Exception as exc:
        logging.getLogger(__name__).warning("GitHub 조회/발송 실패 (%s)", type(exc).__name__)
        await update.effective_message.reply_text("GitHub 소개를 가져오지 못했습니다. 잠시 후 /today를 다시 입력해주세요.")


async def cmd_trend_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """개인 채팅에서 GitHub 정기 소개를 신청합니다."""
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("정기 소개 신청은 봇과의 개인 채팅에서 /trend_on을 입력해주세요.")
        return
    await database.set_trending_subscription(update.effective_chat.id, True)
    await update.effective_message.reply_text("매일 오전 9시(KST) GitHub 핫 프로젝트를 소개합니다. /today로 바로 보기 · /trend_off로 해제")


async def cmd_trend_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """현재 개인 채팅의 GitHub 정기 소개를 해제합니다."""
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("봇과의 개인 채팅에서 /trend_off를 입력해주세요.")
        return
    await database.set_trending_subscription(update.effective_chat.id, False)
    await update.effective_message.reply_text("GitHub 정기 소개를 해제했습니다. /today는 계속 사용할 수 있습니다.")


async def deliver_trending(bot: Bot, chat_id: int, *, scheduled: bool) -> None:
    """채팅별 발송을 직렬화하고 성공한 경우에만 중복 제외 기록을 남깁니다."""
    async with github_trending.chat_lock(chat_id):
        now = github_trending.now_kst()
        if scheduled and await database.trending_was_delivered(chat_id, now.date().isoformat()):
            return
        digest = await github_trending.build_digest(chat_id, now)
        await bot.send_message(chat_id=chat_id, text=github_trending.format_digest(digest),
                               parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await database.mark_trending_delivered(chat_id, digest['day'],
                                               [p['name'] for p in digest['projects']])


async def send_trending_notifications(bot: Bot) -> None:
    """오전 9시 이후 신청자에게 미발송 소개를 전송하며 실패는 다음 실행에 재시도합니다."""
    now = github_trending.now_kst()
    if (now.hour, now.minute) < (TRENDING_SEND_HOUR, TRENDING_SEND_MINUTE):
        return
    for chat_id in await database.get_trending_subscribers():
        try:
            await deliver_trending(bot, chat_id, scheduled=True)
        except Forbidden:
            await database.set_trending_subscription(chat_id, False)
            logging.getLogger(__name__).info("GitHub 구독 해제: 봇 접근이 거부된 채팅")
        except Exception as exc:
            logging.getLogger(__name__).warning("GitHub 정기 발송 실패 (%s)", type(exc).__name__)


async def register_bot_commands(bot: Bot) -> None:
    """슬래시 자동완성 설명과 명령어 메뉴 버튼을 텔레그램에 등록합니다."""
    commands = [BotCommand(command, description) for command, description in TELEGRAM_COMMANDS]
    for language in (None, 'ko', 'en'):
        await bot.set_my_commands(commands, language_code=language)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def create_bot_application() -> Application:
    token = TELEGRAM_BOT_TOKEN
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")

    app = Application.builder().token(token).build()

    # AI 상담 ConversationHandler (다른 핸들러보다 먼저 등록)
    chat_conv = ConversationHandler(
        entry_points=[CommandHandler("chat", cmd_chat_start)],
        states={
            CHAT_ACTIVE: [
                CommandHandler("end", cmd_chat_end),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_message),
            ],
        },
        fallbacks=[CommandHandler("end", cmd_chat_end)],
        per_user=True,
        per_chat=True,
    )
    app.add_handler(chat_conv)

    # GitHub 소개
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("trend_on", cmd_trend_on))
    app.add_handler(CommandHandler("trend_off", cmd_trend_off))

    # 기업 분석
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_start))
    app.add_handler(CommandHandler("analysis",  cmd_analysis))
    app.add_handler(CommandHandler("business",  cmd_business))
    app.add_handler(CommandHandler("dividend",  cmd_dividend))
    app.add_handler(CommandHandler("profit",    cmd_profitability))
    app.add_handler(CommandHandler("health",    cmd_financial_health))
    app.add_handler(CommandHandler("valuation", cmd_valuation))

    # AI 분석
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CommandHandler("buffett",   cmd_buffett_report))
    app.add_handler(CommandHandler("score",     cmd_score))
    app.add_handler(CommandHandler("ask",       cmd_ask))
    app.add_handler(CommandHandler("ai",        cmd_ai))
    app.add_handler(CommandHandler("insider",   cmd_insider))

    # 즐겨찾기
    app.add_handler(CommandHandler("fav_add",   cmd_add_favorite))
    app.add_handler(CommandHandler("fav_del",   cmd_remove_favorite))
    app.add_handler(CommandHandler("favs",      cmd_list_favorites))

    # 유사 기업 추천 버튼 콜백
    app.add_handler(CallbackQueryHandler(handle_suggest_callback))

    # help 텍스트 입력 시 도움말
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(help|/)$"), cmd_start))

    # 이스터에그
    async def _easter_egg(u, c):
        import random
        if random.random() < 0.05:
            await u.message.reply_text("😤 싫어요!")
        else:
            await u.message.reply_text(random.choice([
                "🐰 통통이 메롱~",
                "😏 조치~",
                "😊 좋지~~",
                "🥰 좋지요~",
                "😄 조치~~ ^___^",
            ]))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^ㅅㅅ$"), _easter_egg))

    return app
