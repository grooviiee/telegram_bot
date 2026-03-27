"""
Telegram 봇 모듈.
- 커맨드 핸들러: /analysis, /business, /dividend, /profit, /health,
                 /valuation, /report, /buffett, /chat(/end),
                 /fav_add, /fav_del, /favs
- 알림 발송: send_daily_notification() (스케줄러에서 호출)
"""

import os
import re
import asyncio
import html
import aiohttp
from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

import database

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

async def _get(path: str) -> tuple[dict, int]:
    """로컬 FastAPI 서버에 GET 요청."""
    session = get_session()
    async with session.get(f"{API_BASE}{path}") as resp:
        return await resp.json(), resp.status


async def _post(path: str, payload: dict) -> tuple[dict, int]:
    """로컬 FastAPI 서버에 POST 요청."""
    session = get_session()
    async with session.post(f"{API_BASE}{path}", json=payload) as resp:
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
    if v is None:
        return "N/A"
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}조"
    if abs_v >= 100_000_000:
        return f"{sign}{abs_v / 100_000_000:.0f}억"
    return f"{sign}{abs_v:,.0f}원"


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
        "📈 /profit [회사명]   — 수익성 &amp; 성장성\n"
        "🏦 /health [회사명]   — 재무 건전성\n"
        "💹 /valuation [회사명] — 밸류에이션 지표\n\n"
        "<b>── AI 분석 ──</b>\n"
        "🤖 /report [회사명]  — AI 종합 투자 리포트\n"
        "🧙 /buffett [회사명] — 워렌 버핏 스타일 리포트\n"
        "💬 /chat [회사명]    — AI 상담 시작\n"
        "          /end       — 상담 종료\n\n"
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
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
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
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
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
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
        return
    text = fmt_dividend(data["company_name"], data["dividend_data"], data.get("cached", False))
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_profitability(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("사용법: /profit [회사명]\n예: /profit 삼성전자")
        return
    company = " ".join(ctx.args)
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 수익성 데이터 조회 중...</i>", parse_mode=ParseMode.HTML
    )
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
    msg = await update.message.reply_text(
        f"⏳ <i>'{_e(company)}' 재무 건전성 데이터 조회 중...</i>", parse_mode=ParseMode.HTML
    )
    data, status = await _get(f"/financials/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
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
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
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
    data, status = await _get(f"/report/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
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
    data, status = await _get(f"/buffett-report/{company}")
    if status != 200:
        await msg.edit_text(f"❌ {_e(data.get('detail', '조회 실패'))}", parse_mode=ParseMode.HTML)
        return
    header = f"🧙 <b>{_e(data['company_name'])} 워렌 버핏 스타일 리포트</b>\n\n"
    body = _md_to_html(data.get("report", ""))
    await msg.delete()
    await _send_long(update, header + body)


# -------------------------------------------------------------------
# AI 상담 (ConversationHandler)
# -------------------------------------------------------------------

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
        "⏳ <i>답변 생성 중...</i>", parse_mode=ParseMode.HTML
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

def create_bot_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
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

    # 기업 분석
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("analysis",  cmd_analysis))
    app.add_handler(CommandHandler("business",  cmd_business))
    app.add_handler(CommandHandler("dividend",  cmd_dividend))
    app.add_handler(CommandHandler("profit",    cmd_profitability))
    app.add_handler(CommandHandler("health",    cmd_financial_health))
    app.add_handler(CommandHandler("valuation", cmd_valuation))

    # AI 분석
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CommandHandler("buffett",   cmd_buffett_report))

    # 즐겨찾기
    app.add_handler(CommandHandler("fav_add",   cmd_add_favorite))
    app.add_handler(CommandHandler("fav_del",   cmd_remove_favorite))
    app.add_handler(CommandHandler("favs",      cmd_list_favorites))

    return app
