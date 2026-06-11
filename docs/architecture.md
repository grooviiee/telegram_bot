# 아키텍처 (Architecture)

DART 공시 데이터 기반 한국 기업 재무분석 서비스의 시스템 구조를 설명합니다.

## 시스템 개요

```
 ┌──────────────┐        ┌──────────────┐
 │ Telegram User │       │  Web (Next.js)│
 └──────┬───────┘        └──────┬───────┘
        │ 명령어/메시지            │ HTTP fetch (useDartData)
        ▼                        ▼
 ┌──────────────────────────────────────────────┐
 │            FastAPI 백엔드 (simple_fast_api)     │
 │                                                │
 │  bot.py ──(내부 HTTP)──▶ routes/ ──▶ services/  │
 │     │                      │            │       │
 │     │                      ▼            ▼       │
 │     │                   cache.py    외부 API     │
 │     │                  (diskcache)  DART/Gemini  │
 │     ▼                                           │
 │  APScheduler (일일알림 09:00 / 공시감지 30분)     │
 └───────────────┬────────────────────────────────┘
                 ▼
         SQLite (database.py)
       favorites · filing_watch
```

## 계층 구조

| 계층 | 책임 | 비고 |
|------|------|------|
| **인터페이스** | Telegram(`bot.py`), Web(`frontend/next`) | 사용자 입출력·포맷팅 |
| **라우터** (`routes/`) | 요청 검증, 캐시 확인, 응답 포맷 | 얇게 유지 |
| **서비스** (`services/`) | 데이터 수집·계산·AI 호출 | 무거운 로직 집중 |
| **인프라** | `cache.py`, `database.py`, `config.py`, `utils.py` | 공통 자원 |

> **봇은 백엔드 API의 클라이언트입니다.** `bot.py`는 비즈니스 로직을 직접 갖지
> 않고, `API_BASE_URL`로 자신의 FastAPI 엔드포인트를 HTTP 호출합니다.
> 따라서 웹과 봇은 동일한 라우터/서비스를 공유합니다.

## 라우터별 책임

| 라우터 | 주요 엔드포인트 | 설명 |
|--------|----------------|------|
| `routes/data.py` | `/dividend-data` `/financials` `/business-overview` `/valuation` `/*-quarterly` | DART 원천 데이터 조회 |
| `routes/ai.py` | `/report` `/buffett-report` `/chat` `/insider` `/score` | Gemini AI·정량 스코어링 |
| `routes/system.py` | `/cache/status` `/cache/clear` `/webhook` `/` | 운영·캐시·웹훅 |
| `routes/legacy.py` | `/analyze-dividends` `/analyze-dividends-json` | ZIP 파싱 구버전(레거시) |

## 데이터 흐름 — 조회 요청 예시

`/financials/{회사명}` 호출 시:

1. **캐시 확인** — `financials_cache.get(회사명)` 히트 시 `cached: true`로 즉시 반환.
2. **회사코드 조회** — `get_corp_code()`로 `CORPCODE.xml`에서 corp_code 매칭.
3. **병렬 수집** — 최근 6개 연도를 `asyncio.gather` + `to_thread`로 DART 동시 호출.
4. **정제** — 유효한 5건만 선별, 연도순 정렬.
5. **실패 처리** — 데이터 없으면 `404` → 봇은 유사 기업 추천으로 폴백.
6. **캐시 저장** 후 응답.

## 백그라운드 작업 (APScheduler)

`main.py`의 lifespan에서 봇 토큰이 있을 때만 등록됩니다.

| 작업 | 주기 | 함수 |
|------|------|------|
| 일일 즐겨찾기 요약 | 매일 09:00 KST | `bot.send_daily_notification` |
| 신규 공시 감지·푸시 | 30분 간격 | `bot.send_filing_alerts` |

공시 감지는 `filing_watch` 테이블에 마지막 접수번호(`last_rcept_no`)를 기록해
중복 알림을 방지합니다.

## 외부 의존성

| 서비스 | 용도 | 설정 |
|--------|------|------|
| DART OpenAPI | 공시·재무·배당·내부자 데이터 | `DART_API_KEY` |
| Google Gemini (`gemini-2.5-flash`) | 리포트·챗·요약 (Function Calling, Thinking) | `GEMINI_API_KEY` |
| yfinance | 주가·시가총액 (밸류에이션) | 무인증 |
| Telegram Bot API | 봇 인터페이스 | `TELEGRAM_BOT_TOKEN` |

## 영속성

- **캐시**: `cache.py`의 `DiskCache` — 파일 기반 LRU(최근 20개), 서버 재시작 후 유지.
- **DB**: SQLite 2개 테이블 — `favorites`(즐겨찾기), `filing_watch`(공시 추적).

기능 요구사항 전체 목록은 별도 FR 명세를 참고하세요.
