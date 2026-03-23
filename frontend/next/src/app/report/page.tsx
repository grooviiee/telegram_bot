/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useRef } from 'react';
import { ProgressIndicator } from '@/components/ProgressIndicator';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const REPORT_STEPS = [
  { label: '기업 코드 조회 중',           after: 0 },
  { label: '재무·배당·사업 데이터 수집 중', after: 1_500 },
  { label: '최근 공시 목록 조회 중',       after: 4_000 },
  { label: 'AI가 리포트를 작성하는 중',    after: 6_000 },
];

interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

const PAGE_KEY = 'report';

function renderMarkdown(text: string) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={key++} className="text-xl font-bold text-gray-800 mt-6 mb-3">
          {line.slice(3)}
        </h2>
      );
    } else if (line.startsWith('### ')) {
      elements.push(
        <h3 key={key++} className="text-base font-semibold text-blue-700 mt-5 mb-2 flex items-center gap-2">
          {line.slice(4)}
        </h3>
      );
    } else if (line.startsWith('**') && line.endsWith('**')) {
      const content = line.slice(2, -2);
      const color = content.includes('긍정') ? 'text-emerald-600'
        : content.includes('부정') ? 'text-red-500'
        : 'text-amber-500';
      elements.push(
        <p key={key++} className={`font-bold text-lg mb-2 ${color}`}>{content}</p>
      );
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <li key={key++} className="text-sm text-gray-700 leading-relaxed ml-4 list-disc mb-1">
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
        <p key={key++} className="text-sm text-gray-700 leading-relaxed mb-2">
          {line}
        </p>
      );
    }
  }
  return elements;
}

export default function ReportPage({
  toggleFavorite, isFavorite, initialCompany, onSearched,
}: Props = {}) {
  const [companyName, setCompanyName] = useState(initialCompany ?? '');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [report, setReport] = useState<string | null>(null);
  const [resolvedName, setResolvedName] = useState('');
  const fetchedRef = useRef<string | null>(null);

  const fetchData = useCallback(async (name?: string) => {
    const target = (name ?? companyName).trim();
    if (!target) return;
    if (fetchedRef.current === target) return;
    fetchedRef.current = target;
    setLoading(true);
    setMessage('');
    setReport(null);
    try {
      const res = await fetch(
        `${API_BASE}/report/${encodeURIComponent(target)}`,
        { signal: AbortSignal.timeout(120_000) },
      );
      const json = await res.json() as any;
      if (!res.ok) throw new Error(json.detail ?? '조회 실패');
      setReport(json.report);
      setResolvedName(json.company_name);
      setMessage(`${json.company_name} 리포트 생성 완료${json.cached ? ' (캐시)' : ''}`);
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

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">AI 투자 리포트</h1>
      <p className="text-sm text-gray-500 mb-6">DART 공시 데이터 기반 — Gemini AI 종합 분석</p>

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
          {loading ? '생성 중...' : '리포트 생성'}
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

      <ProgressIndicator steps={REPORT_STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {report && (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 max-w-3xl">
          {renderMarkdown(report)}
        </div>
      )}
    </div>
  );
}
