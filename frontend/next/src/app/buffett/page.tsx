/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  BarElement, LineElement, PointElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { Bar, Line } from 'react-chartjs-2';
import { ProgressIndicator } from '@/components/ProgressIndicator';

ChartJS.register(
  CategoryScale, LinearScale,
  BarElement, LineElement, PointElement,
  Title, Tooltip, Legend, Filler,
);

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

// ── 타입 ─────────────────────────────────────────────────────────────────
interface FinancialYear {
  year: number;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  roe: number | null;
  operating_margin: number | null;
  debt_ratio: number | null;
  fcf: number | null;
  equity: number | null;
  total_assets: number | null;
}

interface ValuationHistory {
  year: number;
  per: number | null;
  pbr: number | null;
  ev_ebit: number | null;
}

interface ScoreCategory {
  score: number;
  grade: string;
}

interface ScoreData {
  total_score: number;
  total_grade: string;
  categories: {
    growth: ScoreCategory;
    profitability: ScoreCategory;
    financial_health: ScoreCategory;
    dividend: ScoreCategory;
    valuation: ScoreCategory;
  };
  key_signals: { text: string; type: 'positive' | 'negative' | 'neutral' }[];
}

interface BuffettData {
  financials: FinancialYear[];
  valHistory: ValuationHistory[];
  score: ScoreData;
  report: string;
}

// ── Props ─────────────────────────────────────────────────────────────────
interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

const PAGE_KEY = 'buffett';

// ── 상수 ──────────────────────────────────────────────────────────────────
const STEPS = [
  { label: '기업 코드 조회 중',           after: 0 },
  { label: '5개년 재무 데이터 수집 중',   after: 1_500 },
  { label: '밸류에이션 및 스코어 계산 중', after: 3_500 },
  { label: 'AI 버핏 리포트 생성 중',      after: 6_000 },
];

// ── 유틸 ──────────────────────────────────────────────────────────────────
const toEok = (v: number | null | undefined) =>
  v != null ? Math.round(v / 1e8 * 10) / 10 : null;

const gradeColor = (grade: string) => {
  if (['A+', 'A'].includes(grade)) return 'text-emerald-600';
  if (['B+', 'B'].includes(grade)) return 'text-blue-600';
  if (['C+', 'C'].includes(grade)) return 'text-amber-500';
  return 'text-red-500';
};

const gradeLabel: Record<string, string> = {
  'A+': '최우수', A: '우수', 'B+': '양호', B: '보통',
  'C+': '주의', C: '미흡', D: '부진', F: '매우 부진',
};

// ── 마크다운 렌더러 ────────────────────────────────────────────────────────
function renderMarkdown(text: string) {
  const elements: React.ReactNode[] = [];
  let key = 0;
  for (const line of text.split('\n')) {
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={key++} className="text-xl font-bold text-gray-800 mt-6 mb-3">{line.slice(3)}</h2>
      );
    } else if (line.startsWith('### ')) {
      elements.push(
        <h3 key={key++} className="text-base font-semibold text-amber-700 mt-5 mb-2">{line.slice(4)}</h3>
      );
    } else if (line.startsWith('**') && line.endsWith('**')) {
      const content = line.slice(2, -2);
      const color = content.includes('긍정') ? 'text-emerald-600'
        : content.includes('부정') || content.includes('부적합') ? 'text-red-500'
        : content.includes('대기') || content.includes('보류') ? 'text-amber-500'
        : 'text-amber-700';
      elements.push(
        <p key={key++} className={`font-bold text-lg mb-2 ${color}`}>{content}</p>
      );
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <li key={key++} className="text-sm text-gray-700 ml-4 list-disc mb-1 leading-relaxed">
          {line.slice(2)}
        </li>
      );
    } else if (line.startsWith('---')) {
      elements.push(<hr key={key++} className="border-gray-200 my-4" />);
    } else if (line.startsWith('*') && line.endsWith('*')) {
      elements.push(
        <p key={key++} className="text-xs text-gray-400 mt-4 italic">{line.slice(1, -1)}</p>
      );
    } else if (line.trim()) {
      elements.push(
        <p key={key++} className="text-sm text-gray-700 leading-relaxed mb-2">{line}</p>
      );
    }
  }
  return elements;
}

// ── 차트 공통 옵션 ────────────────────────────────────────────────────────
const lineOpts = (title: string, yLabel: string, extra?: object) => ({
  responsive: true, spanGaps: true,
  plugins: {
    legend: { position: 'top' as const },
    title: { display: true, text: title, font: { size: 13 } },
    tooltip: { callbacks: { label: (ctx: any) => `${ctx.dataset.label}: ${ctx.parsed.y?.toLocaleString()}` } },
  },
  scales: {
    y: { title: { display: true, text: yLabel }, ticks: { callback: (v: any) => Number(v).toLocaleString() } },
  },
  ...extra,
});

const barOpts = (title: string, yLabel: string, extra?: object) => ({
  responsive: true,
  plugins: {
    legend: { position: 'top' as const },
    title: { display: true, text: title, font: { size: 13 } },
    tooltip: { callbacks: { label: (ctx: any) => `${ctx.dataset.label}: ${ctx.parsed.y?.toLocaleString()}` } },
  },
  scales: {
    y: { title: { display: true, text: yLabel }, ticks: { callback: (v: any) => Number(v).toLocaleString() } },
  },
  ...extra,
});

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────
export default function BuffettPage({ toggleFavorite, isFavorite, initialCompany, onSearched }: Props = {}) {
  const [companyName, setCompanyName] = useState(initialCompany ?? '');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [resolvedName, setResolvedName] = useState('');
  const [data, setData] = useState<BuffettData | null>(null);
  const fetchedRef = useRef<string | null>(null);

  const fetchData = useCallback(async (name?: string) => {
    const target = (name ?? companyName).trim();
    if (!target) return;
    if (fetchedRef.current === target) return;
    fetchedRef.current = target;

    setLoading(true);
    setMessage('');
    setData(null);

    try {
      const enc = encodeURIComponent(target);
      const [finRes, valRes, scoreRes, reportRes] = await Promise.all([
        fetch(`${API_BASE}/financials/${enc}`,       { signal: AbortSignal.timeout(60_000) }),
        fetch(`${API_BASE}/valuation/${enc}`,         { signal: AbortSignal.timeout(60_000) }),
        fetch(`${API_BASE}/score/${enc}`,             { signal: AbortSignal.timeout(60_000) }),
        fetch(`${API_BASE}/buffett-report/${enc}`,    { signal: AbortSignal.timeout(180_000) }),
      ]);

      if (!finRes.ok || !valRes.ok || !scoreRes.ok || !reportRes.ok)
        throw new Error('일부 데이터 조회에 실패했습니다.');

      const [finJson, valJson, scoreJson, reportJson] = await Promise.all([
        finRes.json(), valRes.json(), scoreRes.json(), reportRes.json(),
      ]) as any[];

      setResolvedName(reportJson.company_name ?? target);
      setData({
        financials: finJson.financials ?? [],
        valHistory: valJson.history ?? [],
        score: scoreJson,
        report: reportJson.report ?? '',
      });
      setMessage(`${reportJson.company_name} 버핏 리포트 생성 완료${reportJson.cached ? ' (캐시)' : ''}`);
      onSearched?.();
    } catch (e: any) {
      fetchedRef.current = null;
      setMessage(`오류: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [companyName, onSearched]);

  React.useEffect(() => {
    if (initialCompany && fetchedRef.current !== initialCompany) fetchData(initialCompany);
  }, [initialCompany, fetchData]);

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  // ── 차트 데이터 계산 ──────────────────────────────────────────────────
  const fins = data?.financials.slice().sort((a, b) => a.year - b.year) ?? [];
  const years = fins.map((f) => `${f.year}년`);

  // 1. ROE 추세 + 15% 기준선
  const roeChartData = {
    labels: years,
    datasets: [
      {
        label: 'ROE (%)',
        data: fins.map((f) => f.roe),
        borderColor: 'rgba(239, 68, 68, 1)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        fill: true, tension: 0.3, pointRadius: 5,
      },
      {
        label: '버핏 기준 (15%)',
        data: fins.map(() => 15),
        borderColor: 'rgba(16, 185, 129, 0.7)',
        borderDash: [6, 4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0,
      },
    ],
  };

  // 2. FCF vs 순이익 (이익의 질)
  const earningsQualityData = {
    labels: years,
    datasets: [
      {
        label: '당기순이익 (억원)',
        data: fins.map((f) => toEok(f.net_income)),
        backgroundColor: 'rgba(59, 130, 246, 0.7)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1,
      },
      {
        label: 'FCF · 오너이익 (억원)',
        data: fins.map((f) => toEok(f.fcf)),
        backgroundColor: 'rgba(16, 185, 129, 0.7)',
        borderColor: 'rgba(16, 185, 129, 1)',
        borderWidth: 1,
      },
    ],
  };

  // 3. 영업이익률 추세
  const marginChartData = {
    labels: years,
    datasets: [
      {
        label: '영업이익률 (%)',
        data: fins.map((f) => f.operating_margin),
        borderColor: 'rgba(245, 158, 11, 1)',
        backgroundColor: 'rgba(245, 158, 11, 0.1)',
        fill: true, tension: 0.3, pointRadius: 5,
      },
    ],
  };

  // 4. 부채비율 추세
  const debtChartData = {
    labels: years,
    datasets: [
      {
        label: '부채비율 (%)',
        data: fins.map((f) => f.debt_ratio),
        backgroundColor: fins.map((f) =>
          (f.debt_ratio ?? 0) > 200 ? 'rgba(239, 68, 68, 0.75)' :
          (f.debt_ratio ?? 0) > 100 ? 'rgba(245, 158, 11, 0.75)' :
                                       'rgba(16, 185, 129, 0.75)'
        ),
        borderRadius: 4,
      },
    ],
  };

  // 5. 밸류에이션 히스토리 (PER / PBR)
  const valYears = (data?.valHistory ?? []).map((v) => `${v.year}년`);
  const valChartData = {
    labels: valYears,
    datasets: [
      {
        label: 'PER (배)',
        data: (data?.valHistory ?? []).map((v) => v.per),
        backgroundColor: 'rgba(139, 92, 246, 0.7)',
        borderColor: 'rgba(139, 92, 246, 1)',
        borderWidth: 1,
      },
      {
        label: 'PBR (배)',
        data: (data?.valHistory ?? []).map((v) => v.pbr),
        backgroundColor: 'rgba(249, 115, 22, 0.7)',
        borderColor: 'rgba(249, 115, 22, 1)',
        borderWidth: 1,
      },
    ],
  };

  // 6. 투자 스코어 (가로 막대)
  const CAT_LABELS: Record<string, string> = {
    growth: '성장성', profitability: '수익성',
    financial_health: '재무건전성', dividend: '배당', valuation: '밸류에이션',
  };
  const scoreCategories = data ? Object.entries(data.score.categories) : [];
  const scoreChartData = {
    labels: scoreCategories.map(([k]) => CAT_LABELS[k] ?? k),
    datasets: [
      {
        label: '카테고리 점수 (100점)',
        data: scoreCategories.map(([, v]) => v.score),
        backgroundColor: scoreCategories.map(([, v]) =>
          v.score >= 75 ? 'rgba(16, 185, 129, 0.75)' :
          v.score >= 55 ? 'rgba(59, 130, 246, 0.75)' :
          v.score >= 40 ? 'rgba(245, 158, 11, 0.75)' :
                          'rgba(239, 68, 68, 0.75)'
        ),
        borderRadius: 4,
      },
    ],
  };
  const scoreBarOpts = {
    indexAxis: 'y' as const,
    responsive: true,
    plugins: {
      legend: { display: false },
      title: { display: true, text: '투자 카테고리별 점수', font: { size: 13 } },
      tooltip: { callbacks: { label: (ctx: any) => `${ctx.parsed.x}점` } },
    },
    scales: {
      x: { min: 0, max: 100, ticks: { callback: (v: any) => `${v}점` } },
    },
  };

  // DuPont 분해 — 순이익률, 자산회전율(×10 스케일), 레버리지(×10 스케일)
  const dupont = fins.map((f) => {
    const netMargin = f.net_income && f.revenue ? f.net_income / f.revenue * 100 : null;
    const assetTurnover = f.revenue && f.total_assets ? f.revenue / f.total_assets * 10 : null; // ×10 for scale
    const leverage = f.total_assets && f.equity ? f.total_assets / f.equity * 10 : null; // ×10
    return { netMargin, assetTurnover, leverage };
  });

  const dupontChartData = {
    labels: years,
    datasets: [
      {
        label: '순이익률 (%)',
        data: dupont.map((d) => d.netMargin),
        borderColor: 'rgba(139, 92, 246, 1)',
        backgroundColor: 'rgba(139, 92, 246, 0.1)',
        fill: false, tension: 0.3, pointRadius: 4, yAxisID: 'y',
      },
      {
        label: '자산회전율 ×10',
        data: dupont.map((d) => d.assetTurnover),
        borderColor: 'rgba(245, 158, 11, 1)',
        backgroundColor: 'rgba(245, 158, 11, 0.1)',
        fill: false, tension: 0.3, pointRadius: 4, yAxisID: 'y',
        borderDash: [4, 2],
      },
      {
        label: '재무레버리지 ×10',
        data: dupont.map((d) => d.leverage),
        borderColor: 'rgba(239, 68, 68, 1)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        fill: false, tension: 0.3, pointRadius: 4, yAxisID: 'y',
        borderDash: [2, 2],
      },
      {
        label: 'ROE (%)',
        data: fins.map((f) => f.roe),
        borderColor: 'rgba(16, 185, 129, 1)',
        backgroundColor: 'rgba(16, 185, 129, 0.15)',
        fill: false, tension: 0.3, pointRadius: 5,
        borderWidth: 2.5, yAxisID: 'y',
      },
    ],
  };

  const dupontOpts = lineOpts('DuPont ROE 분해 분석', '%');

  return (
    <div className="p-6 bg-gray-50 min-h-screen">

      {/* 헤더 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">🧙 버핏 스타일 투자 리포트</h1>
        <p className="text-sm text-gray-500">
          워렌 버핏 투자 철학 기반 — 해자 · 내재가치 · 안전마진 시각화 대시보드
        </p>
      </div>

      {/* 검색 */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="회사명 입력 (예: 삼성전자)"
          value={companyName}
          onChange={(e) => { setCompanyName(e.target.value); fetchedRef.current = null; }}
          onKeyDown={(e) => e.key === 'Enter' && fetchData()}
          disabled={loading}
          className="flex-1 max-w-xs px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-50"
        />
        <button
          onClick={() => fetchData()}
          disabled={loading}
          className="px-5 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors"
        >
          {loading ? '분석 중...' : '버핏 분석'}
        </button>
        {resolvedName && toggleFavorite && (
          <button
            onClick={() => toggleFavorite(resolvedName, PAGE_KEY)}
            className={`px-3 py-2 rounded-lg text-xl leading-none transition-colors ${starred ? 'text-yellow-400 hover:text-gray-300' : 'text-gray-300 hover:text-yellow-400'}`}
          >
            {starred ? '★' : '☆'}
          </button>
        )}
      </div>

      <ProgressIndicator steps={STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {data && (
        <>
          {/* ── 스코어 요약 카드 ── */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
            {/* 총점 */}
            <div className="col-span-2 bg-amber-50 border border-amber-200 rounded-xl p-4 flex flex-col items-center justify-center">
              <p className="text-xs text-amber-600 font-semibold mb-1">종합 투자 점수</p>
              <p className={`text-4xl font-bold ${gradeColor(data.score.total_grade)}`}>
                {data.score.total_score.toFixed(0)}
              </p>
              <p className={`text-sm font-semibold mt-1 ${gradeColor(data.score.total_grade)}`}>
                {data.score.total_grade} · {gradeLabel[data.score.total_grade]}
              </p>
            </div>
            {/* 카테고리별 */}
            {Object.entries(data.score.categories).map(([key, cat]) => (
              <div key={key} className="bg-white border border-gray-100 rounded-xl p-3 flex flex-col items-center shadow-sm">
                <p className="text-xs text-gray-500 mb-1">{CAT_LABELS[key]}</p>
                <p className={`text-2xl font-bold ${gradeColor(cat.grade)}`}>{cat.score.toFixed(0)}</p>
                <p className={`text-xs font-semibold ${gradeColor(cat.grade)}`}>{cat.grade}</p>
              </div>
            ))}
          </div>

          {/* ── 시그널 ── */}
          {data.score.key_signals.length > 0 && (
            <div className="bg-white border border-gray-100 rounded-xl p-4 mb-6 shadow-sm">
              <p className="text-sm font-semibold text-gray-700 mb-2">⚡ 자동 감지 시그널</p>
              <div className="flex flex-wrap gap-2">
                {data.score.key_signals.map((sig, i) => (
                  <span key={i} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${
                    sig.type === 'positive' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                    sig.type === 'negative' ? 'bg-red-50 text-red-700 border-red-200' :
                                             'bg-amber-50 text-amber-700 border-amber-200'
                  }`}>
                    {sig.type === 'positive' ? '🟢' : sig.type === 'negative' ? '🔴' : '🟡'} {sig.text}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ── 차트 대시보드 ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">

            {/* 1. ROE 추세 + 버핏 기준선 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <Line options={lineOpts('ROE 추이 (버핏 기준: 15% 이상)', '%')} data={roeChartData} />
              <p className="text-xs text-gray-400 mt-2 text-center">
                녹색 점선 = 버핏이 요구하는 최소 ROE 기준
              </p>
            </div>

            {/* 2. FCF vs 순이익 (이익의 질) */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <Bar options={barOpts('이익의 질 — FCF vs 순이익', '억원')} data={earningsQualityData} />
              <p className="text-xs text-gray-400 mt-2 text-center">
                FCF ≥ 순이익이면 이익의 질이 높음 (오너이익 근사치)
              </p>
            </div>

            {/* 3. 영업이익률 추세 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <Line options={lineOpts('영업이익률 추이', '%')} data={marginChartData} />
            </div>

            {/* 4. 부채비율 추세 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <Bar options={barOpts('부채비율 추이', '%')} data={debtChartData} />
              <p className="text-xs text-gray-400 mt-2 text-center">
                🟢 &lt;100% · 🟡 100~200% · 🔴 &gt;200%
              </p>
            </div>

            {/* 5. DuPont ROE 분해 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <Line options={dupontOpts} data={dupontChartData} />
              <p className="text-xs text-gray-400 mt-2 text-center">
                자산회전율·레버리지는 ×10 스케일 표시 — ROE = 순이익률 × 자산회전율 × 레버리지
              </p>
            </div>

            {/* 6. 밸류에이션 히스토리 */}
            {valYears.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                <Bar options={barOpts('밸류에이션 히스토리 (PER / PBR)', '배(x)')} data={valChartData} />
              </div>
            )}

            {/* 7. 카테고리별 점수 (전체 너비) */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 col-span-1 md:col-span-2">
              <Bar options={scoreBarOpts} data={scoreChartData} />
            </div>

          </div>

          {/* ── AI 버핏 리포트 텍스트 ── */}
          <div className="bg-white rounded-xl border border-amber-100 shadow-sm p-6">
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-amber-100">
              <span className="text-lg">🧙</span>
              <h2 className="text-lg font-bold text-gray-800">
                {resolvedName} — AI 버핏 스타일 분석
              </h2>
            </div>
            <div>{renderMarkdown(data.report)}</div>
          </div>
        </>
      )}
    </div>
  );
}
