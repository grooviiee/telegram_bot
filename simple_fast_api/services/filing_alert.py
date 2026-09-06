"""공시 감지 및 Gemini 기반 투자자 관점 요약 모듈."""
import asyncio
from datetime import datetime, timedelta

from config import IMPORTANT_FILING_KEYWORDS, DART_VIEWER_URL
from html import escape
from urllib.parse import quote


def _is_important_filing(report_nm: str) -> bool:
    """투자자에게 중요한 공시인지 판단합니다."""
    return any(kw in report_nm for kw in IMPORTANT_FILING_KEYWORDS)


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


async def build_filing_alert_message(company_name: str, filing: dict) -> str:
    """공시 알림 텔레그램 메시지를 생성합니다."""
    report_nm = filing.get("report_nm", "")
    rcept_dt = filing.get("rcept_dt", "")
    rcept_no = filing.get("rcept_no", "")

    # 날짜 포맷: 20240315 → 2024.03.15
    if len(rcept_dt) == 8:
        rcept_dt_fmt = f"{rcept_dt[:4]}.{rcept_dt[4:6]}.{rcept_dt[6:]}"
    else:
        rcept_dt_fmt = rcept_dt

    dart_url = DART_VIEWER_URL + quote(rcept_no, safe="")

    summary = "새 공시가 접수되었습니다. 구체적인 변경 수치와 내용은 원문에서 확인해주세요."

    return (
        f"🔔 <b>공시 알림 — {escape(company_name)}</b>\n"
        f"📄 {escape(report_nm)}\n"
        f"📅 {escape(rcept_dt_fmt)}\n\n"
        f"{summary}\n\n"
        f"<a href=\"{dart_url}\">📎 DART 원문 보기</a>"
    )
