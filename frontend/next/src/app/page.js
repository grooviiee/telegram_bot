"use client"

import React, { useState } from 'react';
import { Search, Bell, Settings, User, Menu, ChevronRight } from 'lucide-react'; // 아이콘 임포트 (ChevronRight 추가)

// DashboardCard 컴포넌트
const DashboardCard = ({ title, children, className }) => (
  <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
    <h2 className="text-lg font-semibold text-gray-800 mb-4">{title}</h2>
    {children}
  </div>
);

// 메인 App 컴포넌트
const App = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false); // 왼쪽 사이드바 토글 상태 (모바일용)

  return (
    <div className="min-h-screen flex flex-col bg-gray-100 font-sans">
      {/* Header Component */}
      <header className="bg-white shadow-sm p-4 flex items-center justify-between z-10">
        <div className="flex items-center">
          {/* Mobile menu toggle */}
          <button
            className="md:hidden p-2 rounded-lg text-gray-700 hover:bg-gray-100 mr-3"
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            aria-label="Toggle menu"
          >
            <Menu size={24} />
          </button>
          {/* Logo */}
          <div className="text-xl font-bold text-blue-600">Butler</div>
          {/* Navigation Links - Hidden on mobile */}
          <nav className="hidden md:flex ml-8 space-x-6">
            <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">기업</a>
            <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">업종, 코드</a>
            <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">초성</a>
            <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">검색</a>
          </nav>
        </div>

        {/* Search Bar (responsive) */}
        <div className="relative flex-grow mx-4 max-w-md">
          <input
            type="text"
            placeholder="기업, 코드, 초성을 입력해 주세요."
            className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
        </div>

        {/* User Actions */}
        <div className="flex items-center space-x-4">
          <button className="p-2 rounded-lg text-gray-700 hover:bg-gray-100" aria-label="Notifications">
            <Bell size={20} />
          </button>
          <button className="p-2 rounded-lg text-gray-700 hover:bg-gray-100" aria-label="Settings">
            <Settings size={20} />
          </button>
          <div className="flex items-center space-x-2 border-l pl-4">
            <User size={24} className="text-gray-600" />
            <span className="font-medium text-gray-800 hidden sm:block">그룹비 ▼</span>
          </div>
        </div>
      </header>

      {/* Placeholder Area */}
      <div className="bg-white p-4 shadow-sm mb-4">
        <h3 className="text-lg font-semibold text-gray-800">상단 플레이스홀더</h3>
        <p className="text-gray-600 text-sm mt-1">이곳은 헤더 아래의 플레이스홀더 영역입니다.</p>
        {/* 메뉴바 추가 (예시) */}
        <div className="flex space-x-4 mt-2 text-gray-600">
            <span className="font-medium">피드</span>
            <span>공시</span>
            <span>IR</span>
            <span>뉴스</span>
            <span>+</span>
        </div>
      </div>

      {/* Main content area (flex container for left menu, content, right menu) */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Menu (Sidebar) Component */}
        <aside
          className={`transform top-0 left-0 w-64 bg-white shadow-lg fixed h-full overflow-auto ease-in-out transition-all duration-300 z-20 md:relative md:translate-x-0 md:shadow-none ${
            isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <nav className="p-4">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">내 투자</h2>
            <ul>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                  <span className="mr-2">🏠</span>피드
                </a>
              </li>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                  <span className="mr-2">🌎</span>공시
                </a>
              </li>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                  <span className="mr-2">💡</span>IR
                </a>
              </li>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                  <span className="mr-2">📰</span>뉴스
                </a>
              </li>
            </ul>

            <h3 className="text-md font-semibold text-gray-700 mt-6 mb-3">스크리너</h3>
            <ul>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600">
                  국내
                </a>
              </li>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600">
                  미국
                </a>
              </li>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600">
                  버틀러 인기 기업
                </a>
              </li>
              <li className="mb-2">
                <a href="#" className="flex items-center p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600">
                  23Q1 서프라이즈
                </a>
              </li>
            </ul>
          </nav>
        </aside>

        {/* Overlay for mobile sidebar */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 bg-black opacity-50 z-10 md:hidden"
            onClick={() => setIsSidebarOpen(false)}
          ></div>
        )}

        {/* Main Content Area (Central part) */}
        <main className="flex-1 p-4 overflow-auto">
          {/* 메인 대시보드 그리드: 기본적으로 1개의 열, 중간 화면 이상에서는 3개의 열로 구성됩니다. */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* 첫 번째 패널: 오늘의 인기 검색기업 */}
            <DashboardCard title="오늘의 인기 검색기업">
              <table className="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">순위</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">기업명</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">현재가</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">변동률</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">시가총액 (십억)</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">관심종목</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">보유종목</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200 text-sm">
                  {[
                    { rank: 1, name: '리노공업', current: '48,250원', change: '▲2.33%', cap: '3,677.2', interest: 9, owned: 1 },
                    { rank: 2, name: '삼성전자', current: '59,700원', change: '▲1.01%', cap: '353,402.4', interest: 1, owned: 1 },
                    { rank: 3, name: '현대차', current: '197,600원', change: '▲4.22%', cap: '40,460.1', interest: 4, owned: 4 },
                    { rank: 4, name: 'SK하이닉스', current: '229,250원', change: '▲2.12%', cap: '166,894.5', interest: 2, owned: 2 },
                    { rank: 5, name: 'NAVER', current: '197,900원', change: '▲3.50%', cap: '31,354.7', interest: 3, owned: 3 },
                    { rank: 6, name: '티엔엘', current: '63,800원', change: '▲1.59%', cap: '518.6', interest: 29, owned: 29 },
                    { rank: 7, name: '두산에너빌리티', current: '47,500원', change: '▲3.49%', cap: '30,426.7', interest: 26, owned: 26 },
                    { rank: 8, 'name': '삼일회계', 'current': '51,600원', 'change': '▲0.58%', 'cap': '3,156.5', 'interest': 24, 'owned': 24 },
                    { rank: 9, 'name': '피크스시스템스', 'current': '264,000원', 'change': '▼1.68%', 'cap': '1,845.4', 'interest': 39, 'owned': 39 },
                    { rank: 10, 'name': '기아', 'current': '95,200원', 'change': '▲2.26%', 'cap': '37,858.4', 'interest': 10, 'owned': 10 },
                  ].map((row, index) => (
                    <tr key={index}>
                      <td className="px-6 py-4 whitespace-nowrap">{row.rank}</td>
                      <td className="px-6 py-4 whitespace-nowrap font-medium text-blue-600">{row.name}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.current}</td>
                      <td className={`px-6 py-4 whitespace-nowrap ${row.change.includes('▲') ? 'text-red-500' : 'text-blue-500'}`}>{row.change}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.cap}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.interest}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.owned}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DashboardCard>

            {/* 두 번째 패널: 원하는 기업 찾기 */}
            <DashboardCard title="원하는 기업 찾기">
              <div className="flex flex-col space-y-4">
                <div className="flex space-x-2">
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 shadow">시총 +</button>
                  <button className="px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 shadow">시가총액 +</button>
                  <button className="px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 shadow">시가총액 +</button>
                </div>
                <div className="text-sm text-gray-600">검색한 기업 2,633개</div>
                <ul className="space-y-2 text-sm">
                  {[
                    { rank: 1, name: '삼성전자', value: '59,700원' },
                    { rank: 2, name: 'SK하이닉스', value: '229,250원' },
                    { rank: 3, name: '삼성바이오로직스', value: '1,032,000원' },
                    { rank: 4, name: 'LG에너지솔루션', value: '286,500원' },
                    { rank: 5, name: 'KB금융', value: '110,100원' },
                    { rank: 6, name: '현대엔지니어링', value: '882,000원' },
                    { rank: 7, name: '현대차', value: '197,600원' },
                    { rank: 8, name: '기아', value: '95,200원' },
                    { rank: 9, name: 'HD현대중공업', value: '418,000원' },
                    { rank: 10, name: '셀트리온', value: '160,650원' },
                    { rank: 11, name: 'NAVER', value: '197,900원' },
                    { rank: 12, name: '두산에너빌리티', value: '47,500원' },
                    { rank: 13, name: '신한지주', value: '60,400원' },
                    { rank: 14, name: '삼성물산', value: '166,200원' },
                    { rank: 15, name: '현대모비스', value: '280,500원' },
                  ].map((company, index) => (
                    <li key={index} className="flex justify-between items-center">
                      <span>{company.rank}. {company.name}</span>
                      <span className="text-gray-700">{company.value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </DashboardCard>

            {/* 세 번째 패널: 1분기 서프라이즈 기업 */}
            <DashboardCard title="1분기 서프라이즈 기업">
              <table className="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">순위</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">기업명</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">현재가</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">변동률</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">시가총액 (십억)</th>
                    <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">카테고리</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200 text-sm">
                  {[
                    { rank: 1, name: 'DL', current: '17,350원', change: '▲4.58%', cap: '386.1', category: '건설자재' },
                    { rank: 2, name: '제일기획', current: '21,000원', change: '▲2.10%', cap: '2,400.0', category: '미디어' },
                    { rank: 3, name: 'LX하우시스', current: '51,600원', change: '▲1.20%', cap: '650.0', category: '건설자재' },
                    { rank: 4, name: '삼성엔지니어링', current: '25,000원', change: '▲3.00%', cap: '1,500.0', category: '건설' },
                    { rank: 5, name: '현대건설기계', current: '60,000원', change: '▲1.50%', cap: '800.0', category: '산업재' },
                  ].map((row, index) => (
                    <tr key={index}>
                      <td className="px-6 py-4 whitespace-nowrap">{row.rank}</td>
                      <td className="px-6 py-4 whitespace-nowrap font-medium text-blue-600">{row.name}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.current}</td>
                      <td className={`px-6 py-4 whitespace-nowrap ${row.change.includes('▲') ? 'text-red-500' : 'text-blue-500'}`}>{row.change}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.cap}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{row.category}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DashboardCard>
          </div>
        </main>

        {/* Right Menu */}
        <aside className="hidden lg:block w-64 bg-white shadow-lg p-4 h-full overflow-auto ml-4">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">내 그룹</h2>
          <ul>
            <li className="mb-2">
              <a href="#" className="flex items-center justify-between p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                그룹명
                <ChevronRight size={16} />
              </a>
            </li>
            <li className="mb-2">
              <a href="#" className="flex items-center justify-between p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                그룹명 2
                <ChevronRight size={16} />
              </a>
            </li>
            <li className="mb-2">
              <a href="#" className="flex items-center justify-between p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 font-medium">
                그룹명 3
                <ChevronRight size={16} />
              </a>
            </li>
          </ul>

          <h3 className="text-md font-semibold text-gray-700 mt-6 mb-3">즐겨찾기</h3>
          <ul>
            <li className="mb-2">
              <a href="#" className="flex items-center justify-between p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600">
                즐겨찾기 1
                <ChevronRight size={16} />
              </a>
            </li>
            <li className="mb-2">
              <a href="#" className="flex items-center justify-between p-2 rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600">
                즐겨찾기 2
                <ChevronRight size={16} />
              </a>
            </li>
          </ul>
        </aside>
      </div>
    </div>
  );
};

export default App;
