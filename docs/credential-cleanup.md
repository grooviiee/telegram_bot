# Credential 노출 정리

## 현재 파일 정리

- `simple_fast_api/.env`를 Git 추적에서 제거합니다. 로컬 파일은 보존되지만 커밋되지 않습니다.
- `backend/config.yaml`, `backend/get_api_test.py`, `common/config.yaml`의 하드코딩된 DART 키를 제거합니다.
- 레거시 Python 실행 파일도 `DART_API_KEY` 환경 변수를 사용합니다.
- 레거시 HTTP 요청 오류는 인증키가 포함된 URL을 출력하지 않고 예외 종류만 기록합니다.
- GitHub Actions에서 추적 파일의 credential 패턴 검사를 실행합니다.
- 기존 FastAPI 서버는 `DART_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN` 환경 변수를 사용합니다. 비밀값 없는 `.env.example`만 배포합니다.
- `python scripts/check_secrets.py`로 추적 중인 텍스트 파일의 알려진 credential 형식을 검사합니다. 출력에는 값이 포함되지 않습니다. 이 검사는 모든 형태의 비밀값을 찾아낸다는 보장이 없습니다.

## 소유자가 처리할 사항

이미 노출된 값은 삭제만으로 보호되지 않습니다. DART와 Google AI Studio에서 키를 폐기하고 새 키를 발급하세요. Telegram의 과거 토큰도 BotFather에서 폐기·재발급하세요. 새 값은 배포 환경의 Secrets나 Git이 무시하는 로컬 `.env`에 저장하세요. API 사용 기록과 비정상 요청도 확인하세요.

## 과거 Git 이력

이번 변경은 현재 파일만 정리하며 과거 커밋은 그대로 남습니다. 과거 `init.py`, `README.md`, `.env`와 설정 파일에 들어 있던 값도 회전 대상입니다. 값을 문서·로그·이슈에 복사하지 마세요.

과거 이력을 지우려면 `git-filter-repo` 등을 이용한 전체 branch/tag 이력 재작성과 강제 push가 필요합니다. 협업자의 기존 clone과 커밋 SHA에 영향을 주므로 별도 작업으로 진행해야 합니다. 재작성 후에도 PR 참조·포크·기존 clone·GitHub 캐시에 값이 남을 수 있어 키 폐기·재발급이 먼저입니다. 필요한 경우 GitHub 지원에 민감 데이터 캐시 제거를 요청하세요.
