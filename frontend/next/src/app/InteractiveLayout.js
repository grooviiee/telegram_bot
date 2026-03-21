"use client";

import { useState, useEffect, useCallback } from 'react';
import { Header } from '@/components/header/Header';
import CreatePage from './create/page';
import DividendPage from './dividend/page';
import AnalysisPage from './analysis/page';
import BusinessPage from './business/page';
import ProfitabilityPage from './profitability/page';
import FinancialHealthPage from './financial-health/page';
import FavoritesPage from './favorites/page';

const STORAGE_KEY = 'dart_favorites';

export function InteractiveLayout() {
  const [activePage, setActivePage] = useState('home');
  const [favorites, setFavorites] = useState([]);
  // { company: string, page: string } | null
  const [pendingSearch, setPendingSearch] = useState(null);

  // localStorage에서 즐겨찾기 로드
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setFavorites(JSON.parse(stored));
    } catch {
      // ignore
    }
  }, []);

  const toggleFavorite = useCallback((company, page) => {
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

  // 즐겨찾기 항목 클릭 → 해당 페이지로 이동 후 자동 조회
  const handleFavoriteClick = useCallback((company, page) => {
    setPendingSearch({ company, page });
    setActivePage(page);
  }, []);

  const isFavorite = useCallback(
    (company, page) => favorites.some((f) => f.company === company && f.page === page),
    [favorites]
  );

  const renderPage = () => {
    const initialCompany =
      pendingSearch?.page === activePage ? pendingSearch.company : undefined;
    const onSearched = () => setPendingSearch(null);

    const sharedProps = { favorites, toggleFavorite, isFavorite, initialCompany, onSearched };

    switch (activePage) {
      case 'home':             return <AnalysisPage {...sharedProps} />;
      case 'business':         return <BusinessPage {...sharedProps} />;
      case 'create':           return <CreatePage />;
      case 'dividend':         return <DividendPage {...sharedProps} />;
      case 'profitability':    return <ProfitabilityPage {...sharedProps} />;
      case 'financial-health': return <FinancialHealthPage {...sharedProps} />;
      case 'favorites':        return <FavoritesPage favorites={favorites} toggleFavorite={toggleFavorite} onFavoriteClick={handleFavoriteClick} />;
      default:                 return <HomePage />;
    }
  };

  return (
    <>
      <Header activePage={activePage} setActivePage={setActivePage} favoriteCount={favorites.length} />
      <main className="max-w-screen-xl mx-auto">
        {renderPage()}
      </main>
    </>
  );
}
