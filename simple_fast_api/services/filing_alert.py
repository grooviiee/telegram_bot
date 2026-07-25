"""공시 감지 및 투자자 관점 요약 모듈.

요약은 공시명 키워드에 대응하는 정적 템플릿(`config.FILING_SUMMARY_TEMPLATES`)으로
생성한다. 이 경로에서 LLM에 줄 수 있는 정보는 (회사명, 공시명, 접수일)뿐이라
모델도 제목만 보고 일반론을 쓸 수밖에 없었고, 그 결과물은 템플릿과 정보량이
같으면서 30분 주기로 과금만 발생시켰다.
"""
import asyncio
import html
from datetime import datetime, timedelta

from config import (
    IMPORTANT_FILING_KEYWORDS,
    FILING_SUMMARY_TEMPLATES,
    FILING_SUMMARY_FALLBACK,
)


def _is_important_filing(report_nm: str) -> bool:
    """투자자에게 중요한 공시인지 판단합니다."""
    return any(kw in report_nm for kw in IMPORTANT_FILING_KEYWORDS)


def summarize_filing(report_nm: str) -> str:
    """공시명에 대응하는 투자자 관점 요약 텍스트(HTML)를 생성합니다.

    FILING_SUMMARY_TEMPLATES의 키 순서대로 첫 매칭을 사용하므로, 구체적인
    사건("유상증자")이 일반 보고서류("주요사항보고")보다 우선합니다.
    """
    template = FILING_SUMMARY_FALLBACK
    for keyword, candidate in FILING_SUMMARY_TEMPLATES.items():
        if keyword in report_nm:
            template = candidate
            break

    lines = [
        f"📌 <b>한 줄 요약</b>: {template['summary']}",
        f"💡 <b>투자자 관점</b>: {template['view']}",
    ]
    if template.get("caution"):
        lines.append(f"⚠️ <b>주의사항</b>: {template['caution']}")
    return "\n".join(lines)


async def check_new_filings(corp_code: str, company_name: str) -> list[dict]:
    """즐겨찾기 종목의 새 공시를 감지하고 중요 공시 목록을 반환합니다.

    database와 dart 모듈은 순환참조 방지를 위해 함수 내부에서 import합니다.

    Returns:
        새로운 중요 공시 목록. 각 항목: {rcept_no, rcept_dt, report_nm, summary}
    """
    import database
    from services.dart import fetch_filing_list

    # 30일 전부터 조회 (초기 등록 시 너무 오래된 공시 제외)
    bgn_de = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

    loop = asyncio.get_event_loop()
    filings = await loop.run_in_executor(None, fetch_filing_list, corp_code, bgn_de)

    if not filings:
        return []

    # DB에서 마지막으로 본 공시 정보 조회
    watch = await database.get_filing_watch(corp_code)
    last_rcept_no = watch["last_rcept_no"] if watch else None

    # 가장 최신 공시로 DB 갱신
    latest = filings[0]
    await database.update_filing_watch(
        corp_code, company_name,
        latest["rcept_no"], latest["rcept_dt"]
    )

    # 첫 등록이면 알림 없이 현재 상태만 저장
    if last_rcept_no is None:
        return []

    # last_rcept_no 이후의 새 공시만 필터링
    new_filings = []
    for f in filings:
        if f["rcept_no"] == last_rcept_no:
            break
        if _is_important_filing(f.get("report_nm", "")):
            new_filings.append(f)

    return new_filings


def build_filing_alert_message(company_name: str, filing: dict) -> str:
    """공시 알림 텔레그램 메시지(HTML)를 생성합니다."""
    report_nm = filing.get("report_nm", "")
    rcept_dt = filing.get("rcept_dt", "")
    rcept_no = filing.get("rcept_no", "")

    # 날짜 포맷: 20240315 → 2024.03.15
    if len(rcept_dt) == 8:
        rcept_dt_fmt = f"{rcept_dt[:4]}.{rcept_dt[4:6]}.{rcept_dt[6:]}"
    else:
        rcept_dt_fmt = rcept_dt

    dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={html.escape(rcept_no)}"

    return (
        f"🔔 <b>공시 알림 — {html.escape(company_name)}</b>\n"
        f"📄 {html.escape(report_nm)}\n"
        f"📅 {html.escape(rcept_dt_fmt)}\n\n"
        f"{summarize_filing(report_nm)}\n\n"
        f"<a href=\"{dart_url}\">📎 DART 원문 보기</a>"
    )
