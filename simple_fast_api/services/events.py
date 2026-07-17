"""주가 변곡점 이벤트 분석.

Naver 뉴스 검색 API로 최근 1년간의 실제 기사를 모으고, Groq LLM에게
그 기사들 중 밸류에이션·투자 내러티브 관점에서 유의미한 사건을 고르게 한다.
- 검색 자체는 AI가 하지 않는다(Naver가 실제 기사를 찾아옴) — 출처가 항상 진짜
  기사 링크이고, 사실무근 사건을 지어낼 여지가 없다.
- 사건 선정 기준은 밸류에이션/내러티브 중요도이지 주가 변동폭이 아니다. 이벤트
  날짜 전후 등락률은 참고 정보로만 계산해 붙인다(필터링·정렬에는 쓰지 않는다).
"""
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import yfinance as yf

from services.valuation import get_stock_code
from utils import search_naver_news, call_groq

MAX_EVENTS = 8
NEWS_PAGE_SIZE = 100        # Naver 뉴스 검색 1회 호출당 최대 결과 수
NEWS_MAX_PAGES = 10         # date순 페이지네이션 최대 횟수 (API 상한 start<=1000까지 전부 사용)
NEWS_LOOKBACK_DAYS = 365    # 최근 1년 이내 기사만 사용
MAX_ARTICLES_FOR_PROMPT = 80  # Groq 무료 티어 분당 토큰 한도(TPM 12,000)를 넘기지 않도록 제한
SUMMARY_MAX_CHARS = 70      # 프롬프트용 기사 요약 길이 제한 (토큰 절약)
PRICE_WINDOW_BEFORE = 1     # 이벤트 날짜 기준 참고용 가격 변동 계산 구간(거래일)
PRICE_WINDOW_AFTER = 3

CATEGORY_OPTIONS = "실적/밸류에이션/산업뉴스/규제/공급망/경쟁사/신사업/기타"

SELECTION_SYSTEM_INSTRUCTION = f"""당신은 한국 주식시장을 분석하는 애널리스트입니다.
아래는 특정 종목에 대한 최근 뉴스 기사 목록입니다(번호가 매겨져 있음).

이 중에서 기업의 밸류에이션(실적, 이익률, 성장성, 시장점유율, 신규 수주·계약 등)이나
투자 내러티브(산업 트렌드에서의 포지셔닝, 신사업, 경쟁 구도, 리스크 등)에 유의미한
영향을 줄 만한 사건을 선정하세요.

규칙:
- 반드시 주어진 기사 목록 안에서만 선택하세요. 목록에 없는 사건을 지어내지 마세요.
- "주가가 X% 올랐다/내렸다"는 결과를 보도하는 시황·마감 시황성 기사는 제외하세요.
- 그 사건이 주가에 즉각적인 영향을 줬는지 여부는 중요하지 않습니다. 밸류에이션이나
  내러티브 관점에서 의미가 크다고 판단되면, 주가 변동이 작거나 없었더라도 포함하세요.
  밸류에이션에 직접 관련된 뉴스는 단순 주가 등락 기사보다 우선적으로 포함하세요.
- 서로 다른 기사가 같은 사건을 다루면 하나로 묶고, article_indices에 관련된 기사
  번호를 모두 적으세요.
- 최대 {MAX_EVENTS}개, 중요도가 높은 순으로 정렬하세요.
- 다른 설명 없이 아래 JSON 형식으로만 답하세요.

{{"events": [{{"headline": "10자 내외 제목", "summary": "2문장 이내 설명", "category": "{CATEGORY_OPTIONS} 중 하나", "importance": "high 또는 medium", "article_indices": [1, 3]}}]}}"""


def _fetch_price_history(company_name: str):
    """1년치 일별 시세를 반환합니다. 상장 종목코드가 없으면 None."""
    stock_code = get_stock_code(company_name)
    if not stock_code:
        return None
    for suffix in ("KS", "KQ"):
        hist = yf.Ticker(f"{stock_code}.{suffix}").history(period="1y")
        if not hist.empty:
            return hist
    return None


def _serialize_prices(hist) -> list[dict]:
    """일별 종가 시계열을 [{date, close}] 형태로 직렬화합니다. 시세가 없으면 빈 리스트."""
    if hist is None or hist.empty:
        return []
    return [
        {"date": d.strftime("%Y-%m-%d"), "close": round(float(c), 2)}
        for d, c in zip(hist.index, hist["Close"])
        if c == c  # NaN 제외
    ]


def _price_change_near(hist, date_str: str | None) -> float | None:
    """이벤트 날짜 전후 거래일 등락률(참고용). 계산 불가 시 None."""
    if hist is None or hist.empty or not date_str:
        return None
    dates = [d.strftime("%Y-%m-%d") for d in hist.index]
    pos = next((i for i, d in enumerate(dates) if d >= date_str), len(dates) - 1)
    start_pos = max(0, pos - PRICE_WINDOW_BEFORE)
    end_pos = min(len(dates) - 1, pos + PRICE_WINDOW_AFTER)
    start_price = float(hist["Close"].iloc[start_pos])
    end_price = float(hist["Close"].iloc[end_pos])
    if start_price <= 0:
        return None
    return round((end_price - start_price) / start_price * 100, 1)


def _anchor_date_near(hist, date_str: str | None) -> str | None:
    """이벤트 날짜 이후 첫 거래일을 반환합니다(차트 마커 고정용). 매칭 불가 시 None."""
    if hist is None or hist.empty or not date_str:
        return None
    dates = [d.strftime("%Y-%m-%d") for d in hist.index]
    return next((d for d in dates if d >= date_str), dates[-1])


def _parse_json_object(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _parse_pub_date(pub_date: str):
    try:
        return parsedate_to_datetime(pub_date)
    except (TypeError, ValueError):
        return None


def _stratified_sample(items: list[dict], k: int) -> list[dict]:
    """items(최신순 정렬)에서 k개를 균등 간격으로 뽑는다.

    Groq 프롬프트 토큰 예산 때문에 기사 수를 줄여야 하는데, 단순히
    '최신 k개'만 남기면 페이지네이션으로 어렵게 확보한 과거 기사가 전부
    잘려나가 원래 겪었던 "최근 며칠로 수렴하는" 문제가 재발한다. 대신
    fetch된 전체 기간에 걸쳐 고르게 샘플링해 커버리지를 유지한다.
    """
    if len(items) <= k:
        return items
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


async def _gather_recent_articles(company_name: str) -> list[dict]:
    """date순 페이지네이션 + sim순 1페이지를 합쳐 최근 1년 이내 기사를 모은다.

    네이버 뉴스 검색은 종목별 보도량에 따라 실제로 닿는 과거 시점이 크게 다르다
    (삼성전자 같은 초대형주는 상위 1000건이 하루치도 안 되고, 중소형주는 1000건이
    1년 가까이 닿는다). 그래서 date순으로 여러 페이지를 끝까지 당겨보고, cutoff
    이전 기사가 나오면 더 당길 필요가 없으므로 중단한다.
    """
    # 네이버 API는 초당 요청 수 제한이 있어 순차 호출한다 (동시 호출 시 429 발생).
    page_starts = [p * NEWS_PAGE_SIZE + 1 for p in range(NEWS_MAX_PAGES) if p * NEWS_PAGE_SIZE + 1 <= 1000]
    date_articles: list[dict] = []
    for s in page_starts:
        batch = await search_naver_news(company_name, display=NEWS_PAGE_SIZE, start=s, sort="date")
        if not batch:
            break
        date_articles.extend(batch)
    relevant = await search_naver_news(company_name, display=NEWS_PAGE_SIZE, sort="sim")

    by_url: dict[str, dict] = {}
    for item in date_articles + relevant:
        if item.get("url"):
            by_url.setdefault(item["url"], item)

    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_LOOKBACK_DAYS)

    dated = []
    for item in by_url.values():
        parsed = _parse_pub_date(item["pub_date"])
        if parsed is None or parsed < cutoff:
            continue
        item["_parsed_date"] = parsed
        dated.append(item)

    dated.sort(key=lambda x: x["_parsed_date"], reverse=True)
    return _stratified_sample(dated, MAX_ARTICLES_FOR_PROMPT)


def _build_article_list_prompt(company_name: str, articles: list[dict]) -> str:
    lines = [f"{company_name} 관련 최근 뉴스 기사 목록:\n"]
    for i, a in enumerate(articles, start=1):
        date_str = a["_parsed_date"].strftime("%Y-%m-%d")
        summary = a["summary"][:SUMMARY_MAX_CHARS]
        lines.append(f"{i}. [{date_str}] {a['title']} — {summary}")
    return "\n".join(lines)


async def _select_events(company_name: str, articles: list[dict]) -> list[dict]:
    prompt = _build_article_list_prompt(company_name, articles)
    result = await call_groq(prompt, system_instruction=SELECTION_SYSTEM_INSTRUCTION)
    parsed = _parse_json_object(result)
    if not parsed:
        return []

    events = []
    for candidate in parsed.get("events", [])[:MAX_EVENTS]:
        indices = [i for i in candidate.get("article_indices", []) if 1 <= i <= len(articles)]
        if not indices:
            continue
        referenced = [articles[i - 1] for i in indices]
        referenced.sort(key=lambda a: a["_parsed_date"])
        earliest = referenced[0]

        events.append({
            "date": earliest["_parsed_date"].strftime("%Y-%m-%d"),
            "headline": candidate.get("headline", ""),
            "summary": candidate.get("summary", ""),
            "category": candidate.get("category", "기타"),
            "importance": candidate.get("importance", "medium"),
            "sources": [{"title": a["title"], "url": a["url"]} for a in referenced[:3]],
        })
    return events


async def analyze_price_events(company_name: str) -> dict:
    """종목의 밸류에이션·내러티브 관점 유의미 사건 목록을 반환합니다."""
    hist = _fetch_price_history(company_name)

    articles = await _gather_recent_articles(company_name)
    if not articles:
        return {"company_name": company_name, "events": [], "prices": _serialize_prices(hist)}

    events = await _select_events(company_name, articles)
    for e in events:
        e["pct_change"] = _price_change_near(hist, e.get("date"))
        e["anchor_date"] = _anchor_date_near(hist, e.get("date"))

    importance_rank = {"high": 0, "medium": 1, "low": 2}
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    events.sort(key=lambda e: importance_rank.get(e.get("importance", "medium"), 1))

    return {"company_name": company_name, "events": events, "prices": _serialize_prices(hist)}
