# Software High-Level Design (HLD)

## Butler.works — DART 기반 기업 분석 & AI 투자 자문 서비스

| | |
|---|---|
| 문서 버전 | 1.0 |
| 작성일 | 2026-07-12 |
| 대상 브랜치 | `master` (`a11a29d`) |
| 문서 범위 | 리포지토리 전체 (`simple_fast_api/`, `frontend/next/`, `backend/`, `backend/go/`, `common/`) |

---

## 1. 개요

### 1.1 배경 및 목적

`README.md`에 명시된 목표는 다음과 같다.

> 유료화 예정인 외부 "butler" 서비스가 유료 전환되기 전에, 그 서비스가 제공하던 핵심 기능(기업 검색, 배당·매출·영업이익 조회, 시각화)을 직접 구현하여 대체한다.

이 목적에서 출발해, 리포지토리는 **DART(전자공시시스템) 공시 데이터를 수집·가공하고, Google Gemini를 이용해 AI 투자 리포트/챗봇을 제공하는 시스템**으로 발전했다. 사용자 접점은 두 가지다.

- **Telegram 봇** — 커맨드 기반 인터페이스
- **웹 대시보드(Next.js, "Butler.works")** — 브라우저 기반 인터페이스

두 클라이언트는 동일한 백엔드(`simple_fast_api`)의 REST API를 공유한다.

### 1.2 리포지토리 구조 개관

리포지토리는 단일 서비스가 아니라 **개발 과정에서 남은 3세대 구현이 공존하는 모노레포**다.

| 디렉터리 | 상태 | 역할 |
|---|---|---|
| `simple_fast_api/` | **운영 중 (Active)** | 실제 프로덕션 백엔드. FastAPI + Telegram 봇 + AI/DART 로직 전부 포함 |
| `frontend/next/` | **운영 중 (Active)** | Next.js 15 웹 대시보드, `simple_fast_api`의 REST API 소비 |
| `backend/` | **레거시 (Dead code)** | 초기 Flask/FastAPI 프로토타입, DART corpCode 다운로더, Telegram 발신 스크립트 |
| `backend/go/` | **무관 (Unrelated)** | Go 튜토리얼용 "rolldice" 데모 서버. 시스템 어디와도 연동되지 않음 |
| `frontend/json-server/` | **레거시 (Dead code)** | 초기 목업용 정적 JSON 서버 |
| `common/` | **미사용 (Orphaned)** | 공유 설정을 의도했던 `config.yaml`이나 어떤 코드에서도 참조되지 않음 |

> 본 문서는 위 표의 "운영 중" 두 컴포넌트(`simple_fast_api`, `frontend/next`)를 시스템의 실제 아키텍처로 정의하고, 레거시/무관 컴포넌트는 별도 절(§8)에서 정리·정리 방안을 제시한다.

---

## 2. 전체 시스템 아키텍처

```
                         ┌───────────────────────────────────────────┐
 Telegram 사용자  ─────► │        simple_fast_api  (FastAPI)          │ ◄──── frontend/next
  (봇 커맨드)            │        main.py : uvicorn :8000             │      "Butler.works"
                         │  ┌───────────────────────────────────┐    │      client-side fetch()
                         │  │ python-telegram-bot (in-process)   │    │      NEXT_PUBLIC_API_BASE_URL
                         │  │  polling / webhook 모드             │    │
                         │  └──────────────┬──────────────────────┘    │
                         │                 │ (self HTTP call, aiohttp) │
                         │  ┌──────────────▼──────────────────────┐   │
                         │  │ routes/  data · ai · legacy · system │   │
                         │  └──────────────┬──────────────────────┘   │
                         │  ┌──────────────▼──────────────────────┐   │
                         │  │ services/ dart · valuation · report ·│   │
                         │  │  chat · scoring · insider ·          │   │
                         │  │  filing_alert                         │  │
                         │  └──────────────┬──────────────────────┘   │
                         │  SQLite(aiosqlite)  diskcache(.cache/)     │
                         │  favorites / filing_watch                  │
                         │  APScheduler: 매일 09:00 알림 /            │
                         │               30분마다 신규공시 폴링        │
                         └───────┬──────────────┬─────────────────────┘
                                 │              │
                        DART Open API      Gemini 2.5 Flash API
                     (opendart.fss.or.kr)  (generativelanguage.googleapis.com)
                                 │
                          yfinance (Yahoo Finance, 실시간 시세)
```

### 2.1 아키텍처 특징

- **단일 프로세스, 다중 인터페이스**: `simple_fast_api`는 하나의 프로세스 안에서 (1) REST API 서버, (2) Telegram 봇, (3) 백그라운드 스케줄러를 동시에 실행한다. Telegram 봇 핸들러(`bot.py`)는 자기 자신의 REST API를 `http://localhost:8000`으로 다시 호출하는 **셀프 루프백(self-loopback) 구조**를 사용한다 — 봇 커맨드가 `services/*`를 직접 호출하지 않고, HTTP를 한 번 더 거친다.
- **Frontend와 Telegram 봇은 동등한 클라이언트**: 웹 대시보드와 Telegram 봇은 기능적으로 거의 동일한 화면/명령 세트를 제공하며, 둘 다 같은 REST API를 소비한다. 비즈니스 로직의 단일 진실 공급원(source of truth)은 `simple_fast_api`뿐이다.
- **배포 인프라 부재**: Dockerfile, docker-compose, CI/CD 파이프라인이 존재하지 않는다. 로컬에서 `python main.py` / `next dev`(or `next start`)로 각각 기동하며, 환경 변수(`NEXT_PUBLIC_API_BASE_URL`, `API_BASE_URL`)로만 연결된다.

---

## 3. 컴포넌트 상세 — `simple_fast_api` (핵심 백엔드)

FastAPI 앱(`title="DART Report Analyzer with Gemini", version="2.0.0"`), 진입점은 [main.py](simple_fast_api/main.py).

### 3.1 모듈 구조

```
simple_fast_api/
├── main.py          # FastAPI app + lifespan(DB 초기화, 봇 기동, 스케줄러 등록)
├── config.py        # 환경변수, DART/Gemini 엔드포인트, Gemini 생성 옵션 상수
├── bot.py            # 모든 Telegram 커맨드 핸들러 (별도 봇 프로세스 없음)
├── database.py         # aiosqlite: favorites, filing_watch 테이블
├── cache.py              # diskcache 기반 LRU 캐시 (기능별 9종)
├── utils.py                # fmt_krw(), call_gemini(), call_gemini_with_tools()
├── routes/
│   ├── data.py                # DART 데이터 API (배당/재무/사업/밸류에이션)
│   ├── ai.py                    # AI 리포트/챗봇/인사이더/스코어 API
│   ├── legacy.py                  # 구버전 Gemini 기반 zip 리포트 배당 추출 + 그래프 이미지
│   └── system.py                    # 캐시 관리, Telegram webhook 수신, health check
└── services/
    ├── dart.py                        # DART Open API 원본 호출 + HTML/XML 파싱
    ├── valuation.py                     # yfinance + DART 조합 PER/PBR/PSR/EV-EBIT
    ├── report.py                          # Gemini 프롬프트 템플릿(표준/버핏 리포트)
    ├── chat.py                              # Gemini 멀티턴 챗봇, Function Calling 도구, 버핏 시스템 프롬프트
    ├── scoring.py                             # 정량 투자 스코어링 엔진
    ├── insider.py                               # 내부자/대주주 보유 현황 + AI 코멘터리
    └── filing_alert.py                            # 30분 주기 신규 공시 감지
```

### 3.2 Telegram 봇 (`bot.py`)

프레임워크: `python-telegram-bot >= 20.0` (async `Application` API).

| 커맨드 | 기능 |
|---|---|
| `/start` | 시작 안내 |
| `/analysis` | 종합 분석 |
| `/business` | 사업 내용 |
| `/dividend` | 배당 데이터 |
| `/profit` | 수익성/성장성 |
| `/health` | 재무 건전성 |
| `/valuation` | 밸류에이션(PER/PBR/PSR/EV-EBIT) |
| `/report` | AI 표준 리포트 |
| `/buffett` | 워렌 버핏 스타일 AI 리포트 |
| `/score` | 정량 투자 스코어 |
| `/insider` | 내부자/대주주 보유 현황 |
| `/chat`, `/end` | 멀티턴 AI 상담 (ConversationHandler) |
| `/fav_add`, `/fav_del`, `/favs` | 관심 종목 관리 |

부가 기능: 인라인 키보드 "유사 기업 추천" 콜백, 숨은 이스터에그 정규식 핸들러.

기동 모드: **Polling**(기본) 또는 **Webhook**(`routes/system.py::telegram_webhook`, `WEBHOOK_SECRET_TOKEN`을 `secrets.compare_digest`로 검증).

### 3.3 스케줄링 (APScheduler, `Asia/Seoul`)

- **매일 09:00** — `send_daily_notification`: 관심 종목 요약 알림 발송
- **30분마다** — `send_filing_alerts`: 관심 기업의 신규 공시를 DART에서 폴링하여 알림

### 3.4 데이터 저장

- **SQLite (`bot_data.db`, `aiosqlite`, ORM 없음)**
  - `favorites(user_id, username, company, analysis_type)` — 사용자별 관심 종목, 일일 알림의 기준
  - `filing_watch(corp_code, company_name, last_rcept_no, last_rcept_dt)` — 신규 공시 중복 방지 상태
- **파일 캐시 (`diskcache`, `.cache/` 디렉터리)** — 배당/재무/사업/분기별/밸류에이션/리포트/버핏리포트 등 9종 LRU 캐시. 재시작 후에도 유지. `GET /cache/status`, `DELETE /cache/clear`로 관리.
- **`dart_reports/`** — DART 원본 zip 공시 캐시 (예: 삼성전자, 덕산네오룩스), `download_reports_logic()`이 기록.

### 3.5 외부 연동

| 대상 | 용도 | 세부 |
|---|---|---|
| **DART Open API** (`opendart.fss.or.kr`) | 기업코드, 공시 목록, 재무제표, 배당, 대주주 지분, 원문 공시 다운로드 | `services/dart.py`. 엔드포인트: `corpCode.xml`, `list.json`, `fnlttSinglAcntAll.json`(CFS→OFS 폴백), `alotMatter.json`, `elestock.json`, `document.xml`(+ BeautifulSoup HTML 파싱) |
| **Google Gemini** (`gemini-2.5-flash`) | AI 리포트, 챗봇, 내부자 분석 | `utils.py`에서 공식 SDK가 아닌 raw `aiohttp` POST로 `generativelanguage.googleapis.com`을 직접 호출 |
| **yfinance** | 실시간 주가/시가총액/발행주식수 | `services/valuation.py`, `.KS`→`.KQ` 순으로 티커 탐색 |
| **Telegram Bot API** | 사용자 커맨드 처리, 알림 발송 | polling 또는 webhook |

### 3.6 AI 자문 기능 상세 (최근 고도화 영역)

- **Thinking Mode**: `config.py`의 `GEMINI_CHAT_CONFIG`/`GEMINI_REPORT_CONFIG`에 `thinkingConfig.thinkingBudget`(챗봇 8192 / 리포트 4096) 설정. `utils.py::_extract_text_from_candidates`가 응답의 `thought` 파트를 필터링해 최종 답변만 노출.
- **Function Calling**: `services/chat.py::CHAT_TOOLS`가 4개 도구를 정의 — `get_quarterly_financials`, `calculate_intrinsic_value`(Gordon Growth/DCF), `search_filings`, `get_dupont_analysis`. `utils.py::call_gemini_with_tools`가 최대 `GEMINI_MAX_TOOL_ROUNDS=3`회의 함수 호출↔응답 라운드를 구동.
- **워렌 버핏 투자 철학**: `services/chat.py::BUFFETT_SYSTEM_PROMPT`(내재가치, 안전마진, 경제적 해자, ROE 품질, 능력범위 등을 담은 약 90줄 한국어 시스템 프롬프트) + Few-shot 예시. `services/report.py::BUFFETT_REPORT_TEMPLATE`에도 반영. `GET /buffett-report/{company_name}`, `POST /chat/{company_name}`(mode: "buffett"), Telegram `/buffett`, `/chat`으로 노출.
- **밸류에이션**: `services/valuation.py::fetch_valuation` — yfinance 실시간 시세 + 3개년 DART 재무 데이터를 결합해 PER/PBR/PSR/EV/EV-EBIT 및 히스토리 계산. `GET /valuation/{company_name}`.

---

## 4. 컴포넌트 상세 — `frontend/next` (웹 대시보드)

### 4.1 기술 스택

Next.js **15.3.3**, React **19**, TypeScript, Tailwind CSS 4, `chart.js` + `react-chartjs-2`(차트), `lucide-react`(아이콘). 개발용 Playwright 드라이버 포함.

### 4.2 구조

`layout.js`는 단일 컴포넌트 [`InteractiveLayout.js`](frontend/next/src/app/InteractiveLayout.js)만 렌더링한다. Next.js의 실제 라우팅 대신 **클라이언트 상태(`activePage`)로 화면을 전환하는 SPA 패턴**을 사용하며, `localStorage`(`dart_favorites`)로 관심 종목을 관리한다.

주요 화면: `home`(종합분석) · `business` · `dividend` · `profitability` · `financial-health` · `valuation` · `buffett`(버핏 리포트) · `report`(AI 리포트) · `chat`(AI 상담) · `favorites`.

> `read/[id]/`, `update/[id]/`, `Sidebar.js`, `Control.js`, `UserSwitcher.js`는 초기 CRUD 프로토타입 단계의 잔재로 현재 흐름에서 사용되지 않는 것으로 보인다.

### 4.3 버핏 리포트 화면 (`src/app/buffett/page.tsx`)

최근 수정된 핵심 화면. `/financials`, `/valuation`, `/score`, `/buffett-report` 4개 API를 `Promise.all`로 병렬 호출한 뒤:
- 스코어 카드(총점 + 성장성/수익성/재무건전성/배당/밸류에이션 5개 카테고리)
- 자동 감지 시그널 배지(긍정/부정/중립)
- Chart.js 차트 7종: ROE vs 버핏 기준선(15%), FCF-순이익 비교("이익의 질"), 영업이익률 추이, 부채비율(임계값별 색상), 듀폰 분해, PER/PBR 히스토리, 카테고리별 점수
- Gemini 리포트 텍스트를 위한 자체 경량 마크다운 렌더러(외부 라이브러리 미사용)

### 4.4 백엔드 연동

`process.env.NEXT_PUBLIC_API_BASE_URL`(기본값 `http://localhost:8000`)을 기준으로 클라이언트 사이드 `fetch()` 직접 호출(axios/서버 액션 미사용). `AbortSignal.timeout()`으로 타임아웃 처리.

---

## 5. 데이터 흐름 예시 (버핏 리포트 조회)

```
사용자                Frontend/Telegram              simple_fast_api               외부 API
  │                        │                               │                          │
  │  기업명 입력/버핏버튼    │                               │                          │
  ├───────────────────────►│                               │                          │
  │                        │ GET /buffett-report/{company} │                          │
  │                        ├──────────────────────────────►│                          │
  │                        │                                │  캐시 확인(diskcache)     │
  │                        │                                ├── (miss) ──────────────► DART Open API
  │                        │                                │◄────────────────────────┤ 재무/공시 데이터
  │                        │                                ├── Gemini 프롬프트 구성    │
  │                        │                                │   (BUFFETT_SYSTEM_PROMPT) │
  │                        │                                ├─────────────────────────► Gemini 2.5 Flash
  │                        │                                │◄────────────────────────┤ (Thinking + 응답)
  │                        │                                │  캐시 저장                │
  │                        │◄──────────────────────────────┤                          │
  │◄───────────────────────┤  리포트 + 스코어 + 차트 데이터   │                          │
```

Telegram `/buffett` 커맨드도 동일한 엔드포인트를 `bot.py`가 loopback HTTP로 호출하는 방식으로 동작한다.

---

## 6. 환경 설정 (Configuration)

| 파일 | 위치 | 주요 변수 |
|---|---|---|
| `.env` | `simple_fast_api/` | `DART_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `WEBHOOK_URL`, `WEBHOOK_SECRET_TOKEN` |
| `.env.local` | `frontend/next/` | `NEXT_PUBLIC_API_BASE_URL`, `DART_API`, `BACKEND_IP`, `BACKEND_PORT`(뒤 3개는 초기 설계의 잔재로 추정) |
| `config.yaml` | `backend/`, `common/` | DART API 키 (레거시) |

⚠️ **보안 주의**: `git ls-files` 기준 `simple_fast_api/.env`, `backend/config.yaml`, `common/config.yaml`이 모두 Git에 커밋되어 있다(`.gitignore`는 `.cache/`, `bot_data.db`, `dart_reports/`, `.venv/`만 제외). 즉 DART/Gemini API 키, Telegram 봇 토큰, 웹훅 시크릿이 커밋 히스토리에 평문으로 남아 있다. **§8 개선 과제**에서 조치 방안을 제시한다.

---

## 7. 배포 아키텍처 (현황)

현재 컨테이너화·CI/CD가 전혀 없다.

- **백엔드**: `python main.py` 또는 `uvicorn main:app`으로 `127.0.0.1:8000` 로컬 기동. `simple_fast_api/.claude/skills/run-simple-fast-api/smoke.sh`가 venv 생성 → 의존성 설치 → 서버 기동 → `/`, `/cache/status`, `/dividend-data/{COMPANY}`, `/valuation/{COMPANY}` 헬스체크를 수행하는 개발용 스크립트로 존재(운영 배포 스크립트는 아님).
- **프론트엔드**: `next dev --turbopack`(개발) 또는 `next build && next start`(운영)로 `:3000` 기동. Playwright 기반 스크린샷/스모크 드라이버(`.claude/skills/run-frontend-next/`)는 개발자 도구일 뿐 배포 파이프라인이 아님.
- **연결**: 두 서비스는 오직 HTTP + 환경변수(`NEXT_PUBLIC_API_BASE_URL`, `API_BASE_URL`)로만 결합되며, 서비스 디스커버리·리버스 프록시·헬스체크 오케스트레이션은 없다.

---

## 8. 레거시/미사용 컴포넌트 및 개선 과제

### 8.1 레거시 컴포넌트 정리 대상

| 컴포넌트 | 내용 | 권장 조치 |
|---|---|---|
| `backend/backend_service.py`, `backend/get_api_test.py` | 초기 Flask/FastAPI DART 다운로더 프로토타입, `simple_fast_api`로 완전 대체됨 | 삭제 또는 아카이브 |
| `backend/terraform.py` | DART 배당 조회 프로토타입 (`services/dart.py`로 대체) | 삭제 |
| `backend/init.py` | Telegram 발신 최초 테스트 스크립트 | 삭제 |
| `backend/utils/action_space.py` | `gym` 기반 orphan 코드, 프로젝트와 무관 | 삭제 |
| `backend/go/` | Go "rolldice" 튜토리얼 데모, 어떤 연동도 없음 | 삭제 또는 별도 리포지토리로 분리 |
| `frontend/json-server/` | 초기 정적 목업 API | 삭제 |
| `common/config.yaml` | 어떤 코드에서도 참조되지 않는 설정 파일 | 삭제하거나, 실제 공유 설정으로 활용할 경우 서비스들에 연결 |
| `frontend/next/src/app/read|update/[id]/`, `Sidebar.js`, `Control.js`, `UserSwitcher.js` | 초기 CRUD 프로토타입 잔재 | 사용 여부 확인 후 삭제 |

### 8.2 보안/운영 개선 과제

1. **비밀정보 노출**: 커밋된 `.env`/`config.yaml` 내 API 키·토큰 전량 로테이션 필요. 이후 `.gitignore`에 추가하고 커밋 히스토리에서 제거(`git filter-repo` 등) 검토.
2. **비공식 Gemini 호출 방식**: `utils.py`가 공식 Google SDK가 아닌 raw `aiohttp` 호출을 사용 — 유지보수성과 재시도/에러 처리 표준화 관점에서 공식 SDK 전환 검토.
3. **CI/CD 및 컨테이너화 부재**: `Dockerfile`/`docker-compose.yml`/GitHub Actions 워크플로 부재. 배포 신뢰성 확보를 위해 최소한의 컨테이너화 및 자동 테스트 파이프라인 도입 권장.
4. **자기 자신을 호출하는 봇 구조**: `bot.py`가 자신의 FastAPI 서버를 loopback HTTP로 호출하는 구조는 불필요한 네트워크 홉과 장애 지점을 추가한다. `services/*`를 직접 호출하는 구조로 리팩터링 검토.
5. **중복 설정 소스**: 프론트엔드의 `DART_API`, `BACKEND_IP`, `BACKEND_PORT`는 현재 아키텍처(단일 `NEXT_PUBLIC_API_BASE_URL`)와 맞지 않는 구버전 변수로 보임 — 정리 필요.

---

## 9. 요약

| 항목 | 내용 |
|---|---|
| 시스템 목적 | DART 공시 기반 기업 재무 분석 + Gemini AI 투자 자문을 Telegram 봇과 웹 대시보드로 제공 |
| 핵심 백엔드 | `simple_fast_api/` — FastAPI + 인프로세스 Telegram 봇 + APScheduler |
| 핵심 프론트엔드 | `frontend/next/` — Next.js 15 / React 19 SPA 스타일 대시보드 |
| 데이터 저장 | SQLite(`aiosqlite`, 즐겨찾기/공시감시) + diskcache(응답 캐시) + 로컬 파일(`dart_reports/`) |
| 외부 연동 | DART Open API, Google Gemini 2.5 Flash, yfinance, Telegram Bot API |
| 배포 | 컨테이너/CI 없음, 로컬 프로세스 + 환경변수 기반 연결 |
| 최우선 리스크 | 커밋된 API 키/토큰 노출, 레거시 코드 잔존, 배포 자동화 부재 |
