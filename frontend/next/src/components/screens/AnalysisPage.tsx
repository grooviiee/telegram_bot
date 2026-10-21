/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";
import { CompanySearch, SearchFeedback } from '@/components/CompanySearch';
import { useRememberCompany } from '@/lib/CompanyContext';

import React, { useState } from 'react';
import { useDartData } from '@/lib/useDartData';
import { Bar, Line } from 'react-chartjs-2';
import { ProgressIndicator } from '@/components/ProgressIndicator';
import { PeriodToggle } from '@/components/PeriodToggle';
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


interface DividendItem {
  year: number;
  dividend: number;
  quarter?: string;
  label?: string;
}

interface FinancialYear {
  year: number;
  fs_div: string;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  eps: number | null;
  operating_margin: number | null;
  roe: number | null;
  liabilities: number | null;
  equity: number | null;
  current_assets: number | null;
  current_liabilities: number | null;
  op_cash_flow: number | null;
  capex: number | null;
  fcf: number | null;
  net_debt: number | null;
  debt_ratio: number | null;
  current_ratio: number | null;
  net_debt_ratio: number | null;
  quarter?: string;
  label?: string;
}

const toEok = (v: number | null | undefined): number | null =>
  v != null ? Math.round((v / 1e8) * 10) / 10 : null;

const PAGE_KEY = 'analysis';

const STEPS = [
  { label: '회사명으로 DART 기업 정보를 검색하는 중', after: 0 },
  { label: 'DART 재무제표 & 배당 API에 요청 중',      after: 1_500 },
  { label: '5개년 데이터를 연도별로 집계하는 중',     after: 4_000 },
  { label: '모든 지표를 계산하는 중',                  after: 7_000 },
];

interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

export default function AnalysisPage({
  toggleFavorite,
  isFavorite,
  initialCompany,
  onSearched,
}: Props = {}) {
  const annualFin = useDartData<FinancialYear[]>({
    buildPath: (name) => `/financials/${name}`,
    extractData: (json) => (json as { financials: FinancialYear[] }).financials,
  }, initialCompany, onSearched);
  const annualDiv = useDartData<DividendItem[]>({
    buildPath: (name) => `/dividend-data/${name}`,
    extractData: (json) => (json as { dividend_data: DividendItem[] }).dividend_data,
  }, initialCompany);
  const { companyName, setCompanyName } = annualFin;
  const resolvedName = annualFin.resolvedName || annualDiv.resolvedName;
  const [period, setPeriod] = useState<'annual' | 'quarterly'>('annual');
  const quarterFin = useDartData<FinancialYear[]>({
    buildPath: (name) => `/financials-quarterly/${name}`,
    extractData: (json) => (json as { financials: FinancialYear[] }).financials,
    autoFetch: false,
  }, resolvedName);
  const quarterDiv = useDartData<DividendItem[]>({
    buildPath: (name) => `/dividend-data-quarterly/${name}`,
    extractData: (json) => (json as { dividend_data: DividendItem[] }).dividend_data,
    autoFetch: false,
  }, resolvedName);
  const loading = annualFin.loading || annualDiv.loading || (period === 'quarterly' && (quarterFin.loading || quarterDiv.loading));
  const messages = period === 'annual' ? [annualFin.message, annualDiv.message] : [quarterFin.message, quarterDiv.message];
  const message = messages.find((text) => text.startsWith('오류')) || messages.find(Boolean) || '';

  const fetchData = async (name?: string) => {
    const target = name ?? companyName;
    setPeriod('annual');
    await Promise.all([annualFin.fetchData(target), annualDiv.fetchData(target)]);
  };
  const fetchQuarterly = async (name: string) => {
    await Promise.all([quarterFin.fetchData(name), quarterDiv.fetchData(name)]);
  };
  const handlePeriodChange = (next: 'annual' | 'quarterly') => {
    setPeriod(next);
    if (next === 'quarterly' && resolvedName && (!quarterFin.data || !quarterDiv.data)) void fetchQuarterly(resolvedName);
  };
  const dividendItems = period === 'annual' ? annualDiv.data : quarterDiv.data;
  const financials = period === 'annual' ? annualFin.data : quarterFin.data;

  // ── chart helpers ──────────────────────────────────────────────────────────

  const lineOpts = (title: string, yLabel: string) => ({
    responsive: true,
    spanGaps: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: title, font: { size: 13 } },
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
    spanGaps: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: title, font: { size: 13 } },
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

  // ── dividend chart ─────────────────────────────────────────────────────────

  const divChartData = dividendItems?.length
    ? {
        labels: dividendItems.map((d) => d.label ?? String(d.year)),
        datasets: [{
          label: '주당 현금배당금 (원)',
          data: dividendItems.map((d) => d.dividend),
          backgroundColor: 'rgba(59, 130, 246, 0.65)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 1,
        }],
      }
    : null;

  // ── financial charts ───────────────────────────────────────────────────────

  const finYears = financials?.map((d) => d.label ?? String(d.year)) ?? [];

  const epsData = {
    labels: finYears,
    datasets: [{
      label: 'EPS (원/주)',
      data: financials?.map((d) => d.eps) ?? [],
      borderColor: 'rgba(139, 92, 246, 1)',
      backgroundColor: 'rgba(139, 92, 246, 0.1)',
      fill: true, tension: 0.3, pointRadius: 5,
    }],
  };

  const revenueData = {
    labels: finYears,
    datasets: [
      {
        label: '매출액 (억원)',
        data: financials?.map((d) => toEok(d.revenue)) ?? [],
        backgroundColor: 'rgba(59, 130, 246, 0.65)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1,
      },
      {
        label: '영업이익 (억원)',
        data: financials?.map((d) => toEok(d.operating_income)) ?? [],
        backgroundColor: 'rgba(16, 185, 129, 0.65)',
        borderColor: 'rgba(16, 185, 129, 1)',
        borderWidth: 1,
      },
    ],
  };

  const marginData = {
    labels: finYears,
    datasets: [{
      label: '영업이익률 (%)',
      data: financials?.map((d) => d.operating_margin) ?? [],
      borderColor: 'rgba(245, 158, 11, 1)',
      backgroundColor: 'rgba(245, 158, 11, 0.1)',
      fill: true, tension: 0.3, pointRadius: 5,
    }],
  };

  const roeData = {
    labels: finYears,
    datasets: [{
      label: 'ROE (%)',
      data: financials?.map((d) => d.roe) ?? [],
      borderColor: 'rgba(239, 68, 68, 1)',
      backgroundColor: 'rgba(239, 68, 68, 0.1)',
      fill: true, tension: 0.3, pointRadius: 5,
    }],
  };

  const debtRatioData = {
    labels: finYears,
    datasets: [{
      label: '부채비율 (%)',
      data: financials?.map((d) => d.debt_ratio) ?? [],
      backgroundColor: financials?.map((d) =>
        d.debt_ratio != null && d.debt_ratio > 200
          ? 'rgba(239, 68, 68, 0.7)'
          : d.debt_ratio != null && d.debt_ratio > 100
          ? 'rgba(245, 158, 11, 0.7)'
          : 'rgba(16, 185, 129, 0.7)'
      ) ?? [],
      borderWidth: 1,
    }],
  };

  const currentRatioData = {
    labels: finYears,
    datasets: [{
      label: '유동비율 (%)',
      data: financials?.map((d) => d.current_ratio) ?? [],
      borderColor: 'rgba(59, 130, 246, 1)',
      backgroundColor: 'rgba(59, 130, 246, 0.1)',
      fill: true, tension: 0.3, pointRadius: 5,
    }],
  };

  const fcfData = {
    labels: finYears,
    datasets: [
      {
        label: '영업현금흐름 (억원)',
        data: financials?.map((d) => toEok(d.op_cash_flow)) ?? [],
        backgroundColor: 'rgba(99, 102, 241, 0.65)',
        borderColor: 'rgba(99, 102, 241, 1)',
        borderWidth: 1,
      },
      {
        label: 'FCF (억원)',
        data: financials?.map((d) => toEok(d.fcf)) ?? [],
        backgroundColor: 'rgba(16, 185, 129, 0.65)',
        borderColor: 'rgba(16, 185, 129, 1)',
        borderWidth: 1,
      },
    ],
  };

  const netDebtData = {
    labels: finYears,
    datasets: [{
      label: '순부채비율 (%)',
      data: financials?.map((d) => d.net_debt_ratio) ?? [],
      backgroundColor: financials?.map((d) =>
        d.net_debt_ratio != null && d.net_debt_ratio < 0
          ? 'rgba(16, 185, 129, 0.7)'
          : 'rgba(239, 68, 68, 0.65)'
      ) ?? [],
      borderWidth: 1,
    }],
  };

  // ── summary cards ──────────────────────────────────────────────────────────

  const latest = financials?.[financials.length - 1];
  useRememberCompany(resolvedName);
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  const showCharts = dividendItems || financials;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">종합 분석</h1>
      <p className="text-sm text-gray-500 mb-6">DART 공시 기반 5개년 배당·수익성·재무건전성 통합 분석</p>

      {/* 검색 */}
      <CompanySearch value={companyName} onChange={setCompanyName}
        onSearch={fetchData} loading={loading} resolvedName={resolvedName}
        starred={Boolean(starred)}
        onToggleFavorite={toggleFavorite ? () => toggleFavorite(resolvedName, PAGE_KEY) : undefined} />

      <div className="mb-4">
        <PeriodToggle value={period} onChange={handlePeriodChange} disabled={!resolvedName || loading} />
      </div>

      <ProgressIndicator steps={STEPS} active={loading} />

      <SearchFeedback message={message} onRetry={() => period === 'quarterly' ? void fetchQuarterly(resolvedName) : void fetchData()} />

      {financials && financials.length > 0 && (
        <p className="mb-4 text-sm text-gray-600">
          <strong>{resolvedName}</strong> · {financials[0].label ?? financials[0].year} ~ {financials[financials.length - 1].label ?? financials[financials.length - 1].year}
          {' · '}{Array.from(new Set(financials.map((row) => row.fs_div === 'CFS' ? '연결' : row.fs_div === 'OFS' ? '개별' : '구분 미제공'))).join(' / ')} 재무제표
        </p>
      )}

      {/* 최신연도 요약 카드 */}
      {latest && period === 'annual' && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[
            {
              label: '부채비율',
              value: latest.debt_ratio != null ? `${latest.debt_ratio.toLocaleString()}%` : '-',
              sub: latest.debt_ratio != null
                ? latest.debt_ratio > 200 ? '위험' : latest.debt_ratio > 100 ? '주의' : '안전'
                : '',
              color: latest.debt_ratio != null
                ? latest.debt_ratio > 200 ? 'text-red-500' : latest.debt_ratio > 100 ? 'text-yellow-500' : 'text-green-600'
                : 'text-gray-400',
            },
            {
              label: '유동비율',
              value: latest.current_ratio != null ? `${latest.current_ratio.toLocaleString()}%` : '-',
              sub: latest.current_ratio != null
                ? latest.current_ratio >= 200 ? '우수' : latest.current_ratio >= 100 ? '보통' : '부족'
                : '',
              color: latest.current_ratio != null
                ? latest.current_ratio >= 200 ? 'text-green-600' : latest.current_ratio >= 100 ? 'text-yellow-500' : 'text-red-500'
                : 'text-gray-400',
            },
            {
              label: 'FCF',
              value: latest.fcf != null ? `${toEok(latest.fcf)?.toLocaleString()}억원` : '-',
              sub: latest.fcf != null ? (latest.fcf >= 0 ? '양(+)' : '음(-)') : '',
              color: latest.fcf != null ? (latest.fcf >= 0 ? 'text-green-600' : 'text-red-500') : 'text-gray-400',
            },
            {
              label: '영업이익률',
              value: latest.operating_margin != null ? `${latest.operating_margin.toLocaleString()}%` : '-',
              sub: latest.operating_margin != null
                ? latest.operating_margin >= 15 ? '우수' : latest.operating_margin >= 5 ? '보통' : '저조'
                : '',
              color: latest.operating_margin != null
                ? latest.operating_margin >= 15 ? 'text-green-600' : latest.operating_margin >= 5 ? 'text-yellow-500' : 'text-red-500'
                : 'text-gray-400',
            },
          ].map(({ label, value, sub, color }) => (
            <div key={label} className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <p className="text-xs text-gray-400 mb-1">{label} ({latest.year})</p>
              <p className={`text-xl font-bold ${color}`}>{value}</p>
              <p className={`text-xs mt-1 ${color}`}>{sub}</p>
            </div>
          ))}
        </div>
      )}

      {showCharts && (
        <>
          {/* 섹션: 배당 */}
          {divChartData && divChartData.datasets[0].data.some((v) => (v as number) > 0) && (
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-gray-700 mb-3">배당 분석</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                  <Bar
                    options={barOpts(
                      resolvedName ? `${resolvedName} — 배당금 추이` : '배당금 추이',
                      '배당금 (원)'
                    )}
                    data={divChartData}
                  />
                </div>
              </div>
            </section>
          )}

          {/* 섹션: 수익성 & 성장성 */}
          {financials && (
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-gray-700 mb-3">수익성 &amp; 성장성</h2>
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
            </section>
          )}

          {/* 섹션: 재무 건전성 */}
          {financials && (
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-gray-700 mb-3">재무 건전성</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                  <Bar options={barOpts('부채비율 추이 (부채/자본 × 100)', '%')} data={debtRatioData} />
                </div>
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                  <Line options={lineOpts('유동비율 추이 (유동자산/유동부채 × 100)', '%')} data={currentRatioData} />
                </div>
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                  <Bar options={barOpts('영업현금흐름 & FCF 추이', '억원')} data={fcfData} />
                </div>
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                  <Bar options={barOpts('순부채비율 추이 (순부채/자본 × 100)', '%')} data={netDebtData} />
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
