## Dart/Flutter 기업 정보 시각화 서비스 개발 계획
### 1. 프로젝트 목표
    사용자가 특정 기업을 검색하면, 공개된 데이터를 수집 및 파싱하여 해당 기업의 주요 지표(예: 재무 정보, 주가 등)를 이해하기 쉬운 그래프 형태로 제공하는 애플리케이션을 개발합니다.

### 2. 핵심 기능 정의
    기업 정보 검색: 사용자가 회사 이름이나 종목 코드로 원하는 기업을 찾을 수 있습니다.

    데이터 파싱: 공공 API 또는 웹 크롤링을 통해 기업 정보를 가져옵니다.

    데이터 시각화: 파싱한 데이터를 막대, 선, 원형 등 다양한 그래프로 보여줍니다.

    데이터 종류: 재무제표(매출, 영업이익), 주가 변동 등 핵심적인 정보를 대상으로 합니다.

## 3. 기술 스택 및 라이브러리 추천
    프레임워크: Flutter → Next.js (React)

    HTTP 통신: http 패키지 → fetch API (내장) 또는 axios 라이브러리

    데이터 파싱 (JSON): dart:convert → response.json() (내장)

    데이터 파싱 (HTML): html 패키지 → cheerio, jsdom (주로 서버 사이드 API Route에서 사용)

    그래프/차트: fl_chart → Recharts, Chart.js, Nivo 등 인기 있는 React 차트 라이브러리

    상태 관리: Provider → useState/useEffect (기본), Zustand, React Query (서버 상태 관리)