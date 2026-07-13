"""주가 변곡점 이벤트 분석.

과거에는 yfinance 급등락 구간을 먼저 찾고 그 원인을 역추적했지만, 이 방식은
"주가는 크게 안 움직였지만 밸류에이션·투자 내러티브 관점에서는 중요한 사건"을
놓친다. 그래서 지금은 순서를 뒤집는다:

1. 발견(discovery) — Gemini + Google Search grounding으로 최근 1년간
   밸류에이션/내러티브에 유의미한 사건을 먼저 찾는다. 주가 변동 여부는
   조건이 아니다.
2. 검증(verify) — 각 사건을 개별적으로 다시 검색해 사실 확인 + 출처를 확보한다.
3. 가격 컨텍스트 — 이벤트 날짜 전후 등락률은 참고 정보로만 계산해 붙인다
   (필터링이나 정렬 기준으로 쓰지 않는다).
"""
import json
import re

import yfinance as yf

from config import GEMINI_EVENT_CONFIG, GEMINI_EVENT_DISCOVERY_CONFIG
from services.valuation import get_stock_code
from utils import call_gemini_with_search

MAX_EVENTS = 8
PRICE_WINDOW_BEFORE = 1  # 이벤트 날짜 기준 참고용 가격 변동 계산 구간(거래일)
PRICE_WINDOW_AFTER = 3

CATEGORY_OPTIONS = "실적/밸류에이션/산업뉴스/규제/공급망/경쟁사/신사업/기타"

DISCOVERY_SYSTEM_INSTRUCTION = f"""당신은 한국 주식시장을 분석하는 애널리스트입니다.
특정 종목에 대해 최근 1년간 있었던 사건 중, 기업의 밸류에이션(실적, 이익률, 성장성,
시장점유율, 신규 수주·계약 등)이나 투자 내러티브(산업 트렌드에서의 포지셔닝, 신사업,
경쟁 구도, 리스크 등)에 유의미한 영향을 줄 만한 사건을 찾아 나열하세요.

규칙:
- 실적 발표, 공시, 산업 뉴스, 규제, M&A, 신규 계약, 경쟁사 동향 등 실제로 있었던
  사건만 포함하세요.
- 그 사건 시점에 주가가 실제로 크게 움직였는지 여부는 중요하지 않습니다. 밸류에이션이나
  내러티브 관점에서 의미가 크다고 판단되면, 주가 변동이 작거나 없었더라도 포함하세요.
  밸류에이션에 직접 관련된 뉴스·공시는 단순 주가 등락폭보다 우선적으로 포함하세요.
- "주가가 X% 올랐다/내렸다"는 결과를 보도하는 기사 자체는 사건이 아니므로 제외하세요.
- 최대 {MAX_EVENTS}개, 중요도가 높은 순으로 정렬하세요.
- 다른 설명 없이 아래 JSON 형식으로만 답하세요.

{{"events": [{{"date": "YYYY-MM-DD", "headline": "10자 내외 제목", "reason": "밸류에이션/내러티브에 왜 중요한지 1문장", "category": "{CATEGORY_OPTIONS} 중 하나", "importance": "high 또는 medium"}}]}}"""

VERIFY_SYSTEM_INSTRUCTION = f"""당신은 한국 주식시장을 분석하는 애널리스트입니다.
아래 사건을 웹 검색으로 사실 확인하고, 근거와 출처를 제공하세요.

규칙:
- 검색으로 사실을 확인하지 못했다면 found를 false로 하세요. 억지로 만들어내지 마세요.
- 다른 설명 없이 아래 JSON 형식으로만 답하세요.

{{"found": true 또는 false, "headline": "10자 내외 제목", "summary": "2문장 이내 설명", "category": "{CATEGORY_OPTIONS} 중 하나"}}"""


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


def _parse_event_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def _discover_events(company_name: str) -> list[dict]:
    prompt = f"{company_name}에 대해 최근 1년간 밸류에이션이나 투자 내러티브에 유의미한 영향을 준 사건을 찾아주세요."
    result = await call_gemini_with_search(
        prompt, system_instruction=DISCOVERY_SYSTEM_INSTRUCTION, generation_config=GEMINI_EVENT_DISCOVERY_CONFIG,
    )
    parsed = _parse_event_json(result["text"])
    if not parsed:
        return []
    return parsed.get("events", [])[:MAX_EVENTS]


async def _verify_event(company_name: str, candidate: dict) -> dict | None:
    date = candidate.get("date", "")
    prompt = (
        f"{company_name}과 관련해 {date or '최근'}경 있었던 다음 사건을 검색으로 확인해주세요: "
        f"{candidate.get('headline', '')} — {candidate.get('reason', '')}"
    )
    result = await call_gemini_with_search(
        prompt, system_instruction=VERIFY_SYSTEM_INSTRUCTION, generation_config=GEMINI_EVENT_CONFIG,
    )
    parsed = _parse_event_json(result["text"])
    if not parsed or not parsed.get("found"):
        return None

    return {
        "date": date,
        "headline": parsed.get("headline") or candidate.get("headline", ""),
        "summary": parsed.get("summary", ""),
        "category": parsed.get("category") or candidate.get("category", "기타"),
        "importance": candidate.get("importance", "medium"),
        "sources": result["sources"][:3],
    }


async def analyze_price_events(company_name: str) -> dict:
    """종목의 밸류에이션·내러티브 관점 유의미 사건 목록을 반환합니다."""
    hist = _fetch_price_history(company_name)

    candidates = await _discover_events(company_name)
    if not candidates:
        return {"company_name": company_name, "events": []}

    # Gemini 무료 티어 분당 요청 한도(RPM)를 넘기지 않도록 순차 처리한다.
    events = []
    for c in candidates:
        v = await _verify_event(company_name, c)
        if v is None:
            continue
        v["pct_change"] = _price_change_near(hist, v.get("date"))
        events.append(v)

    importance_rank = {"high": 0, "medium": 1, "low": 2}
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    events.sort(key=lambda e: importance_rank.get(e.get("importance", "medium"), 1))

    return {"company_name": company_name, "events": events}
