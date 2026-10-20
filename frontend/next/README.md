# 기업 분석 웹

Next.js 15 / React 19 기반 DART 기업 분석 화면입니다.

```bash
npm ci
npm run dev
```

기본 주소는 `http://localhost:3000`입니다. API 주소는 `NEXT_PUBLIC_API_BASE_URL`로 지정하며 기본값은 `http://localhost:8000`입니다.

```bash
npm run lint
npx tsc --noEmit
npm run build
npx playwright install chromium
# 웹 서버가 실행 중인 별도 터미널에서:
npm run test:ux
```

브라우저 검증은 API 응답을 대체하므로 실제 API 키가 필요하지 않습니다. 다른 웹 주소는 `UX_BASE_URL`로 지정합니다.

화면 구현은 `src/components/screens/`, 검색·요청 처리는 `src/components/CompanySearch.tsx`와 `src/lib/useDartData.ts`를 사용합니다. `src/app/*/page.tsx`는 진입할 분석 화면을 지정합니다.

사용 흐름과 검증 범위는 [기존 분석 기능 UX](../../docs/existing-feature-ux.md)를 참고하세요.
