"""지금이니! 관심종목의 시세와 설명 가능한 가격 조건을 확인합니다."""
import asyncio
import html
import logging
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo

import yfinance as yf

import config
from cache import timing_cache
from utils import fmt_krw

notification_lock = asyncio.Lock()


def parse_registration(args: list[str]) -> tuple[str, float | None]:
    """회사명과 선택 목표가를 해석하고 유효하지 않은 가격을 거부합니다."""
    if not args:
        raise ValueError('사용법: /timing [회사명 또는 종목코드] [목표가]\n예: /timing 삼성전자 또는 /timing 005930 70,000')
    target = None
    company_args = args
    if len(args) > 1:
        token = args[-1].replace(',', '').removesuffix('원')
        if token.lower() == 'auto':
            company_args = args[:-1]
        else:
            try:
                target = float(token)
            except ValueError:
                # 공백이 들어간 회사명은 전체를 검색어로 유지합니다.
                pass
            else:
                if not math.isfinite(target) or target <= 0:
                    raise ValueError('목표가는 0보다 큰 유한한 원화 금액을 입력해주세요.')
                company_args = args[:-1]
    company = ' '.join(company_args).strip()
    if not company:
        raise ValueError('회사명 또는 6자리 종목코드를 입력해주세요.')
    return company, target


def now_kst() -> datetime:
    """가격 확인 기준시각을 한국 시간으로 반환합니다."""
    return datetime.now(ZoneInfo(config.TIMING_TIMEZONE))


def is_market_hours(now: datetime) -> bool:
    """평일 정규장 시간인지 확인하며 휴장 여부는 당일 시세로 추가 검증합니다."""
    local = now.astimezone(ZoneInfo(config.TIMING_TIMEZONE))
    return (local.weekday() < 5
            and time(*config.TIMING_MARKET_OPEN) <= local.time() <= time(*config.TIMING_MARKET_CLOSE))


def calculate_rsi(closes: list[float]) -> float | None:
    """종가에 Wilder 평활을 적용한 RSI를 계산하며 자료 부족은 None으로 반환합니다."""
    period = config.TIMING_RSI_PERIOD
    if len(closes) <= period or any(not math.isfinite(p) or p <= 0 for p in closes):
        return None
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(change, 0) for change in changes[:period]) / period
    loss = sum(max(-change, 0) for change in changes[:period]) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0)) / period
        loss = (loss * (period - 1) + max(-change, 0)) / period
    if loss == 0:
        return 50.0 if gain == 0 else 100.0
    return 100 - 100 / (1 + gain / loss)


def is_fresh_quote(snapshot: dict, now: datetime) -> bool:
    """양수 가격·거래량과 당일 시세 기준시각을 검증해 오래된 가격을 제외합니다."""
    try:
        quote_at = datetime.fromisoformat(snapshot['quote_at'])
        if quote_at.tzinfo is None:
            return False
        local = now.astimezone(ZoneInfo(config.TIMING_TIMEZONE))
        quote_at = quote_at.astimezone(local.tzinfo)
        age = (local - quote_at).total_seconds()
        price = float(snapshot['price'])
        volume = float(snapshot['volume'])
        return (math.isfinite(price) and price > 0 and math.isfinite(volume) and volume > 0
                and quote_at.date() == local.date()
                and time(*config.TIMING_MARKET_OPEN) <= quote_at.time() <= time(*config.TIMING_MARKET_CLOSE)
                and 0 <= age <= config.TIMING_MAX_QUOTE_AGE_SECONDS)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _fetch_snapshot(stock_code: str) -> dict:
    for suffix in config.TIMING_TICKER_SUFFIXES:
        symbol = stock_code + suffix
        try:
            ticker = yf.Ticker(symbol)
            quotes = ticker.history(
                period=config.TIMING_QUOTE_PERIOD, interval=config.TIMING_QUOTE_INTERVAL,
                auto_adjust=False, actions=False, prepost=False, timeout=config.TIMING_HTTP_TIMEOUT)
            if quotes.empty:
                continue
            quotes = quotes.sort_index()
            valid = quotes[(quotes['Close'] > 0) & (quotes['Volume'] > 0)]
            if valid.empty:
                continue
            row = valid.iloc[-1]
            quote_at = valid.index[-1].to_pydatetime()
            snapshot = {'stock_code': stock_code, 'symbol': symbol, 'price': float(row['Close']),
                        'volume': float(row['Volume']), 'quote_at': quote_at.isoformat(),
                        'rsi': None, 'ma': None, 'history_through': None}
        except Exception as exc:
            logging.getLogger(__name__).warning('가격 조회 실패 %s (%s)', symbol, type(exc).__name__)
            continue

        # 목표가 알림은 일봉 자료가 없어도 유효한 최신 가격으로 동작합니다.
        try:
            history = ticker.history(
                period=config.TIMING_HISTORY_PERIOD, interval=config.TIMING_HISTORY_INTERVAL,
                auto_adjust=True, actions=False, timeout=config.TIMING_HTTP_TIMEOUT)
            if history.empty or quote_at.tzinfo is None:
                return snapshot
            dates = history.index.tz_convert(config.TIMING_TIMEZONE).date
            quote_day = quote_at.astimezone(ZoneInfo(config.TIMING_TIMEZONE)).date()
            completed = history[dates < quote_day].sort_index()
            completed = completed[~completed.index.duplicated(keep='last')]
            closes = [float(p) for p in completed['Close']]
            closes.append(snapshot['price'])  # 당일 진행 중인 일봉은 최신 5분봉 종가로 한 번만 반영합니다.
            if len(closes) >= config.TIMING_MA_PERIOD and all(math.isfinite(p) and p > 0 for p in closes):
                snapshot.update(
                    rsi=calculate_rsi(closes),
                    ma=sum(closes[-config.TIMING_MA_PERIOD:]) / config.TIMING_MA_PERIOD,
                    history_through=completed.index[-1].date().isoformat())
        except Exception as exc:
            logging.getLogger(__name__).warning('일봉 조회 실패 %s (%s)', symbol, type(exc).__name__)
        return snapshot
    raise ValueError('시세를 조회하지 못했습니다.')


async def get_price_snapshot(company: str, stock_code: str) -> dict:
    """회사명 원문 키로 시세를 짧게 캐시하고 블로킹 수집은 스레드에서 실행합니다."""
    async with timing_cache.lock(company):
        cached = await timing_cache.get(company)
        if cached is not None and cached.get('stock_code') == stock_code:
            return {**cached, 'cached': True}
        result = await asyncio.to_thread(_fetch_snapshot, stock_code)
        await timing_cache.set(company, result)
        return {**result, 'cached': False}


async def collect_snapshots(watches: list[dict]) -> dict[str, dict | None]:
    """같은 종목은 한 번만 수집하고 외부 호출 동시 수를 제한합니다."""
    companies = {watch['stock_code']: watch['company'] for watch in watches}
    semaphore = asyncio.Semaphore(config.TIMING_FETCH_CONCURRENCY)

    async def fetch(code: str, company: str) -> tuple[str, dict | None]:
        async with semaphore:
            try:
                return code, await get_price_snapshot(company, code)
            except Exception as exc:
                logging.getLogger(__name__).warning('시세 확인 실패 %s (%s)', code, type(exc).__name__)
                return code, None

    return dict(await asyncio.gather(*(fetch(code, name) for code, name in companies.items())))


def evaluate_watch(watch: dict, snapshot: dict | None, now: datetime) -> str:
    """목표가 또는 RSI·이동평균 조건을 판정하며 자료 부족을 매수 신호로 취급하지 않습니다."""
    if snapshot is None:
        return 'unavailable'
    if not is_fresh_quote(snapshot, now):
        return 'stale'
    target = watch['target_price']
    if target is not None:
        return 'matched' if snapshot['price'] <= target else 'not_matched'
    rsi, ma = snapshot.get('rsi'), snapshot.get('ma')
    if (rsi is None or ma is None or not math.isfinite(rsi) or not math.isfinite(ma)
            or not 0 <= rsi <= 100 or ma <= 0):
        return 'insufficient_data'
    return ('matched' if rsi <= config.TIMING_RSI_THRESHOLD and snapshot['price'] <= ma
            else 'not_matched')


def describe_condition(target_price: float | None) -> str:
    """사용자에게 실제 적용할 가격 조건을 설명합니다."""
    if target_price is not None:
        return f'목표가 {fmt_krw(target_price)} 이하'
    return (f'RSI({config.TIMING_RSI_PERIOD}) ≤ {config.TIMING_RSI_THRESHOLD} + '
            f'가격 ≤ {config.TIMING_MA_PERIOD}일 평균가')


def build_alert_message(watch: dict, snapshot: dict) -> str:
    """가격·매수 검토 조건·시세 기준시각과 자료 출처를 HTML로 표시합니다."""
    quote_at = datetime.fromisoformat(snapshot['quote_at']).astimezone(ZoneInfo(config.TIMING_TIMEZONE))
    lines = [f"🔔 <b>지금이니! {html.escape(watch['company'])} ({html.escape(watch['stock_code'])})</b>",
             f"5분봉 종가: <b>{fmt_krw(snapshot['price'])}</b>",
             f"충족 조건: {describe_condition(watch['target_price'])}"]
    if watch['target_price'] is None:
        lines.extend([f"RSI: {snapshot['rsi']:.1f} · 평균가: {fmt_krw(snapshot['ma'])}",
                      f"일봉 기준: {snapshot['history_through']}까지의 수정 종가 + 당일 최신 가격"])
    lines.extend([f"시세 기준: {quote_at:%Y-%m-%d %H:%M} KST (5분봉 시작시각)",
                  f"출처: Yahoo Finance · {html.escape(snapshot['symbol'])} (지연 가능)",
                  '등록 조건에 따른 매수 검토 알림입니다. 수익이나 반등을 보장하지 않습니다.',
                  f"해제: /timing_del {html.escape(watch['stock_code'])}"])
    return '\n'.join(lines)
