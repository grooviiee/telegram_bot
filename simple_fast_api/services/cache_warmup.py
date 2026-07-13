"""인기 검색 종목 캐시 워밍업.

search_stats(검색 횟수) 상위 N개 종목에 대해 배당·재무·사업개요·밸류에이션
데이터를 미리 조회해 캐시에 채워둔다. 각 조회 함수는 이미 캐시가 있으면
그대로 반환하므로, 이미 따뜻한 종목은 다시 API를 호출하지 않는다.
"""
import database
from routes.data import get_dividend_data, get_financials, get_business_overview, get_valuation_endpoint

TOP_N = 20

_WARMERS = (get_dividend_data, get_financials, get_business_overview, get_valuation_endpoint)


async def warm_popular_companies() -> None:
    companies = await database.get_top_searched_companies(TOP_N)
    if not companies:
        print("[CacheWarmup] 검색 이력이 없어 워밍업을 건너뜁니다.")
        return

    print(f"[CacheWarmup] 인기 종목 {len(companies)}개 워밍업 시작: {companies}")
    for company in companies:
        for warmer in _WARMERS:
            try:
                await warmer(company)
            except Exception as e:
                print(f"[CacheWarmup] '{company}' {warmer.__name__} 실패: {e}")
    print("[CacheWarmup] 워밍업 완료")
