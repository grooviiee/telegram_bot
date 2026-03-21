'use client';

const NAV_ITEMS = [
  { key: 'home',             label: '종합 분석',        group: null },
  { key: 'dividend',         label: '배당 분석',        group: '재무 분석' },
  { key: 'profitability',    label: '수익성 & 성장성',  group: '재무 분석' },
  { key: 'financial-health', label: '재무 건전성',      group: '재무 분석' },
];

export function Sidebar({ setActivePage, activePage }) {
  const groups = [...new Set(NAV_ITEMS.map((i) => i.group))];

  return (
    <div className="sidebar" style={{ minWidth: 180 }}>
      <h2 className="text-lg font-semibold mb-4">메뉴</h2>
      <nav className="mt-2 flex flex-col gap-1">
        {groups.map((group) => (
          <div key={group ?? '__root'}>
            {group && (
              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wide mt-4 mb-1 px-2">
                {group}
              </p>
            )}
            {NAV_ITEMS.filter((i) => i.group === group).map((item) => (
              <button
                key={item.key}
                onClick={() => setActivePage(item.key)}
                className={`w-full text-left px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  activePage === item.key
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-700 hover:bg-gray-200'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </div>
  );
}
