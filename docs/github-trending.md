# GitHub 핫 프로젝트 소개

기존 DART 봇에 분야 제한 없는 GitHub 소개 기능을 추가합니다. python-telegram-bot, APScheduler, 비동기 SQLite와 기존 Gemini 호출 함수를 재사용합니다. 새 봇 토큰이나 OpenAI 키는 필요하지 않습니다.

## Telegram에서 사용

- `/today`: 오늘의 프로젝트 최대 3개를 즉시 받습니다.
- `/trend_on`: 봇과의 **개인 채팅**에서 매일 오전 9시(KST) 소개를 신청합니다.
- `/trend_off`: 정기 소개를 해제합니다.

신청한 채팅 ID는 기존 `bot_data.db`에 자동 저장됩니다. `TELEGRAM_CHAT_ID`나 별도의 `.env` 파일은 필요하지 않습니다. 기존 서버의 `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, DART 기능용 `DART_API_KEY` 설정을 그대로 사용합니다. 배포 환경의 환경 변수/Secrets로 주입해도 됩니다. 배포 환경의 환경 변수/Secrets가 로컬 .env보다 우선하며, .env는 미설정 항목만 채웁니다.

선택적으로 `GITHUB_TOKEN`을 기존 배포 환경의 Secret에 추가하면 README API 호출 한도를 늘릴 수 있습니다. 키를 저장소에 커밋하지 마세요.

## 선정과 메시지

GitHub **일간 Trending 후보**를 오늘 증가한 스타 수로 정렬합니다. 전체 GitHub 저장소 순위를 의미하지 않습니다. 해당 채팅에 최근 7일 동안 성공적으로 소개한 저장소를 제외하고 최대 3개를 선정합니다.

README와 설명으로 Gemini가 한국어 소개·특징·활용 아이디어를 작성합니다. 오늘 증가량, 누적 스타, 언어, 저장소 링크, 최초 수집 시각도 표시합니다. README 미수집은 메시지에 표시합니다. Gemini 키가 없거나 호출에 실패하면 **원문 소개**를 표시합니다. 저장소 기능·성능은 작성자 자료이며 독립 검증이 아닙니다. 활용 아이디어는 제안입니다.

## 캐시 및 발송

- 당일 후보와 프로젝트 소개는 DiskCache로 공유해 구독자별 외부 호출을 줄입니다.
- 채팅별 당일 소개는 SQLite에 저장됩니다. `/today` 재조회는 같은 소개를 다시 보냅니다.
- `/today`를 먼저 받았다면 그날 자동 발송은 생략합니다.
- 봇을 차단해 Telegram 접근이 거부된 채팅은 자동으로 구독을 해제합니다.
- 정기 발송은 오전 9시이며 5분마다 미발송분을 재시도합니다. 9시 이후 서버를 시작해도 다음 실행 때 발송합니다.
- 발송 성공 후 기록을 저장합니다. Telegram 전송 직후 DB 기록 전에 서버가 종료되면 중복될 수 있습니다.
- 후보가 부족하면 1~2개, 모두 최근 소개한 후보이면 안내 메시지를 보냅니다.
- 채팅별 잠금으로 명령과 스케줄의 경합을 방지합니다. 봇 서버는 **프로세스 하나**로 실행하세요.
- 당일 캐시를 만든 후 AI 키를 바꿔도 해당 채팅의 소개는 그날 유지됩니다.
- 기존 DB 시작 절차에서 새 테이블만 생성하며 즐겨찾기·공시 추적 데이터를 보존합니다.

## 미리보기 API

기존 서버를 시작하고 다음 주소를 호출합니다.

```bash
cd simple_fast_api
python main.py
curl http://127.0.0.1:8000/github/trending
```

Telegram 발송 없이 공용 소개용 캐시를 사용하며 사용자 발송 기록을 변경하지 않습니다. 응답은 `day`, `collected_at`, `projects`, `source`, `cached`를 포함합니다. 각 프로젝트는 `name`, `stars_today`, `stars`, `language`, `summary`, `ai_used`, `warnings`, `url`을 포함합니다. Trending 수집 장애나 HTML 구조 변경은 502로 응답하고 실패 결과를 캐시하지 않습니다.

## 검증

```bash
cd simple_fast_api
python -m unittest discover -s tests -v
```

GitHub 테스트는 임시 DB·캐시와 모의 API를 사용합니다. 실제 Telegram 메시지를 발송하거나 Gemini 비용을 발생시키지 않습니다.
