"""공시 감지 및 Gemini 기반 투자자 관점 요약 모듈."""
import asyncio
from datetime import datetime, timedelta

from config import IMPORTANT_FILING_KEYWORDS
from utils import call_gemini


def _is_important_filing(report_nm: str) -> bool:
    """투자자에게 중요한 공시인지 판단합니다."""
    return any(kw in report_nm for kw in IMPORTANT_FILING_KEYWORDS)


async def summarize_filing_with_gemini(company_name: str, report_nm: str, rcept_dt: str) -> str:
    """Gemini를 이용해 공시를 투자자 관점에서 간략히 요약합니다."""
    prompt = f"""당신은 한국 주식 투자 전문가입니다.

아래 공시가 방금 접수되었습니다. 개인 투자자 관점에서 이 공시가 어떤 의미인지 3~4문장으로 간결하게 설명해주세요.

- 회사명: {company_name}
- 공시명: {report_nm}
- 접수일: {rcept_dt}

답변 형식:
📌 **한 줄 요약**: (이 공시가 무엇인지 한 줄로)
💡 **투자자 관점**: (주가/실적/지배구조에 미칠 영향 2~3문장)
⚠️ **주의사항**: (있다면 투자자가 확인해야 할 점 한 줄, 없으면 생략)

간결하게, 핵심만 답변하세요. 불필요한 면책 문구는 생략하세요."""

    return await call_gemini(
        prompt,
        generation_config={"temperature": 0.3, "maxOutputTokens": 512},
        timeout=30,
    )


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

    dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

    summary = await summarize_filing_with_gemini(company_name, report_nm, rcept_dt_fmt)

    return (
        f"🔔 <b>공시 알림 — {company_name}</b>\n"
        f"📄 {report_nm}\n"
        f"📅 {rcept_dt_fmt}\n\n"
        f"{summary}\n\n"
        f"<a href=\"{dart_url}\">📎 DART 원문 보기</a>"
    )
