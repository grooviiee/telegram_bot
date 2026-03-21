/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useEffect, useRef } from 'react';
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

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
  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [resolvedName, setResolvedName] = useState('');
  const [annualDividendItems, setAnnualDividendItems] = useState<DividendItem[] | null>(null);
  const [annualFinancials, setAnnualFinancials] = useState<FinancialYear[] | null>(null);

  const [period, setPeriod] = useState<'annual' | 'quarterly'>('annual');
  const [quarterlyDividendItems, setQuarterlyDividendItems] = useState<DividendItem[] | null>(null);
  const [quarterlyFinancials, setQuarterlyFinancials] = useState<FinancialYear[] | null>(null);
  const quarterlyFetchedRef = useRef<string | null>(null);

  const fetchData = useCallback(async (nameOverride?: string) => {
    const name = (nameOverride ?? companyName).trim();
    if (!name) { setMessage('회사명을 입력해주세요.'); return; }
    setLoading(true);
    setMessage('');
    setAnnualDividendItems(null);
    setAnnualFinancials(null);
    setQuarterlyDividendItems(null);
    setQuarterlyFinancials(null);
    quarterlyFetchedRef.current = null;
    setPeriod('annual');
    setResolvedName('');
    try {
      const encoded = encodeURIComponent(name);
      const [divRes, finRes] = await Promise.all([
        fetch(`${API_BASE}/dividend-data/${encoded}`, { signal: AbortSignal.timeout(300_000) }),
        fetch(`${API_BASE}/financials/${encoded}`,    { signal: AbortSignal.timeout(300_000) }),
      ]);
      const [divJson, finJson] = await Promise.all([divRes.json(), finRes.json()]) as [any, any];
      if (!divRes.ok) throw new Error(divJson.detail || '배당 데이터 조회 실패');
      if (!finRes.ok) throw new Error(finJson.detail || '재무 데이터 조회 실패');
      const resolved = (finJson.company_name ?? divJson.company_name) as string;
      setResolvedName(resolved);
      setAnnualDividendItems(divJson.dividend_data);
      setAnnualFinancials(finJson.financials);
      setMessage(`'${resolved}' 데이터 조회 완료`);
    } catch (e: unknown) {
      setMessage(`오류: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
      onSearched?.();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyName]);

  useEffect(() => {
    if (initialCompany) {
      setCompanyName(initialCompany);
      fetchData(initialCompany);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCompany]);

  const fetchQuarterly = useCallback(async (name: string) => {
    if (quarterlyFetchedRef.current === name) return;
    quarterlyFetchedRef.current = name;
    setLoading(true);
    try {
      const encoded = encodeURIComponent(name);
      const [divQRes, finQRes] = await Promise.all([
        fetch(`${API_BASE}/dividend-data-quarterly/${encoded}`, { signal: AbortSignal.timeout(300_000) }),
        fetch(`${API_BASE}/financials-quarterly/${encoded}`,    { signal: AbortSignal.timeout(300_000) }),
      ]);
      const [divQJson, finQJson] = await Promise.all([divQRes.json(), finQRes.json()]) as [any, any];
      setQuarterlyDividendItems(divQJson.dividend_data ?? []);
      setQuarterlyFinancials(finQJson.financials ?? []);
    } catch {
      quarterlyFetchedRef.current = null;
    } finally {
      setLoading(false);
    }
  }, []);

  const handlePeriodChange = (newPeriod: 'annual' | 'quarterly') => {
    setPeriod(newPeriod);
    if (newPeriod === 'quarterly' && resolvedName) {
      fetchQuarterly(resolvedName);
    }
  };

  // display 변수
  const dividendItems = period === 'annual' ? annualDividendItems : quarterlyDividendItems;
  const financials    = period === 'annual' ? annualFinancials    : quarterlyFinancials;

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
  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  const showCharts = dividendItems || financials;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">종합 분석</h1>
      <p className="text-sm text-gray-500 mb-6">DART 공시 기반 5개년 배당·수익성·재무건전성 통합 분석</p>

      {/* 검색 */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="회사명 입력 (예: 삼성전자)"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetchData()}
          disabled={loading}
          className="flex-1 max-w-xs px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={() => fetchData()}
          disabled={loading}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? '조회 중...' : '조회'}
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

      <ProgressIndicator steps={STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
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
