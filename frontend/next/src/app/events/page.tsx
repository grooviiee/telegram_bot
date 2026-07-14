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
  date: string;
  pct_change: number | null;
  headline: string;
  summary: string;
  category: string;
  importance: 'high' | 'medium' | string;
  sources: Source[];
}

interface EventsData {
  events: PriceEvent[];
}

const PAGE_KEY = 'events';

const EVENT_STEPS = [
  { label: '회사명으로 종목코드를 조회하는 중',                    after: 0 },
  { label: '최근 뉴스 기사를 모으는 중',                          after: 1_000 },
  { label: 'AI가 밸류에이션·내러티브 관점에서 사건을 선별하는 중',   after: 3_000 },
  { label: '거의 다 됐어요, 조금만 더 기다려주세요',                after: 10_000 },
];

interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

function PctBadge({ pct }: { pct: number | null }) {
  if (pct == null) {
    return (
      <span className="text-xs font-medium text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
        주가 영향 미미
      </span>
    );
  }
  const isUp = pct > 0;
  return (
    <span className={`text-sm font-bold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
      {isUp ? '+' : ''}{pct}%
    </span>
  );
}

function EventCard({ event }: { event: PriceEvent }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start gap-4 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex-shrink-0 text-xs text-gray-400 pt-0.5 w-24">
          {event.date}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            {event.importance === 'high' && (
              <span className="text-xs font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
                ★ 중요도 높음
              </span>
            )}
            <PctBadge pct={event.pct_change} />
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
        최근 1년간 밸류에이션·투자 내러티브에 유의미한 사건을 AI가 검색합니다.
        주가가 실제로 크게 움직이지 않았어도 포함될 수 있어요.
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
          <p className="text-sm text-gray-400">최근 1년간 유의미한 사건을 찾지 못했습니다.</p>
        )
      )}
    </div>
  );
}
