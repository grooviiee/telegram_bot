/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";
import { CompanySearch, SearchFeedback } from '@/components/CompanySearch';
import { useRememberCompany } from '@/lib/CompanyContext';

import React, { useState } from 'react';
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

export default function DividendChartPage(rawProps: any) {
  const props = rawProps as DividendPageProps;
  const {
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
  const quarterly = useDartData<DividendItem[]>({
    buildPath: (name) => `/dividend-data-quarterly/${name}`,
    extractData: (json) => (json as { dividend_data: DividendItem[] }).dividend_data,
    autoFetch: false,
  }, resolvedName);
  const { data: quarterlyData, loading: quarterlyLoading } = quarterly;

  React.useEffect(() => { setPeriod('annual'); }, [resolvedName]);

  const handlePeriodChange = (newPeriod: 'annual' | 'quarterly') => {
    setPeriod(newPeriod);
    if (newPeriod === 'quarterly' && resolvedName) {
      if (!quarterlyData) void quarterly.fetchData(resolvedName);
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

  useRememberCompany(resolvedName);
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">배당 분석</h1>
      <p className="text-sm text-gray-500 mb-6">DART 공시 기반 최근 5년 연도별 · 분기별 배당금 추이</p>

      <CompanySearch value={companyName} onChange={setCompanyName}
        onSearch={fetchData} loading={isLoading} resolvedName={resolvedName}
        starred={Boolean(starred)}
        onToggleFavorite={toggleFavorite ? () => toggleFavorite(resolvedName, PAGE_KEY) : undefined} />

      <div className="mb-4">
        <PeriodToggle value={period} onChange={handlePeriodChange} disabled={!resolvedName || isLoading} />
      </div>

      <ProgressIndicator steps={DIVIDEND_STEPS} active={isLoading} />

      <SearchFeedback message={period === 'quarterly' ? quarterly.message : message}
        onRetry={() => { if (period === 'quarterly') void quarterly.fetchData(resolvedName); else void fetchData(); }} />



      {!isLoading && dividendItems && (dividendItems.length === 0 || dividendItems.every((item) => !item.dividend)) && (
        <p className="mb-4 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-600">선택한 기간에 표시할 현금배당 내역이 없습니다.</p>
      )}

      {chartData && chartData.datasets[0].data.some((v: number) => v > 0) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 max-w-3xl">
          <Bar options={options} data={chartData} />
        </div>
      )}
    </div>
  );
}
