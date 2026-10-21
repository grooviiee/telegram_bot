"use client";

import { ANALYSIS_PAGES } from '@/lib/navigation';

export function Header({ activePage, setActivePage, favoriteCount = 0 }) {
  return (
    <header className="sticky top-0 z-10 shrink-0 border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-screen-xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <button onClick={() => setActivePage('home')} aria-label="Butler.works 종합 분석으로 이동"
          className="text-lg font-bold tracking-tight text-blue-600">Butler.works</button>
        <button onClick={() => setActivePage('favorites')} aria-current={activePage === 'favorites' ? 'page' : undefined}
          className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium ${activePage === 'favorites' ? 'bg-yellow-50 text-yellow-700' : 'text-gray-600 hover:bg-yellow-50'}`}>
          <span aria-hidden="true">☆ </span>즐겨찾기{favoriteCount > 0 ? ` ${favoriteCount}` : ''}
        </button>
      </div>
      <nav aria-label="분석 메뉴" className="mx-auto flex max-w-screen-xl gap-1 overflow-x-auto px-4 sm:px-6">
        {ANALYSIS_PAGES.map((item) => (
          <button key={item.key} onClick={() => setActivePage(item.key)}
            aria-current={activePage === item.key ? 'page' : undefined}
            className={`shrink-0 whitespace-nowrap border-b-2 px-3 py-3 text-sm font-medium transition-colors ${activePage === item.key ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900'}`}>
            {item.label}
          </button>
        ))}
      </nav>
    </header>
  );
}
