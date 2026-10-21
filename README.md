## Objective
기존 웹의 검색·분석 이동·즐겨찾기·오류 복구 개선과 브라우저 검증은 [기존 분석 기능 UX](docs/existing-feature-ux.md)를 참고하세요.
로컬 AI Telegram 사용법은 [로컬 AI 설정](docs/local-ai.md)을 참고하세요.
사업부별 손익·비중 질문은 [사업부 손익 상담](docs/segment-profit.md)을 참고하세요.
공시 전체에서 근거를 찾아 설명하는 기능은 [공시 검색 기반 상담](docs/report-retrieval.md)을 참고하세요.
`/changes`로 최근 두 해를 비교하는 기능은 [사업보고서 서술 변화](docs/annual-changes.md)를 참고하세요.
응답 재사용과 모델 사전 준비는 [응답 속도 개선](docs/response-performance.md)을 참고하세요.

7/1 일자 butler 서비스가 유료화가 되기 이전에 필요한 기능들을 빼온다.


## TO DO List.
1. 기업 검색
    
    xml파일 가져온 후, 압축 풀어서 기업 코드를 찾아야 한다.

2. 검색 시, 배당내역, 매출, 영업이익 값 구하기 (최근 5년 분기별, 연도별)

3. 구한 값을 토대로 그래프 나타내기

## GitHub 핫 프로젝트 소개

기존 Telegram 봇에서 `/today`로 일간 Trending 프로젝트 최대 3개를 받아볼 수 있습니다.
개인 채팅에서 `/trend_on`으로 매일 09:00 KST 소개를 신청하고 `/trend_off`로 해제합니다.
기존 봇 토큰·Gemini 설정을 재사용하며 채팅 ID는 자동 저장합니다.
[설정, 캐시, 선정 기준 및 미리보기 API](docs/github-trending.md)를 참고하세요.
