# AGENTS.md

> AI 코딩 에이전트를 위한 온보딩 문서. 이 저장소에서 작업하기 전에 먼저 읽으세요.
> 사람용 소개는 `README.md`, 개념·설계 배경은 `docs/`를 참고합니다.

## 프로젝트 개요

DART(전자공시) 공시 데이터를 수집·분석하여 한국 상장기업의 재무지표,
밸류에이션, AI 투자 리포트를 제공하는 서비스입니다. 사용자는 **Telegram 봇**
또는 **웹(Next.js)** 으로 기업을 검색하고 분석 결과를 받습니다.

| 구성 | 기술 | 위치 |
|------|------|------|
| 백엔드 API | FastAPI (Python 3.10+) | `simple_fast_api/` |
| Telegram 봇 | python-telegram-bot v20+ (polling) | `simple_fast_api/bot.py` |
| 웹 프론트엔드 | Next.js 15 / React 19 / TypeScript | `frontend/next/` |
| DB | SQLite (aiosqlite) — 즐겨찾기·공시추적 | `simple_fast_api/database.py` |
| 캐시 | diskcache 기반 LRU | `simple_fast_api/cache.py` |
| 외부 API | DART OpenAPI, Google Gemini, yfinance | `simple_fast_api/services/` |

**주 작업 대상은 `simple_fast_api/`입니다.** 루트의 `backend/`(Go·terraform 실험)와
`frontend/json-server/`(목업)는 레거시이므로 명시적 요청 없이는 수정하지 마세요.

## 빌드 · 실행 · 테스트 명령어

```bash
# --- 백엔드 (simple_fast_api/) ---
cd simple_fast_api
pip install -r requirements.txt          # 의존성 설치
cp .env.example .env                      # 환경변수 준비 (아래 '환경변수' 참고)
python main.py                            # 개발 서버 → http://127.0.0.1:8000
                                          # API 문서 → http://127.0.0.1:8000/docs
uvicorn main:app --reload --port 8000     # (대안) 핫리로드 실행

# --- 프론트엔드 (frontend/next/) ---
cd frontend/next
npm install
npm run dev                               # 개발 서버 (turbopack) → http://localhost:3000
npm run build                             # 프로덕션 빌드
npm run lint                              # ESLint 검사 — PR 전 필수
```

> **테스트 프레임워크는 아직 없습니다.** 검증은 서버를 띄우고 실제 엔드포인트를
> 호출해 확인합니다 (예: `curl http://127.0.0.1:8000/financials/삼성전자`).
> QA는 `.claude/agents/tester.md` 서브에이전트가 담당합니다.

## 환경변수

`simple_fast_api/.env`에 설정합니다. 키가 없으면 서버가 기동을 거부하거나
봇 기능이 비활성화됩니다 (`config.py`, `main.py` 참고).

| 변수 | 필수 | 용도 |
|------|------|------|
| `DART_API_KEY` | ✅ | DART OpenAPI 인증 (없으면 기동 실패) |
| `GEMINI_API_KEY` | ✅ | Gemini AI 호출 (없으면 기동 실패) |
| `TELEGRAM_BOT_TOKEN` | ⬜ | 없으면 봇 비활성화, API만 동작 |
| `WEBHOOK_SECRET_TOKEN` | ⬜ | `/webhook` 시크릿 검증 |
| `API_BASE_URL` | ⬜ | 봇→API 호출 주소 (기본 `http://localhost:8000`) |

## 디렉토리 구조

```
simple_fast_api/
├── main.py            # FastAPI 엔트리포인트, lifespan, 스케줄러, 봇 기동
├── bot.py             # Telegram 커맨드 핸들러·알림 발송
├── config.py          # 모든 환경변수·상수·URL 중앙 관리 (← 상수는 여기서만)
├── database.py        # SQLite 비동기 접근 (favorites, filing_watch)
├── cache.py           # DiskCache 인스턴스 정의
├── utils.py           # 공유 유틸 (fmt_krw, Gemini 호출 래퍼)
├── routes/            # API 라우터 (HTTP 계층, 얇게 유지)
│   ├── data.py        #   배당·재무·사업개요·밸류에이션 조회
│   ├── ai.py          #   리포트·챗·스코어·내부자 분석
│   ├── system.py      #   캐시 관리·webhook·헬스체크
│   └── legacy.py      #   ZIP 파싱 기반 구버전 (수정 자제)
└── services/          # 도메인 로직 (비즈니스 계층, 무거운 작업)
    ├── dart.py        #   DART API 호출·파싱·기업검색
    ├── valuation.py   #   PER/PBR/PSR/EV-EBIT 계산
    ├── scoring.py     #   정량 투자 스코어링 엔진
    ├── report.py      #   Gemini 리포트 생성
    ├── chat.py        #   Function Calling 챗봇
    ├── insider.py     #   내부자 거래 분석
    └── filing_alert.py#   신규 공시 감지·요약
```

**계층 규칙**: `routes/`는 요청 검증·캐시 확인·응답 포맷만 담당하고,
실제 데이터 수집/계산은 `services/`에 둡니다. 동기 블로킹 호출(DART·파일 IO)은
반드시 `asyncio.to_thread()`로 감쌉니다.

## 코딩 컨벤션

### Python (백엔드)
- **Docstring은 한국어**, 모든 공개 함수에 한 줄 요약을 답니다.
- 타입힌트 필수. 신형 문법 사용: `dict | None`, `list[dict]`.
- 새 상수/환경변수/URL은 반드시 `config.py`에 추가하고 import 합니다. 하드코딩 금지.
- 외부 호출은 비동기로. 블로킹 함수는 `asyncio.to_thread`로 오프로딩:

```python
# 좋은 예 — routes 계층: 캐시 확인 → 서비스 위임 → 캐시 저장
@router.get("/financials/{company_name}")
async def get_financials(company_name: str):
    cached = financials_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await asyncio.to_thread(get_corp_code, company_name)  # 블로킹 오프로딩
    financials = await asyncio.gather(...)
    if not financials:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 재무 데이터를 찾을 수 없습니다.")

    result = {'company_name': company_name, 'financials': financials}
    financials_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})
```

- 데이터를 못 찾으면 `HTTPException(status_code=404, detail="...")`. 봇은 404를
  받으면 유사 기업 추천(`_show_suggestions`)으로 폴백하므로 이 규약을 지키세요.
- Telegram 메시지는 `ParseMode.HTML`을 쓰고, 사용자 입력은 `_e()`(html escape),
  AI 출력은 `_md_to_html()`로 변환합니다. 4096자 초과는 `_send_long()`으로 분할.

### TypeScript (프론트엔드)
- 데이터 패칭은 `src/lib/useDartData.ts` 훅을 재사용합니다. 새 fetch 로직을
  컴포넌트에 직접 작성하지 마세요.
- API 주소는 `process.env.NEXT_PUBLIC_API_BASE_URL`로 참조 (하드코딩 금지).

## 도메인 규칙 (Rules)

- **연도 범위**: 재무·배당은 "최근 5년"이 기본 (`config.YEAR_RANGE`). 연도 후보를
  넉넉히(6년) 조회한 뒤 유효한 5건만 사용합니다.
- **재무제표 우선순위**: 연결(CFS) → 개별(OFS) 순 (`config.FS_DIV_ORDER`).
- **금액 표기**: 사용자 노출 금액은 `utils.fmt_krw()`로 조/억 단위 포맷.
- **캐시**: 모든 조회 결과는 해당 `*_cache`에 저장하고 응답에 `cached` 플래그를
  포함합니다. 캐시 키는 회사명 원문입니다.
- **스케줄 작업**: 일일 요약(매일 09:00 KST), 신규 공시 감지(30분 주기)는
  `main.py`의 APScheduler에 등록되어 있습니다.

## 경계 — 하지 말아야 할 것 (Boundaries)

- 🚫 비밀키(`.env`, 토큰)를 커밋·로그·코드에 절대 노출하지 않습니다.
- 🚫 `routes/legacy.py`, 루트 `backend/`, `frontend/json-server/`는 명시적 요청 없이 수정하지 않습니다.
- 🚫 `CORPCODE.xml`, `*.zip`, `bot_data.db`, `dart_reports/` 등 생성·데이터 파일을 커밋하지 않습니다 (`.gitignore` 확인).
- 🚫 이벤트 루프에서 동기 블로킹 호출(requests, 파일 IO)을 직접 실행하지 않습니다 → `asyncio.to_thread`.
- 🚫 상수·URL·모델명을 파일 곳곳에 하드코딩하지 않습니다 → `config.py`.

## Git 워크플로우

- 기능 브랜치에서 작업하고, 명확하고 서술적인 커밋 메시지(한국어 가능)를 작성합니다.
- 커밋 전 백엔드는 서버 기동 확인, 프론트엔드는 `npm run lint`를 통과시킵니다.
- 작업 완료 시 PR을 **draft**로 생성합니다.

## 하네스 구성 (Skills & Agents)

이 저장소는 하네스 엔지니어링 원칙에 따라 서브에이전트를 정의해 두었습니다
(`.claude/agents/`). 구현 완료 후 메인 세션이 **병렬로** 호출합니다.

| 에이전트 | 역할 | 트리거 예시 |
|----------|------|-------------|
| `reviewer` | 품질·보안·성능 코드 리뷰 보고서 반환 | "방금 구현한 코드 리뷰해줘" |
| `tester` | 서버 실행·API 호출로 동작 검증 | "실제로 동작하는지 확인해줘" |

자세한 개념과 운영 방식은 `docs/harness-engineering.md`를 참고하세요.
