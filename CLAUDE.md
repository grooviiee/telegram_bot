# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 이 저장소의 문서는 한국어가 기본입니다. 에이전트 온보딩 문서 `AGENTS.md`,
> 설계 배경 `docs/architecture.md` · `docs/harness-engineering.md` · `HLD.md`도 함께 참고하세요.

## 프로젝트 개요

DART(전자공시) 데이터를 수집·분석하여 한국 상장기업의 재무지표, 밸류에이션,
AI 투자 리포트를 제공하는 서비스. 사용자는 **Telegram 봇** 또는 **웹(Next.js)**
으로 기업을 검색하고 분석 결과를 받습니다.

| 구성 | 기술 | 위치 |
|------|------|------|
| 백엔드 API | FastAPI (Python 3.10+) | `simple_fast_api/` |
| Telegram 봇 | python-telegram-bot v20+ (polling) | `simple_fast_api/bot.py` |
| 웹 프론트엔드 | Next.js 15 / React 19 / TypeScript / Tailwind 4 / Chart.js | `frontend/next/` |
| DB | SQLite (aiosqlite) — favorites · filing_watch · search_stats | `simple_fast_api/database.py` |
| 캐시 | diskcache 기반 LRU (`simple_fast_api/.cache/`) | `simple_fast_api/cache.py` |
| 외부 API | DART OpenAPI, Google Gemini, Groq, Naver 뉴스 검색, yfinance | `simple_fast_api/services/`, `utils.py` |

**주 작업 대상은 `simple_fast_api/`입니다.** 루트의 `backend/`(Go·terraform 실험)와
`frontend/json-server/`(목업)는 레거시이므로 명시적 요청 없이 수정하지 마세요.

## 빌드 · 실행 · 테스트 명령어

```bash
# --- 백엔드 (simple_fast_api/) ---
cd simple_fast_api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # 환경변수 준비 (아래 '환경변수' 참고)
python main.py                            # 개발 서버 → http://127.0.0.1:8000 (문서: /docs)
uvicorn main:app --reload --port 8000     # (대안) 핫리로드 실행

# 에이전트용 스모크 테스트 — 봇 토큰을 비운 채 서버를 띄우고 대표 엔드포인트 curl 후 종료
.claude/skills/run-simple-fast-api/smoke.sh

# --- 프론트엔드 (frontend/next/) ---
cd frontend/next
npm install
npm run dev                               # 개발 서버 (turbopack) → http://localhost:3000
npm run build                             # 프로덕션 빌드
npm run lint                              # ESLint 검사 — PR 전 필수
```

> **자동화된 테스트 스위트는 없습니다.** 검증은 서버를 띄우고 실제 엔드포인트를
> 호출해 확인합니다 (예: `curl http://127.0.0.1:8000/financials/삼성전자`).
> 엔드포인트는 실제 DART·yfinance를 호출하므로, 가능하면 이미 캐시된 종목을
> 사용하세요 (`/cache/status`로 확인). QA는 `.claude/agents/tester.md` 서브에이전트 담당.

### 실행 시 주의 (Gotchas)

- `main.py`는 `DART_API_KEY`/`GEMINI_API_KEY`가 없으면 앱 생성 전에 `ValueError`로
  기동을 거부합니다 — 우회 방법 없음.
- 첫 실행은 matplotlib 폰트 캐시 빌드로 ~20초간 무응답입니다. readiness 폴링을
  넉넉히(60초) 잡으세요.
- `TELEGRAM_BOT_TOKEN`이 설정된 채 `main.py`를 실행하면 **실제 봇에 즉시 라이브
  폴링**을 시작합니다. 에이전트는 토큰을 비워주는 `smoke.sh`를 사용하세요
  (라이브 봇이 필요하면 `ENABLE_BOT=1 ./smoke.sh`).

## 환경변수

`simple_fast_api/.env`에 설정합니다 (`config.py`가 중앙 관리).

| 변수 | 필수 | 용도 |
|------|------|------|
| `DART_API_KEY` | ✅ | DART OpenAPI 인증 (없으면 기동 실패) |
| `GEMINI_API_KEY` | ✅ | Gemini AI 호출 (없으면 기동 실패) |
| `TELEGRAM_BOT_TOKEN` | ⬜ | 없으면 봇 비활성화, API만 동작 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | ⬜ | Naver 뉴스 검색 (`/events` 기능) |
| `GROQ_API_KEY` | ⬜ | Groq LLM 호출 (`/events` 이벤트 선별) |
| `WEBHOOK_SECRET_TOKEN` | ⬜ | `/webhook` 시크릿 검증 |
| `API_BASE_URL` | ⬜ | 봇→API 호출 주소 (기본 `http://localhost:8000`) |

## 아키텍처

```
Telegram User ─┐                          ┌─ Web (Next.js, useDartData 훅)
               ▼                          ▼
        bot.py ──(내부 HTTP, API_BASE_URL)──▶ routes/ ──▶ services/
                                              │             │
                                              ▼             ▼
                                          cache.py      외부 API (DART/Gemini/
                                         (diskcache)     Groq/Naver/yfinance)
        APScheduler (main.py lifespan)        │
        SQLite (database.py) ◀────────────────┘
```

**핵심: 봇은 백엔드 API의 클라이언트입니다.** `bot.py`는 비즈니스 로직을 직접
갖지 않고 자신의 FastAPI 엔드포인트를 HTTP로 호출하므로, 웹과 봇이 동일한
라우터/서비스를 공유합니다.

**계층 규칙**: `routes/`는 요청 검증 → 캐시 확인 → 서비스 위임 → 캐시 저장 →
응답 포맷만 담당하는 얇은 계층이고, 데이터 수집·계산·AI 호출은 `services/`에
둡니다. 동기 블로킹 호출(requests, 파일 IO)은 반드시 `asyncio.to_thread()`로
감쌉니다.

### 디렉토리 구조 (`simple_fast_api/`)

```
main.py            # 엔트리포인트: lifespan에서 DB 초기화, 봇 폴링, 스케줄러 등록
bot.py             # Telegram 커맨드 핸들러·알림 발송 (API 클라이언트)
config.py          # 모든 환경변수·상수·URL·모델명 중앙 관리 (← 상수는 여기서만)
database.py        # SQLite 비동기 접근 (favorites, filing_watch, search_stats)
cache.py           # DiskCache 인스턴스 정의 (기능별 *_cache, LRU max_size 10~20)
utils.py           # 공유 유틸: fmt_krw, call_gemini(_with_tools), call_groq, search_naver_news
routes/
├── data.py        #   /dividend-data /financials /business-overview /valuation /*-quarterly
├── ai.py          #   /report /buffett-report /chat /insider /score /events
├── system.py      #   /cache/* (status·clear·popular·warmup) /webhook 헬스체크
└── legacy.py      #   /analyze-dividends* — ZIP 파싱 구버전 (수정 자제)
services/
├── dart.py        #   DART API 호출·파싱·기업검색 (CORPCODE.xml)
├── valuation.py   #   PER/PBR/PSR/EV-EBIT 계산 (yfinance 주가)
├── scoring.py     #   정량 투자 스코어링 엔진
├── report.py      #   Gemini 리포트 생성 (일반·버핏 스타일)
├── chat.py        #   Gemini Function Calling 챗봇
├── insider.py     #   내부자 거래 분석
├── filing_alert.py#   신규 공시 감지·요약
├── events.py      #   주가 변곡점 이벤트: Naver 뉴스 검색 + Groq 선별 (AI가 기사를 지어내지 못하게 검색은 Naver가 수행)
└── cache_warmup.py#   search_stats 상위 종목 캐시 프리로드
```

### 백그라운드 작업 (APScheduler, 봇 토큰 있을 때만 등록)

| 작업 | 주기 | 함수 |
|------|------|------|
| 일일 즐겨찾기 요약 | 매일 09:00 KST | `bot.send_daily_notification` |
| 신규 공시 감지·푸시 | 30분 간격 | `bot.send_filing_alerts` |
| 인기 종목 캐시 워밍업 | 매일 05:30 KST | `services.cache_warmup.warm_popular_companies` |

## 코딩 컨벤션

### Python (백엔드)
- **Docstring은 한국어**, 모든 공개 함수에 한 줄 요약을 답니다.
- 타입힌트 필수. 신형 문법 사용: `dict | None`, `list[dict]`.
- 새 상수/환경변수/URL/모델명은 반드시 `config.py`에 추가하고 import. 하드코딩 금지.
- 외부 호출은 비동기로. 블로킹 함수는 `asyncio.to_thread`로 오프로딩.
- 데이터를 못 찾으면 `HTTPException(status_code=404, detail="...")`. 봇은 404를
  받으면 유사 기업 추천(`_show_suggestions`)으로 폴백하므로 이 규약을 지키세요.
- Telegram 메시지는 `ParseMode.HTML`. 사용자 입력은 `_e()`(html escape),
  AI 출력은 `_md_to_html()`로 변환. 4096자 초과는 `_send_long()`으로 분할.

### TypeScript (프론트엔드)
- 데이터 패칭은 `src/lib/useDartData.ts` 훅을 재사용합니다. 새 fetch 로직을
  컴포넌트에 직접 작성하지 마세요.
- API 주소는 `process.env.NEXT_PUBLIC_API_BASE_URL`로 참조 (하드코딩 금지).

## 도메인 규칙

- **연도 범위**: 재무·배당은 "최근 5년"이 기본 (`config.YEAR_RANGE`). 연도 후보를
  넉넉히(6년) 병렬 조회한 뒤 유효한 5건만 사용합니다.
- **재무제표 우선순위**: 연결(CFS) → 개별(OFS) 순 (`config.FS_DIV_ORDER`).
- **금액 표기**: 사용자 노출 금액은 `utils.fmt_krw()`로 조/억 단위 포맷.
- **캐시**: 모든 조회 결과는 해당 `*_cache`에 저장하고 응답에 `cached` 플래그를
  포함합니다. 캐시 키는 회사명 원문입니다.
- **이벤트 분석** (`services/events.py`): 뉴스 검색은 Naver API가 수행하고 Groq는
  주어진 기사 목록 안에서만 선별합니다. 선정 기준은 밸류에이션·내러티브 중요도이며
  주가 등락률은 참고 정보로만 계산합니다. Groq 무료 티어 토큰 한도(TPM) 때문에
  프롬프트에 넣는 기사 수·요약 길이에 상한이 있습니다.

## 경계 — 하지 말아야 할 것

- 🚫 비밀키(`.env`, 토큰)를 커밋·로그·코드에 절대 노출하지 않습니다.
  (로컬 `.env`에는 실제 키가 들어 있습니다.)
- 🚫 `routes/legacy.py`, 루트 `backend/`, `frontend/json-server/`는 명시적 요청 없이 수정하지 않습니다.
- 🚫 `CORPCODE.xml`, `*.zip`, `bot_data.db`, `dart_reports/`, `.cache/` 등 생성·데이터 파일을 커밋하지 않습니다.
- 🚫 이벤트 루프에서 동기 블로킹 호출을 직접 실행하지 않습니다 → `asyncio.to_thread`.

## Git 워크플로우

- 기능 브랜치에서 작업하고, 명확하고 서술적인 커밋 메시지(한국어 가능)를 작성합니다.
- 커밋 전 백엔드는 서버 기동 확인(또는 `smoke.sh`), 프론트엔드는 `npm run lint` 통과.
- 작업 완료 시 PR을 **draft**로 생성합니다.

## 하네스 구성 (Skills & Agents)

구현 완료 후 메인 세션이 **병렬로** 호출하는 서브에이전트가 `.claude/agents/`에
정의되어 있습니다. 운영 원칙은 `docs/harness-engineering.md` 참고.

| 이름 | 종류 | 역할 |
|------|------|------|
| `reviewer` | 에이전트 | 품질·보안·성능 코드 리뷰 보고서 반환 |
| `tester` | 에이전트 | 서버 실행·API 호출로 동작 검증 |
| `run-simple-fast-api` | 스킬 | 백엔드 서버 기동·스모크 테스트 (`simple_fast_api/.claude/skills/`) |
| `run-frontend-next` | 스킬 | Next.js 프론트 기동·확인 (`frontend/next/.claude/skills/`) |
