/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useRef } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { ProgressIndicator } from '@/components/ProgressIndicator';
import { PeriodToggle } from '@/components/PeriodToggle';
import { useDartData } from '@/lib/useDartData';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const PAGE_KEY = 'dividend';

const DIVIDEND_STEPS = [
  { label: '회사명으로 DART 기업 정보를 검색하는 중', after: 0 },
  { label: 'DART 배당 데이터를 조회하는 중',          after: 1_500 },
  { label: '5개년 배당금을 집계하는 중',               after: 4_000 },
];

interface DividendItem {
  year: number;
  dividend: number;
  quarter?: string;
  label?: string;
}

interface DividendPageProps {
  favorites?: { company: string; page: string }[];
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function DividendChartPage(rawProps: any) {
  const props = rawProps as DividendPageProps;
  const {
    favorites: _favorites,
    toggleFavorite,
    isFavorite,
    initialCompany,
    onSearched,
  } = props;
  const { companyName, setCompanyName, loading, message, resolvedName, fetchData, data: rawData } =
    useDartData<DividendItem[]>(
      {
        buildPath: (n) => `/dividend-data/${n}`,
        extractData: (j) => (j as any).dividend_data,
      },
      initialCompany,
      onSearched,
    );

  const [period, setPeriod] = useState<'annual' | 'quarterly'>('annual');
  const [quarterlyData, setQuarterlyData] = useState<DividendItem[] | null>(null);
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
        `${API_BASE}/dividend-data-quarterly/${encodeURIComponent(name)}`,
        { signal: AbortSignal.timeout(300_000) }
      );
      const json = await res.json() as any;
      if (!res.ok) throw new Error(json.detail || '분기 데이터 조회 실패');
      setQuarterlyData(json.dividend_data);
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

  const dividendItems = period === 'annual' ? rawData : quarterlyData;
  const isLoading = loading || (period === 'quarterly' && quarterlyLoading);

  const chartData = React.useMemo(() => {
    if (!dividendItems || dividendItems.length === 0) return null;
    const labels = dividendItems.map((d) => d.label ?? String(d.year));
    const amounts = dividendItems.map((d) => d.dividend);
    return {
      labels,
      datasets: [
        {
          label: '주당 현금배당금 (원)',
          data: amounts,
          backgroundColor: 'rgba(59, 130, 246, 0.65)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 1,
        },
      ],
    };
  }, [dividendItems]);

  const options = {
    responsive: true,
    plugins: {
      legend: { position: 'top' as const },
      title: {
        display: true,
        text: resolvedName ? `${resolvedName} — 배당금 추이` : '배당금 추이',
        font: { size: 14 },
      },
      tooltip: {
        callbacks: {
          label: (ctx: any) =>
            `${ctx.dataset.label}: ${ctx.parsed.y?.toLocaleString()}원`,
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: { display: true, text: '배당금 (원)' },
        ticks: { callback: (v: string | number) => Number(v).toLocaleString() },
      },
      x: { title: { display: true, text: '사업연도' } },
    },
  };

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">배당 분석</h1>
      <p className="text-sm text-gray-500 mb-6">DART 공시 기반 5개년 분기별 배당금 추이</p>

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

      <ProgressIndicator steps={DIVIDEND_STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {period === 'quarterly' && quarterlyLoading && (
        <p className="mb-4 text-sm text-blue-500">분기 데이터를 조회하는 중...</p>
      )}

      {chartData && chartData.datasets[0].data.some((v: number) => v > 0) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 max-w-3xl">
          <Bar options={options} data={chartData} />
        </div>
      )}
    </div>
  );
}
