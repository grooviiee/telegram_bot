# Telegram 로컬 AI

`simple_fast_api/.env`에 `AI_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M`,
`OLLAMA_BASE_URL=http://127.0.0.1:11434`를 설정하고 서버를 재시작합니다.
Gemini 키는 로컬 모드에서 필요하지 않습니다. Ollama 연결 실패 시 외부 AI로 자동 전환하지 않습니다.

Windows의 Ollama 사용자 환경변수는 `OLLAMA_VULKAN=1`,
`OLLAMA_LLM_LIBRARY=vulkan`, `OLLAMA_FLASH_ATTENTION=0`으로 설정하고
Ollama를 완전히 종료한 후 재시작합니다. 이 PC에서는 모델 경로가
`F:\AI\Ollama\models`이고, `OLLAMA_NO_CLOUD=1`을 사용합니다.
로그에 `library=Vulkan`이 나오는지 확인합니다. 다른 버전에서는 백엔드 선택 방식을 다시 확인해야 합니다.

- `/ask 영업이익률이 뭐야?`: 공시 조회 없이 일반 개념 질문
- `/ai`: 제공자, 모델, 연결 및 GPU 메모리 적재 상태
- `/chat 삼성전자`: DART 데이터를 바탕으로 기업 상담, `/end`로 종료
- `/report 삼성전자`, `/buffett 삼성전자`: AI 리포트

PC, Ollama, 봇 서버가 켜져 있어야 합니다. 모델은 한 번에 한 요청을 처리하며
대화와 자료 일부는 문맥 제한으로 생략될 수 있습니다. 이 경우 답변에 표시합니다.
잘린 응답이나 추론만 나온 응답은 실패로 처리합니다. 로컬 소형 모델의 답변은
공시 원문과 함께 확인하세요. `/ask`는 최신 기업 실적을 조회하지 않습니다.

모델은 [공식 Qwen3 4B Instruct 배포](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)를 사용합니다.
같은 4B 계열의 Thinking 모델은 긴 추론으로 응답이 잘릴 수 있어 텔레그램 기본값에서 제외했습니다.
