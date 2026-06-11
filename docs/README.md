# 문서 (docs)

DART 재무분석 서비스의 개발 문서 모음입니다.

| 문서 | 내용 |
|------|------|
| [harness-engineering.md](./harness-engineering.md) | 하네스 엔지니어링 개념과 본 저장소 적용 방식 |
| [architecture.md](./architecture.md) | 시스템 구조, 계층, 데이터 흐름, 외부 의존성 |

## 관련 문서

- [`../AGENTS.md`](../AGENTS.md) — AI 코딩 에이전트용 온보딩·규칙·경계
- [`../README.md`](../README.md) — 프로젝트 개요 (사람용)
- [`../Arhitecture.md`](../Arhitecture.md) — 초기 기획 메모

## 빠른 시작

```bash
# 백엔드
cd simple_fast_api
pip install -r requirements.txt
cp .env.example .env   # 키 입력
python main.py         # http://127.0.0.1:8000/docs

# 프론트엔드
cd frontend/next
npm install && npm run dev
```
