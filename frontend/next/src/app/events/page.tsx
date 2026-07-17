/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useMemo, useRef } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { ProgressIndicator } from '@/components/ProgressIndicator';
import { useDartData } from '@/lib/useDartData';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler,
);

interface Source {
  title: string;
  url: string;
}

interface PriceEvent {
  date: string;
  anchor_date: string | null;
  pct_change: number | null;
  headline: string;
  summary: string;
  category: string;
  importance: 'high' | 'medium' | string;
  sources: Source[];
}

interface PricePoint {
  date: string;
  close: number;
}

interface EventsData {
  events: PriceEvent[];
  prices: PricePoint[];
}

const PAGE_KEY = 'events';

const EVENT_STEPS = [
  { label: '회사명으로 종목코드를 조회하는 중',                    after: 0 },
  { label: '최근 뉴스 기사를 모으는 중',                          after: 1_000 },
  { label: 'AI가 밸류에이션·내러티브 관점에서 사건을 선별하는 중',   after: 3_000 },
  { label: '거의 다 됐어요, 조금만 더 기다려주세요',                after: 10_000 },
];

const HIGH_COLOR = '#d97706';   // amber-600
const MEDIUM_COLOR = '#3b82f6'; // blue-500

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

function EventCard({
  event,
  open,
  onToggle,
}: {
  event: PriceEvent;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={`bg-white rounded-xl shadow-sm border overflow-hidden transition-colors ${
        open ? 'border-blue-300 ring-1 ring-blue-200' : 'border-gray-100'
      }`}
    >
      <button
        onClick={onToggle}
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
        extractData: (j: any) => ({ events: j.events ?? [], prices: j.prices ?? [] }),
      },
      initialCompany,
      onSearched,
    );

  // 차트 마커 ↔ 카드 선택 상태 (양방향 연동)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 새 회사 검색 시 선택 초기화
  React.useEffect(() => {
    setSelectedIdx(null);
  }, [resolvedName]);

  // 가격 시계열 + 이벤트 마커를 하나의 라인 차트 데이터로 구성한다.
  const chart = useMemo(() => {
    if (!data || data.prices.length === 0) return null;

    const labels = data.prices.map((p) => p.date);
    const closes = data.prices.map((p) => p.close);
    const dateIndex = new Map(labels.map((d, i) => [d, i]));

    // 각 거래일 인덱스에 매칭되는 이벤트(있으면). 같은 날 충돌 시 먼저 온(중요도 높은) 이벤트 유지.
    const markerEvent: (PriceEvent | null)[] = labels.map(() => null);
    const markerEventIdx: (number | null)[] = labels.map(() => null);
    data.events.forEach((ev, evIdx) => {
      const anchor = ev.anchor_date ?? ev.date;
      const i = dateIndex.get(anchor);
      if (i != null && markerEvent[i] == null) {
        markerEvent[i] = ev;
        markerEventIdx[i] = evIdx;
      }
    });

    const markerData = labels.map((_, i) => (markerEvent[i] ? closes[i] : null));
    const markerRadius = labels.map((_, i) => {
      if (markerEventIdx[i] == null) return 0;
      return markerEventIdx[i] === selectedIdx ? 9 : 5;
    });
    const markerColor = labels.map((_, i) => {
      const ev = markerEvent[i];
      if (!ev) return 'transparent';
      return ev.importance === 'high' ? HIGH_COLOR : MEDIUM_COLOR;
    });

    const chartData = {
      labels,
      datasets: [
        {
          label: '종가 (원)',
          data: closes,
          borderColor: 'rgba(107, 114, 128, 0.9)',
          backgroundColor: 'rgba(107, 114, 128, 0.08)',
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 0,
          tension: 0.1,
          fill: true,
          order: 2,
        },
        {
          label: '사건',
          data: markerData,
          showLine: false,
          pointRadius: markerRadius,
          pointHoverRadius: markerRadius.map((r) => (r > 0 ? r + 2 : 0)),
          pointBackgroundColor: markerColor,
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          order: 1,
        },
      ],
    };

    return { chartData, markerEvent, markerEventIdx };
  }, [data, selectedIdx]);

  const selectEvent = (evIdx: number | null) => {
    setSelectedIdx(evIdx);
    if (evIdx != null && listRef.current) {
      listRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'nearest' as const, intersect: true },
    onClick: (_evt: any, elements: any[]) => {
      const hit = elements.find((el) => el.datasetIndex === 1);
      if (hit && chart) {
        const evIdx = chart.markerEventIdx[hit.index];
        selectEvent(evIdx ?? null);
      }
    },
    plugins: {
      legend: { display: false },
      title: {
        display: true,
        text: resolvedName ? `${resolvedName} — 최근 1년 주가와 사건` : '주가와 사건',
        font: { size: 14 },
      },
      tooltip: {
        callbacks: {
          title: (items: any[]) => {
            const it = items[0];
            if (it?.datasetIndex === 1 && chart) {
              const ev = chart.markerEvent[it.dataIndex];
              return ev ? `${ev.date} · ${ev.headline}` : it.label;
            }
            return it?.label ?? '';
          },
          label: (ctx: any) => {
            if (ctx.datasetIndex === 1 && chart) {
              const ev = chart.markerEvent[ctx.dataIndex];
              if (!ev) return '';
              const pct = ev.pct_change == null ? '주가 영향 미미' : `${ev.pct_change > 0 ? '+' : ''}${ev.pct_change}%`;
              return `${ev.category} · ${pct}`;
            }
            return `종가: ${Number(ctx.parsed.y).toLocaleString()}원`;
          },
        },
      },
    },
    scales: {
      y: {
        title: { display: true, text: '종가 (원)' },
        ticks: { callback: (v: string | number) => Number(v).toLocaleString() },
      },
      x: {
        ticks: { maxTicksLimit: 8, autoSkip: true, maxRotation: 0 },
      },
    },
  }), [chart, resolvedName]);

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">주가를 움직인 사건들</h1>
      <p className="text-sm text-gray-500 mb-6">
        최근 1년간 밸류에이션·투자 내러티브에 유의미한 사건을 AI가 검색해 주가 그래프 위에 표시합니다.
        마커나 아래 카드를 클릭하면 서로 연동됩니다.
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

      {chart && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 max-w-3xl mb-5">
          <div className="h-72">
            <Line options={options} data={chart.chartData} />
          </div>
        </div>
      )}

      {data && (
        data.events.length > 0 ? (
          <div ref={listRef} className="flex flex-col gap-3 max-w-3xl">
            {data.events.map((event, i) => (
              <EventCard
                key={i}
                event={event}
                open={selectedIdx === i}
                onToggle={() => selectEvent(selectedIdx === i ? null : i)}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">최근 1년간 유의미한 사건을 찾지 못했습니다.</p>
        )
      )}
    </div>
  );
}
