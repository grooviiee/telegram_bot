# Telegram 분기 수익성 그래프

`/profit 삼성전자`는 최근 공시된 분기부터 거슬러 올라간 12분기(3년)의
매출액·영업이익(억원), 영업이익률(%), 전년 동기 매출 성장률(%)을 PNG 한 장으로 보냅니다.
유사 기업 추천 버튼에서도 같은 그래프를 제공합니다. 즐겨찾기의 일일 요약은 기존 연간 기준입니다.

`GET /profit-quarterly/{company_name}`는 그래프 입력 데이터를 반환합니다.
기존 `/financials-quarterly`와 별도 캐시를 사용하며, `cached` 플래그와 수집 시각·출처를 제공합니다.
`/cache/status`와 `/cache/clear`에서 `quarterly_profit` 캐시를 확인·삭제할 수 있습니다.

- DART 손익계산서(IS/CIS)의 1~3분기 `thstrm_amount`는 3개월 금액입니다.
- 4분기는 연간 금액에서 같은 해 3분기의 `thstrm_add_amount`(누적)를 차감합니다.
- 연결(CFS) 우선, 개별(OFS) 대체 순서로 조회합니다. 차감하거나 전년 동기를 비교할 때
  재무제표 기준이 다르거나 데이터가 없으면 해당 계산값을 제공하지 않습니다.
- 전년 동기 매출이 0 또는 음수이면 성장률을 계산하지 않습니다.
- 누락 분기는 시계열에 남겨 두고 그래프에서 빈 구간으로 표시합니다. 0과 적자는 그대로 표시합니다.
- 인증·통신 오류는 502로 반환하며 부분 수집 결과를 캐싱하지 않습니다.

분기와 누적 금액의 정의: [DART 단일회사 전체 재무제표 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020).

검증: `simple_fast_api`에서 `.venv/Scripts/python.exe -m unittest discover -s tests -v`.

그래프 한글 폰트는 Windows의 맑은 고딕, 그 외 환경의 NanumGothic을 기본으로 사용합니다.
Linux 배포 시 해당 폰트를 설치하거나 `PROFIT_CHART_FONT`에 설치된 한글 폰트명을 지정하세요.
