/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useRef } from 'react';
import { Bar, Line } from 'react-chartjs-2';
import { ProgressIndicator } from '@/components/ProgressIndicator';
import { PeriodToggle } from '@/components/PeriodToggle';
import { useDartData } from '@/lib/useDartData';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface FinancialYear {
  year: number;
  fs_div: string;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  eps: number | null;
  operating_margin: number | null;
  roe: number | null;
  quarter?: string;
  label?: string;
}

// 원 → 억원 변환 (소수점 1자리)
const toEok = (v: number | null | undefined): number | null =>
  v != null ? Math.round(v / 1e8 * 10) / 10 : null;

const nullableArr = (data: FinancialYear[], fn: (d: FinancialYear) => number | null) =>
  data.map(fn);

const PAGE_KEY = 'profitability';

const FINANCIAL_STEPS = [
  { label: '회사명으로 DART 기업 정보를 검색하는 중', after: 0 },
  { label: 'DART 재무제표 API에 요청 중',        after: 1_500 },
  { label: '5개년 데이터를 연도별로 집계하는 중', after: 4_000 },
  { label: '수익성 지표를 계산하는 중',           after: 7_000 },
];

interface ProfitabilityPageProps {
  favorites?: { company: string; page: string }[];
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function ProfitabilityPage(rawProps: any) {
  const props = rawProps as ProfitabilityPageProps;
  const {
    toggleFavorite,
    isFavorite,
    initialCompany,
    onSearched,
  } = props;
  const { companyName, setCompanyName, loading, message, resolvedName, fetchData, data } =
    useDartData<FinancialYear[]>(
      {
        buildPath: (n) => `/financials/${n}`,
        extractData: (j) => (j as any).financials,
      },
      initialCompany,
      onSearched,
    );

  const [period, setPeriod] = useState<'annual' | 'quarterly'>('annual');
  const [quarterlyData, setQuarterlyData] = useState<FinancialYear[] | null>(null);
  const [quarterlyLoading, setQuarterlyLoading] = useState(false);
  const quarterlyFetchedRef = useRef<string | null>(null);

  // 새 회사 검색 시 분기 상태 초기화
  React.useEffect(() => {
    setQuarterlyData(null);
    quarterlyFetchedRef.current = null;
    setPeriod('annual');
  }, [resolvedName]);

  const fetchQuarterly = useCallback(async (name: string) => {
    if (quarterlyFetchedRef.current === name) return;
    quarterlyFetchedRef.current = name;
    setQuarterlyLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/financials-quarterly/${encodeURIComponent(name)}`,
        { signal: AbortSignal.timeout(300_000) }
      );
      const json = await res.json() as any;
      if (!res.ok) throw new Error(json.detail || '분기 데이터 조회 실패');
      setQuarterlyData(json.financials);
    } catch {
      quarterlyFetchedRef.current = null;
    } finally {
      setQuarterlyLoading(false);
    }
  }, []);

  const handlePeriodChange = (newPeriod: 'annual' | 'quarterly') => {
    setPeriod(newPeriod);
    if (newPeriod === 'quarterly' && resolvedName) {
      fetchQuarterly(resolvedName);
    }
  };

  const displayData = period === 'annual' ? data : quarterlyData;
  const isLoading = loading || (period === 'quarterly' && quarterlyLoading);

  const years = displayData?.map((d) => d.label ?? String(d.year)) ?? [];

  // ① EPS 추이
  const epsData = {
    labels: years,
    datasets: [
      {
        label: 'EPS (원/주)',
        data: displayData ? nullableArr(displayData, (d) => d.eps) : [],
        borderColor: 'rgba(139, 92, 246, 1)',
        backgroundColor: 'rgba(139, 92, 246, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 5,
      },
    ],
  };

  // ② 매출액 & 영업이익 (묶음 막대)
  const revenueData = {
    labels: years,
    datasets: [
      {
        label: '매출액 (억원)',
        data: displayData ? nullableArr(displayData, (d) => toEok(d.revenue)) : [],
        backgroundColor: 'rgba(59, 130, 246, 0.65)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1,
      },
      {
        label: '영업이익 (억원)',
        data: displayData ? nullableArr(displayData, (d) => toEok(d.operating_income)) : [],
        backgroundColor: 'rgba(16, 185, 129, 0.65)',
        borderColor: 'rgba(16, 185, 129, 1)',
        borderWidth: 1,
      },
    ],
  };

  // ③ 영업이익률
  const marginData = {
    labels: years,
    datasets: [
      {
        label: '영업이익률 (%)',
        data: displayData ? nullableArr(displayData, (d) => d.operating_margin) : [],
        borderColor: 'rgba(245, 158, 11, 1)',
        backgroundColor: 'rgba(245, 158, 11, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 5,
      },
    ],
  };

  // ④ ROE
  const roeData = {
    labels: years,
    datasets: [
      {
        label: 'ROE (%)',
        data: displayData ? nullableArr(displayData, (d) => d.roe) : [],
        borderColor: 'rgba(239, 68, 68, 1)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 5,
      },
    ],
  };

  const lineOpts = (title: string, yLabel: string) => ({
    responsive: true,
    spanGaps: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: title, font: { size: 14 } },
      tooltip: {
        callbacks: {
          label: (ctx: any) => `${ctx.dataset.label}: ${ctx.parsed.y?.toLocaleString()}`,
        },
      },
    },
    scales: {
      y: {
        title: { display: true, text: yLabel },
        ticks: { callback: (v: number | string) => Number(v).toLocaleString() },
      },
    },
  });

  const barOpts = (title: string, yLabel: string) => ({
    responsive: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: title, font: { size: 14 } },
      tooltip: {
        callbacks: {
          label: (ctx: any) => `${ctx.dataset.label}: ${ctx.parsed.y?.toLocaleString()}`,
        },
      },
    },
    scales: {
      y: {
        title: { display: true, text: yLabel },
        ticks: { callback: (v: number | string) => Number(v).toLocaleString() },
      },
    },
  });

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">수익성 &amp; 성장성</h1>
      <p className="text-sm text-gray-500 mb-6">DART 공시 기반 5개년 추이 분석</p>

      {/* 검색 */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="회사명 입력 (예: 삼성전자)"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetchData()}
          disabled={isLoading}
          className="flex-1 max-w-xs px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={() => fetchData()}
          disabled={isLoading}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {isLoading ? '조회 중...' : '조회'}
        </button>
        {resolvedName && toggleFavorite && (
          <button
            onClick={() => toggleFavorite(resolvedName, PAGE_KEY)}
            title={starred ? '즐겨찾기 해제' : '즐겨찾기 추가'}
            className={`px-3 py-2 rounded-lg text-xl leading-none transition-colors ${
              starred
                ? 'text-yellow-400 hover:text-gray-300'
                : 'text-gray-300 hover:text-yellow-400'
            }`}
          >
            {starred ? '★' : '☆'}
          </button>
        )}
      </div>

      <div className="mb-4">
        <PeriodToggle value={period} onChange={handlePeriodChange} disabled={!resolvedName} />
      </div>

      <ProgressIndicator steps={FINANCIAL_STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {period === 'quarterly' && quarterlyLoading && (
        <p className="mb-4 text-sm text-blue-500">분기 데이터를 조회하는 중...</p>
      )}

      {/* 차트 2×2 그리드 */}
      {displayData && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <Line options={lineOpts('EPS 추이 (주당순이익)', '원/주')} data={epsData} />
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <Bar options={barOpts('매출액 & 영업이익 추이', '억원')} data={revenueData} />
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <Line options={lineOpts('영업이익률 추이', '%')} data={marginData} />
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <Line options={lineOpts('ROE 추이 (자기자본이익률)', '%')} data={roeData} />
          </div>
        </div>
      )}
    </div>
  );
}
