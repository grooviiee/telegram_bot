"use client";

import { useId } from 'react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSearch: (name?: string) => void;
  loading: boolean;
  resolvedName?: string;
  starred?: boolean;
  onToggleFavorite?: () => void;
  submitLabel?: string;
}

export function CompanySearch({ value, onChange, onSearch, loading, resolvedName,
  starred, onToggleFavorite, submitLabel = '조회' }: Props) {
  const id = useId();
  return (
    <form role="search" aria-label="기업 검색" className="mb-4 max-w-2xl"
      onSubmit={(event) => { event.preventDefault(); if (!loading && value.trim()) onSearch(); }}>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-gray-700">기업명</label>
      <div className="flex items-center gap-2">
        <input id={id} type="search" value={value} placeholder="예: 삼성전자, SK하이닉스"
          autoComplete="off" enterKeyHint="search" disabled={loading}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault();
          }}
          className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 disabled:opacity-60" />
        <button type="submit" disabled={loading || !value.trim()}
          className="shrink-0 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">
          {loading ? '조회 중…' : submitLabel}
        </button>
        {resolvedName && onToggleFavorite && (
          <button type="button" onClick={onToggleFavorite} aria-pressed={Boolean(starred)}
            aria-label={`${resolvedName} 즐겨찾기 ${starred ? '해제' : '추가'}`}
            className={`shrink-0 rounded-lg border px-3 py-2 text-xl ${starred ? 'border-yellow-300 bg-yellow-50 text-yellow-600' : 'border-gray-200 bg-white text-gray-500'}`}>
            <span aria-hidden="true">{starred ? '★' : '☆'}</span>
          </button>
        )}
      </div>
      {!resolvedName && !loading && !value && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500">
          <span>기업을 골라 시작해보세요</span>
          {['삼성전자', 'SK하이닉스', '현대자동차'].map((name) => (
            <button key={name} type="button" onClick={() => { onChange(name); onSearch(name); }}
              className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-gray-700 hover:border-blue-300 hover:text-blue-700">{name}</button>
          ))}
        </div>
      )}
    </form>
  );
}

export function SearchFeedback({ message, onRetry }: { message: string; onRetry: () => void }) {
  if (!message) return null;
  const error = message.startsWith('오류');
  return (
    <div role={error ? 'alert' : 'status'} className={`mb-5 rounded-lg border p-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-100 bg-emerald-50 text-emerald-800'}`}>
      <p>{message}</p>
      {error && <button type="button" onClick={onRetry} className="mt-2 rounded border border-red-200 bg-white px-3 py-1.5 font-medium hover:bg-red-100">다시 시도</button>}
    </div>
  );
}
