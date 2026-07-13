"""주가 변곡점 이벤트 분석.

yfinance 일별 종가에서 단기간 급등락 구간(변곡점)을 찾아내고,
Google Search grounding을 지원하는 Gemini로 그 구간의 실제 원인 사건을
조사한다. '주가가 몇 % 올랐다/내렸다'는 결과 보도 자체는 원인으로 치지
않도록 프롬프트에서 명시적으로 배제한다.
"""
import json
import re

import yfinance as yf

from config import GEMINI_EVENT_CONFIG
from services.valuation import get_stock_code
from utils import call_gemini_with_search

WINDOW_DAYS = 5
THRESHOLD_PCT = 5.0
MAX_EVENTS = 8

EVENT_SYSTEM_INSTRUCTION = """당신은 한국 주식시장을 분석하는 애널리스트입니다.
특정 종목의 주가가 특정 기간 동안 크게 움직인 원인을 웹 검색으로 조사합니다.

규칙:
- 실적 발표, 산업/경쟁사 뉴스, 규제·정책, 공급망 이슈 등 실제로 벌어진 사건만 원인으로 제시하세요.
- "주가가 X% 올랐다/내렸다"는 결과를 보도하는 기사 자체는 원인이 아니므로 절대 근거로 사용하지 마세요.
- 뚜렷한 원인을 찾지 못했다면 found를 false로 하세요. 억지로 이유를 만들지 마세요.
- 다른 설명 없이 아래 JSON 형식으로만 답하세요.

{"found": true 또는 false, "headline": "10자 내외 짧은 제목", "summary": "2문장 이내 설명", "category": "실적/산업뉴스/규제/공급망/경쟁사/기타 중 하나"}"""


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


def _detect_inflections(hist) -> list[dict]:
    """WINDOW_DAYS 구간 등락률이 THRESHOLD_PCT를 넘는 변곡점을 찾는다.

    겹치는 구간은 등락폭이 가장 큰 것만 남기고, 최신순으로 최대 MAX_EVENTS개 반환.
    """
    closes = hist["Close"]
    dates = hist.index

    candidates = []
    for i in range(WINDOW_DAYS, len(closes)):
        start_price = float(closes.iloc[i - WINDOW_DAYS])
        end_price = float(closes.iloc[i])
        if start_price <= 0:
            continue
        pct = (end_price - start_price) / start_price * 100
        if abs(pct) >= THRESHOLD_PCT:
            candidates.append({
                "end_idx": i,
                "start_date": dates[i - WINDOW_DAYS].strftime("%Y-%m-%d"),
                "end_date": dates[i].strftime("%Y-%m-%d"),
                "pct_change": round(pct, 1),
            })

    candidates.sort(key=lambda c: -abs(c["pct_change"]))
    picked, used_idx = [], []
    for c in candidates:
        if any(abs(c["end_idx"] - u) < WINDOW_DAYS for u in used_idx):
            continue
        used_idx.append(c["end_idx"])
        picked.append(c)
        if len(picked) >= MAX_EVENTS:
            break

    picked.sort(key=lambda c: c["end_date"], reverse=True)
    return picked


def _parse_event_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def _explain_event(company_name: str, candidate: dict) -> dict | None:
    direction = "상승" if candidate["pct_change"] > 0 else "하락"
    prompt = (
        f"{company_name} 주가가 {candidate['start_date']}부터 {candidate['end_date']}까지 "
        f"{candidate['pct_change']:+.1f}% {direction}했습니다. "
        "이 기간 전후로 이 변동에 실질적인 영향을 줬을 만한 실제 사건을 찾아주세요."
    )
    result = await call_gemini_with_search(
        prompt, system_instruction=EVENT_SYSTEM_INSTRUCTION, generation_config=GEMINI_EVENT_CONFIG,
    )
    parsed = _parse_event_json(result["text"])
    if not parsed or not parsed.get("found"):
        return None

    return {
        "start_date": candidate["start_date"],
        "end_date": candidate["end_date"],
        "pct_change": candidate["pct_change"],
        "headline": parsed.get("headline", ""),
        "summary": parsed.get("summary", ""),
        "category": parsed.get("category", "기타"),
        "sources": result["sources"][:3],
    }


async def analyze_price_events(company_name: str) -> dict:
    """종목의 주가 변곡점과 원인 사건 목록을 반환합니다."""
    hist = _fetch_price_history(company_name)
    if hist is None or hist.empty:
        return {"company_name": company_name, "events": []}

    candidates = _detect_inflections(hist)

    events = []
    for candidate in candidates:
        explained = await _explain_event(company_name, candidate)
        if explained:
            events.append(explained)

    return {"company_name": company_name, "events": events}
