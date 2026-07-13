/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState } from 'react';
import { ProgressIndicator } from '@/components/ProgressIndicator';
import { useDartData } from '@/lib/useDartData';

interface Source {
  title: string;
  url: string;
}

interface PriceEvent {
  start_date: string;
  end_date: string;
  pct_change: number;
  headline: string;
  summary: string;
  category: string;
  sources: Source[];
}

interface EventsData {
  events: PriceEvent[];
}

const PAGE_KEY = 'events';

const EVENT_STEPS = [
  { label: '회사명으로 종목코드를 조회하는 중',           after: 0 },
  { label: '최근 1년 주가 데이터를 분석하는 중',          after: 1_500 },
  { label: '급등락 변곡점 구간을 탐지하는 중',            after: 4_000 },
  { label: 'AI가 원인 사건을 웹에서 검색하는 중 (최대 2분 정도 걸릴 수 있어요)', after: 8_000 },
];

interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

function EventCard({ event }: { event: PriceEvent }) {
  const [open, setOpen] = useState(false);
  const isUp = event.pct_change > 0;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start gap-4 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex-shrink-0 text-xs text-gray-400 pt-0.5 w-28">
          {event.start_date} ~<br />{event.end_date}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-sm font-bold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
              {isUp ? '+' : ''}{event.pct_change}%
            </span>
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
              {event.category}
            </span>
          </div>
          <p className="font-semibold text-gray-800 text-sm">{event.headline}</p>
        </div>
        <span className="text-gray-400 text-lg leading-none flex-shrink-0">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-gray-100 pt-4">
          <p className="text-sm text-gray-700 leading-relaxed mb-3">{event.summary}</p>
          {event.sources.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {event.sources.map((s, i) => (
                <a
                  key={i}
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded-full transition-colors"
                >
                  출처: {s.title || `링크 ${i + 1}`}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function EventsPage({
  toggleFavorite,
  isFavorite,
  initialCompany,
  onSearched,
}: Props = {}) {
  const { companyName, setCompanyName, loading, message, resolvedName, fetchData, data } =
    useDartData<EventsData>(
      {
        buildPath: (n) => `/events/${n}`,
        extractData: (j: any) => ({ events: j.events ?? [] }),
      },
      initialCompany,
      onSearched,
    );

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">주가를 움직인 사건들</h1>
      <p className="text-sm text-gray-500 mb-6">
        최근 1년간 5거래일 기준 급등락 구간을 찾아, AI가 원인이 된 뉴스·이벤트를 검색합니다.
      </p>

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
          {loading ? '분석 중...' : '조회'}
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

      <ProgressIndicator steps={EVENT_STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {data && (
        data.events.length > 0 ? (
          <div className="flex flex-col gap-3 max-w-3xl">
            {data.events.map((event, i) => (
              <EventCard key={i} event={event} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">최근 1년간 유의미한 급등락 구간을 찾지 못했습니다.</p>
        )
      )}
    </div>
  );
}
