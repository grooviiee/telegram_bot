/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useRef } from 'react';
import { ProgressIndicator } from '@/components/ProgressIndicator';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const VALUATION_STEPS = [
  { label: '종목코드 조회 중',              after: 0 },
  { label: '현재 주가 및 시가총액 조회 중', after: 1_000 },
  { label: 'DART 재무 데이터 조회 중',      after: 2_500 },
  { label: '밸류에이션 지표 계산 중',       after: 6_000 },
];

interface HistoryItem {
  year: number;
  per: number | null;
  pbr: number | null;
  psr: number | null;
  ev_ebit: number | null;
  eps: number | null;
  equity: number | null;
  revenue: number | null;
}

interface ValuationData {
  company_name: string;
  stock_code: string;
  price: number;
  shares: number;
  market_cap: number;
  per: number | null;
  pbr: number | null;
  psr: number | null;
  ev: number | null;
  ev_ebit: number | null;
  latest_year: number;
  history: HistoryItem[];
}

interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

const PAGE_KEY = 'valuation';

function fmt(n: number, digits = 0) {
  return n.toLocaleString('ko-KR', { maximumFractionDigits: digits });
}

function fmtTrillion(n: number) {
  if (Math.abs(n) >= 1e12) return `${(n / 1e12).toFixed(1)}조`;
  if (Math.abs(n) >= 1e8)  return `${(n / 1e8).toFixed(0)}억`;
  return fmt(n);
}

function MetricCard({
  label, value, sub, color,
}: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex flex-col gap-1">
      <span className="text-xs text-gray-400 font-medium">{label}</span>
      <span className={`text-2xl font-bold ${color ?? 'text-gray-800'}`}>{value}</span>
      {sub && <span className="text-xs text-gray-400">{sub}</span>}
    </div>
  );
}

function ratingColor(metric: 'per' | 'pbr' | 'psr', value: number | null): string {
  if (value === null) return 'text-gray-400';
  const thresholds: Record<string, [number, number]> = {
    per:  [10, 25],
    pbr:  [1, 3],
    psr:  [0.5, 2],
  };
  const [low, high] = thresholds[metric];
  if (value <= low)  return 'text-emerald-600';
  if (value <= high) return 'text-amber-500';
  return 'text-red-500';
}

export default function ValuationPage({
  toggleFavorite, isFavorite, initialCompany, onSearched,
}: Props = {}) {
  const [companyName, setCompanyName] = useState(initialCompany ?? '');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [data, setData] = useState<ValuationData | null>(null);
  const [resolvedName, setResolvedName] = useState('');
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
      const res = await fetch(
        `${API_BASE}/valuation/${encodeURIComponent(target)}`,
        { signal: AbortSignal.timeout(120_000) },
      );
      const json = await res.json() as any;
      if (!res.ok) throw new Error(json.detail ?? '조회 실패');
      setData(json);
      setResolvedName(json.company_name);
      setMessage(`${json.company_name} 밸류에이션 조회 완료`);
      onSearched?.();
    } catch (e: any) {
      fetchedRef.current = null;
      setMessage(`오류: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [companyName, onSearched]);

  // initialCompany 자동 조회
  React.useEffect(() => {
    if (initialCompany && fetchedRef.current !== initialCompany) fetchData(initialCompany);
  }, [initialCompany, fetchData]);

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">밸류에이션</h1>
      <p className="text-sm text-gray-500 mb-6">현재 주가 기반 — PER · PBR · PSR · EV/EBIT</p>

      {/* 검색 */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="회사명 입력 (예: 삼성전자)"
          value={companyName}
          onChange={(e) => { setCompanyName(e.target.value); fetchedRef.current = null; }}
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
              starred ? 'text-yellow-400 hover:text-gray-300' : 'text-gray-300 hover:text-yellow-400'
            }`}
          >
            {starred ? '★' : '☆'}
          </button>
        )}
      </div>

      <ProgressIndicator steps={VALUATION_STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {data && (
        <>
          {/* 주가 / 시가총액 요약 */}
          <div className="flex items-center gap-3 mb-5 text-sm text-gray-500">
            <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded-full font-medium">
              {data.stock_code}
            </span>
            <span className="font-semibold text-gray-700">{fmt(data.price)}원</span>
            <span className="text-gray-300">|</span>
            <span>시가총액 {fmtTrillion(data.market_cap)}</span>
            <span className="text-gray-300">|</span>
            <span className="text-gray-400">{data.latest_year}년 재무 기준</span>
          </div>

          {/* 지표 카드 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8 max-w-3xl">
            <MetricCard
              label="PER"
              value={data.per != null ? `${data.per}x` : 'N/A'}
              sub="주가 / EPS"
              color={ratingColor('per', data.per)}
            />
            <MetricCard
              label="PBR"
              value={data.pbr != null ? `${data.pbr}x` : 'N/A'}
              sub="시가총액 / 자본총계"
              color={ratingColor('pbr', data.pbr)}
            />
            <MetricCard
              label="PSR"
              value={data.psr != null ? `${data.psr}x` : 'N/A'}
              sub="시가총액 / 매출액"
              color={ratingColor('psr', data.psr)}
            />
            <MetricCard
              label="EV/EBIT"
              value={data.ev_ebit != null ? `${data.ev_ebit}x` : 'N/A'}
              sub="기업가치 / 영업이익"
              color="text-gray-800"
            />
          </div>

          {/* 색상 범례 */}
          <div className="flex gap-4 mb-6 text-xs text-gray-500">
            <span><span className="text-emerald-600 font-bold">●</span> 저평가</span>
            <span><span className="text-amber-500 font-bold">●</span> 적정</span>
            <span><span className="text-red-500 font-bold">●</span> 고평가</span>
          </div>

          {/* 연도별 이력 테이블 */}
          {data.history.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden max-w-3xl">
              <div className="px-5 py-4 border-b border-gray-100">
                <span className="font-semibold text-gray-800 text-sm">연도별 이력 (현재 주가 기준)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-gray-500 text-xs">
                      <th className="px-5 py-3 text-left font-medium">연도</th>
                      <th className="px-5 py-3 text-right font-medium">EPS</th>
                      <th className="px-5 py-3 text-right font-medium">PER</th>
                      <th className="px-5 py-3 text-right font-medium">PBR</th>
                      <th className="px-5 py-3 text-right font-medium">PSR</th>
                      <th className="px-5 py-3 text-right font-medium">EV/EBIT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((h) => (
                      <tr key={h.year} className="border-t border-gray-50 hover:bg-gray-50 transition-colors">
                        <td className="px-5 py-3 font-medium text-gray-700">{h.year}년</td>
                        <td className="px-5 py-3 text-right text-gray-600">
                          {h.eps != null ? `${fmt(h.eps)}원` : '-'}
                        </td>
                        <td className={`px-5 py-3 text-right font-medium ${ratingColor('per', h.per)}`}>
                          {h.per != null ? `${h.per}x` : '-'}
                        </td>
                        <td className={`px-5 py-3 text-right font-medium ${ratingColor('pbr', h.pbr)}`}>
                          {h.pbr != null ? `${h.pbr}x` : '-'}
                        </td>
                        <td className={`px-5 py-3 text-right font-medium ${ratingColor('psr', h.psr)}`}>
                          {h.psr != null ? `${h.psr}x` : '-'}
                        </td>
                        <td className="px-5 py-3 text-right text-gray-600">
                          {h.ev_ebit != null ? `${h.ev_ebit}x` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="px-5 py-3 text-xs text-gray-400 border-t border-gray-50">
                * PER·PBR·PSR·EV/EBIT 모두 현재 주가({fmt(data.price)}원) 기준으로 계산
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
