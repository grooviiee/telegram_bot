"use client";

const NAV_ITEMS = [
  { key: 'home',             label: '종합 분석' },
  { key: 'business',         label: '사업 분석' },
  { key: 'dividend',         label: '배당 분석' },
  { key: 'profitability',    label: '수익성 & 성장성' },
  { key: 'financial-health', label: '재무 건전성' },
];

export function Header({ activePage, setActivePage, favoriteCount = 0 }) {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-screen-xl mx-auto px-6 flex items-center gap-8 h-14">
        {/* 로고 */}
        <span className="font-bold text-blue-600 text-lg tracking-tight flex-shrink-0">
          Butler.works
        </span>

        {/* 탭 네비게이션 */}
        <nav className="flex items-stretch h-full gap-1 flex-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => setActivePage(item.key)}
              className={`px-4 text-sm font-medium border-b-2 transition-colors ${
                activePage === item.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-300'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {/* 즐겨찾기 버튼 */}
        <button
          onClick={() => setActivePage('favorites')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            activePage === 'favorites'
              ? 'bg-yellow-50 text-yellow-600 border border-yellow-300'
              : 'text-gray-500 hover:text-yellow-600 hover:bg-yellow-50'
          }`}
        >
          <span>{activePage === 'favorites' ? '★' : '☆'}</span>
          <span>즐겨찾기</span>
          {favoriteCount > 0 && (
            <span className="bg-yellow-400 text-white text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center">
              {favoriteCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
