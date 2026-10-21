export const ANALYSIS_PAGES = [
  { key: 'home', label: '종합 분석' },
  { key: 'business', label: '사업 분석' },
  { key: 'dividend', label: '배당 분석' },
  { key: 'profitability', label: '수익성 & 성장성' },
  { key: 'financial-health', label: '재무 건전성' },
  { key: 'valuation', label: '밸류에이션' },
  { key: 'buffett', label: '버핏 리포트' },
  { key: 'report', label: 'AI 리포트' },
  { key: 'chat', label: 'AI 상담' },
  { key: 'events', label: '주가 이벤트' },
];

export const PAGE_LABELS: Record<string, string> = Object.fromEntries(
  ANALYSIS_PAGES.map(({ key, label }) => [key, label]),
);
// 이전 버전에서 저장한 종합 분석 즐겨찾기도 같은 화면으로 연결합니다.
PAGE_LABELS.analysis = PAGE_LABELS.home;

export const normalizePage = (page: string): string => page === 'analysis' ? 'home' : page;
