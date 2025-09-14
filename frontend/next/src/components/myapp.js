"use client";
import React, { useState } from 'react';
import { Search, Bell, Settings, User, Menu } from 'lucide-react';

// 레이아웃 컴포넌트
const Layout = ({ children }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false); // 사이드바 토글 상태 (모바일용)

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
            className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
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

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar Component */}
        <aside
          className={`transform top-0 left-0 w-64 bg-white shadow-lg fixed h-full overflow-auto ease-in-out transition-all duration-300 z-20 md:relative md:translate-x-0 md:shadow-none ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
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

        {/* Content Area - Children will be rendered here */}
        <main className="flex-1 p-4 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
};
// Next.js _app.js 파일의 기본 구조

export default function MyApp({ Component, pageProps }) {
  return (
    <Layout>
      <Component {...pageProps} />
    </Layout>
  );
}

// DashboardCard 컴포넌트 (Next.js 프로젝트 내 별도의 컴포넌트 파일로 생성)
// components/DashboardCard.js
export const DashboardCard = ({ title, children, className }) => (
  <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
    <h2 className="text-lg font-semibold text-gray-800 mb-4">{title}</h2>
    {children}
  </div>
);
