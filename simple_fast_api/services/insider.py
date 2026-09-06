"""내부자 거래 집계 및 Gemini 기반 AI 분석 모듈."""
from html import escape
from config import AI_EVIDENCE_RULES
from utils import fmt_shares, call_gemini

# 직위 중요도 (높을수록 주목해야 할 인물)
ROLE_PRIORITY = {
    '회장': 10, '부회장': 9, '사장': 8, '부사장': 7,
    '전무': 6, '상무': 5, '이사': 4, '감사': 3,
}


def _role_priority(role: str) -> int:
    for key, val in ROLE_PRIORITY.items():
        if key in role:
            return val
    return 1


def summarize_insider_data(holdings: list[dict]) -> dict:
    """보유/변동 데이터를 집계하여 요약 통계를 반환합니다."""
    buyers, sellers = [], []

    for h in holdings:
        change = h.get('change', 0)
        if change > 0:
            buyers.append(h)
        elif change < 0:
            sellers.append(h)

    # 변동량 절댓값 기준 정렬
    buyers.sort(key=lambda x: x['change'], reverse=True)
    sellers.sort(key=lambda x: x['change'])

    total_buy = sum(h['change'] for h in buyers)
    total_sell = sum(abs(h['change']) for h in sellers)

    # 등기임원 / 주요주주 필터
    key_buyers = [h for h in buyers if h.get('is_registered') or h.get('is_major_shareholder')]
    key_sellers = [h for h in sellers if h.get('is_registered') or h.get('is_major_shareholder')]

    return {
        'buyer_count': len(buyers),
        'seller_count': len(sellers),
        'total_buy_shares': total_buy,
        'total_sell_shares': total_sell,
        'top_buyers': buyers[:5],
        'top_sellers': sellers[:5],
        'key_buyers': key_buyers[:3],
        'key_sellers': key_sellers[:3],
        'net_change': total_buy - total_sell,
    }


def build_insider_text(company_name: str, year: str, summary: dict, recent_filings: list[dict]) -> str:
    """텔레그램 메시지용 내부자 거래 현황 텍스트를 생성합니다."""
    buyer_count = summary['buyer_count']
    seller_count = summary['seller_count']
    total_buy = summary['total_buy_shares']
    total_sell = summary['total_sell_shares']
    net = summary['net_change']
    net_sign = "▲" if net >= 0 else "▼"
    net_label = "순증가" if net >= 0 else "순감소"

    lines = [
        f"<b>📊 {escape(company_name)} 소유주식 변동 현황 (조회된 신고 기준)</b>\n",
        "소유주식 증감이며 실제 매수·매도 여부와 원인은 확인되지 않았습니다.\n",
        f"<b>── 집계 요약 ──</b>",
        f"증가 신고: {buyer_count}건 (+{fmt_shares(total_buy)})",
        f"감소 신고: {seller_count}건 (-{fmt_shares(total_sell)})",
        f"{net_sign} {net_label}: {fmt_shares(abs(net))}\n",
    ]

    # 주요 증가자 (등기임원/주요주주)
    if summary['key_buyers']:
        lines.append("<b>── 주요 증가 (등기임원/주주) ──</b>")
        for h in summary['key_buyers']:
            tag = "🏢" if h.get('is_major_shareholder') else "👤"
            lines.append(f"{tag} {escape(h['name'])} ({escape(h['role'])}) +{fmt_shares(h['change'])}")
        lines.append("")

    # 주요 감소자 (등기임원/주요주주)
    if summary['key_sellers']:
        lines.append("<b>── 주요 감소 (등기임원/주주) ──</b>")
        for h in summary['key_sellers']:
            tag = "🏢" if h.get('is_major_shareholder') else "👤"
            lines.append(f"{tag} {escape(h['name'])} ({escape(h['role'])}) {fmt_shares(h['change'])}")
        lines.append("")

    # 변동량 상위 매수/매도 (비등기 포함)
    if summary['top_buyers']:
        lines.append("<b>── 증가 상위 5인 ──</b>")
        for h in summary['top_buyers']:
            lines.append(f"  {escape(h['name'])} ({escape(h['role'])}) +{fmt_shares(h['change'])}")
        lines.append("")

    if summary['top_sellers']:
        lines.append("<b>── 감소 상위 5인 ──</b>")
        for h in summary['top_sellers']:
            lines.append(f"  {escape(h['name'])} ({escape(h['role'])}) {fmt_shares(h['change'])}")
        lines.append("")

    # 최근 3개월 신고 내역
    if recent_filings:
        lines.append("<b>── 최근 3개월 신고 내역 ──</b>")
        for f in recent_filings[:8]:
            dt = f.get('rcept_dt', '')
            if len(dt) == 8:
                dt = f"{dt[:4]}.{dt[4:6]}.{dt[6:]}"
            filer = f.get('filer', '')
            lines.append(f"  {dt} {escape(filer)}")
        lines.append("")

    return "\n".join(lines)


def _build_gemini_prompt(company_name: str, year: str, summary: dict, recent_filings: list[dict]) -> str:
    buyer_count = summary['buyer_count']
    seller_count = summary['seller_count']
    total_buy = summary['total_buy_shares']
    total_sell = summary['total_sell_shares']
    net = summary['net_change']

    top_buyers_txt = "\n".join(
        f"- {escape(h['name'])} ({escape(h['role'])}, {'등기' if h['is_registered'] else '비등기'}): +{h['change']:,}주"
        for h in summary['top_buyers']
    )
    top_sellers_txt = "\n".join(
        f"- {escape(h['name'])} ({escape(h['role'])}, {'등기' if h['is_registered'] else '비등기'}): {h['change']:,}주"
        for h in summary['top_sellers']
    )
    recent_txt = "\n".join(
        f"- {f.get('rcept_dt')} {f.get('filer')}"
        for f in recent_filings[:5]
    )

    return f"""당신은 한국 주식 투자 전문가입니다.

아래는 {company_name}의 {year}년 임원/주요주주 소유주식 변동 데이터입니다.

[집계]
- 증가 신고: {buyer_count}명 (합계 +{total_buy:,}주)
- 감소 신고: {seller_count}명 (합계 -{total_sell:,}주)
- 순변동: {net:+,}주

[증가 상위]
{top_buyers_txt or '없음'}

[감소 상위]
{top_sellers_txt or '없음'}

[최근 3개월 신고]
{recent_txt or '없음'}

위 데이터를 바탕으로 투자자에게 유용한 인사이트를 제공하세요.

답변 형식:
🧭 **내부자 동향 요약**: (한 줄로 현재 내부자들의 전반적 행동 방향)
💡 **투자 시사점**: (이 데이터가 투자자에게 의미하는 바, 2~3문장)
⚠️ **주의점**: (데이터 해석 시 주의해야 할 맥락, 1~2문장)

간결하게 핵심만 답변하세요."""


async def analyze_insider_with_gemini(company_name: str, year: str, summary: dict, recent_filings: list[dict]) -> str:
    """Gemini로 내부자 거래 패턴을 분석합니다."""
    prompt = AI_EVIDENCE_RULES + "소유주식 증감은 매수·매도를 입증하지 않습니다. 증여·보상·정정 등 원인이 확인되지 않았습니다.\n" + _build_gemini_prompt(company_name, year, summary, recent_filings)
    return await call_gemini(prompt, timeout=30)
