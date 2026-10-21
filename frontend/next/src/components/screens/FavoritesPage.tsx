"use client";

import { PAGE_LABELS } from "@/lib/navigation";

interface Favorite {
  company: string;
  page: string;
}



interface Props {
  favorites: Favorite[];
  toggleFavorite: (company: string, page: string) => void;
  onFavoriteClick: (company: string, page: string) => void;
}

export default function FavoritesPage({ favorites, toggleFavorite, onFavoriteClick }: Props) {
  if (favorites.length === 0) {
    return (
      <div className="p-6 bg-gray-50 min-h-screen">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">즐겨찾기</h1>
        <p className="text-sm text-gray-500 mb-8">자주 조회하는 기업을 저장해두세요.</p>
        <div className="flex flex-col items-center justify-center py-24 text-gray-400">
          <span className="text-5xl mb-4">☆</span>
          <p className="text-base font-medium">아직 즐겨찾기가 없습니다.</p>
          <p className="text-sm mt-1">기업을 조회한 뒤 검색창 옆 ☆ 버튼을 눌러 저장하세요.</p>
          <button onClick={() => onFavoriteClick('', 'home')} className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">기업 분석 시작하기</button>
        </div>
      </div>
    );
  }

  // 기업명 기준으로 그룹화
  const grouped = favorites.reduce<Record<string, Favorite[]>>((acc, fav) => {
    if (!acc[fav.company]) acc[fav.company] = [];
    acc[fav.company].push(fav);
    return acc;
  }, Object.create(null) as Record<string, Favorite[]>);

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">즐겨찾기</h1>
      <p className="text-sm text-gray-500 mb-6">
        저장된 기업 {Object.keys(grouped).length}개 · 항목 {favorites.length}개
      </p>

      <div className="flex flex-col gap-4 max-w-xl">
        {Object.entries(grouped).map(([company, items]) => (
          <div key={company} className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
              <span className="font-semibold text-gray-800">{company}</span>
            </div>
            <ul className="divide-y divide-gray-50">
              {items.map((fav) => (
                <li key={fav.page} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors">
                  <button
                    onClick={() => onFavoriteClick(fav.company, fav.page)}
                    className="text-sm text-blue-600 font-medium hover:underline text-left"
                  >
                    {PAGE_LABELS[fav.page] ?? fav.page}
                  </button>
                  <button
                    onClick={() => toggleFavorite(fav.company, fav.page)}
                    aria-label={`${fav.company} ${PAGE_LABELS[fav.page] ?? fav.page} 즐겨찾기 삭제`}
                    className="text-yellow-400 hover:text-gray-300 transition-colors text-lg leading-none"
                  >
                    ★
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
