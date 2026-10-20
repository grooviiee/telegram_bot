"use client";

import { useState, useEffect, useCallback } from 'react';
import { CompanyContext } from '@/lib/CompanyContext';
import { normalizePage, ANALYSIS_PAGES } from '@/lib/navigation';
import { Header } from '@/components/header/Header';
import CreatePage from './create/page';
import DividendPage from '@/components/screens/DividendPage';
import AnalysisPage from '@/components/screens/AnalysisPage';
import BusinessPage from '@/components/screens/BusinessPage';
import ProfitabilityPage from '@/components/screens/ProfitabilityPage';
import FinancialHealthPage from '@/components/screens/FinancialHealthPage';
import FavoritesPage from '@/components/screens/FavoritesPage';
import ValuationPage from '@/components/screens/ValuationPage';
import ReportPage from '@/components/screens/ReportPage';
import BuffettPage from '@/components/screens/BuffettPage';
import ChatPage from '@/components/screens/ChatPage';
import EventsPage from '@/components/screens/EventsPage';

const STORAGE_KEY = 'dart_favorites';

export function InteractiveLayout({ initialPage = 'home' }) {
  const [activePage, setActivePage] = useState(initialPage);
  const [favorites, setFavorites] = useState([]);
  const [company, rememberCompany] = useState('');
  // { company: string, page: string } | null
  const [pendingSearch, setPendingSearch] = useState(null);

  // localStorage에서 즐겨찾기 로드
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          const valid = parsed.filter((item) => item && typeof item.company === 'string' && item.company.trim()
            && ANALYSIS_PAGES.some((page) => page.key === normalizePage(item.page)))
            .map((item) => ({ company: item.company, page: normalizePage(item.page) }));
          setFavorites(valid.filter((item, index) => valid.findIndex((other) => other.company === item.company && other.page === item.page) === index));
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const toggleFavorite = useCallback((company, page) => {
    page = normalizePage(page);
    setFavorites((prev) => {
      const exists = prev.some((f) => f.company === company && f.page === page);
      const next = exists
        ? prev.filter((f) => !(f.company === company && f.page === page))
        : [...prev, { company, page }];
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const navigate = useCallback((page) => {
    const target = normalizePage(page);
    if (target === activePage) return;
    setPendingSearch(company ? { company, page: target } : null);
    setActivePage(target);
  }, [activePage, company]);

  // 즐겨찾기 항목 클릭 → 해당 페이지로 이동 후 자동 조회
  const handleFavoriteClick = useCallback((company, page) => {
    page = normalizePage(page);
    rememberCompany(company);
    setPendingSearch({ company, page });
    setActivePage(page);
  }, []);

  const isFavorite = useCallback(
    (company, page) => favorites.some((f) => f.company === company && f.page === normalizePage(page)),
    [favorites]
  );

  const renderPage = () => {
    const initialCompany =
      pendingSearch?.page === activePage ? pendingSearch.company : undefined;

    const sharedProps = { favorites, toggleFavorite, isFavorite, initialCompany };

    switch (activePage) {
      case 'home':             return <AnalysisPage {...sharedProps} />;
      case 'business':         return <BusinessPage {...sharedProps} />;
      case 'create':           return <CreatePage />;
      case 'dividend':         return <DividendPage {...sharedProps} />;
      case 'profitability':    return <ProfitabilityPage {...sharedProps} />;
      case 'financial-health': return <FinancialHealthPage {...sharedProps} />;
      case 'valuation':        return <ValuationPage {...sharedProps} />;
      case 'buffett':          return <BuffettPage {...sharedProps} />;
      case 'report':           return <ReportPage {...sharedProps} />;
      case 'events':           return <EventsPage {...sharedProps} />;
      case 'chat':             return <ChatPage initialCompany={pendingSearch?.page === 'chat' ? pendingSearch.company : undefined} />;
      case 'favorites':        return <FavoritesPage favorites={favorites} toggleFavorite={toggleFavorite} onFavoriteClick={handleFavoriteClick} />;
      default:                 return <AnalysisPage {...sharedProps} />;
    }
  };

  return (
    <CompanyContext.Provider value={{ company, rememberCompany }}>
      <div className="flex h-dvh flex-col">
      <a href="#analysis-content" className="skip-link">분석 본문으로 이동</a>
      <Header activePage={activePage} setActivePage={navigate} favoriteCount={favorites.length} />
      <div className="shrink-0 border-b border-gray-200 bg-white px-4 py-3 text-sm text-gray-600">
        <div className="mx-auto max-w-screen-xl">
          {company ? <><span className="font-semibold text-gray-900">{company}</span><span className="ml-2">다른 분석 메뉴에서도 이어서 확인할 수 있어요.</span></>
            : '기업을 검색하고 재무 · 사업 · AI 분석을 이어서 살펴보세요.'}
        </div>
      </div>
      <main id="analysis-content" tabIndex={-1} className="mx-auto min-h-0 w-full max-w-screen-xl flex-1 overflow-y-auto">
        {renderPage()}
      </main>
      </div>
    </CompanyContext.Provider>
  );
}
