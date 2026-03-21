"use client";

import { useState } from 'react';
import { Menu, Search, Bell, Settings, User } from 'lucide-react';

export default function Header() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <header className="bg-white shadow-sm p-4 flex items-center justify-between z-10">
      <div className="flex items-center">
        <button
          className="md:hidden p-2 rounded-lg text-gray-700 hover:bg-gray-100 mr-3"
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          aria-label="Toggle menu"
        >
          <Menu size={24} />
        </button>
        <div className="text-xl font-bold text-blue-600">Butler</div>
        <nav className="hidden md:flex ml-8 space-x-6">
          <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">기업</a>
          <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">업종, 코드</a>
          <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">초성</a>
          <a href="#" className="text-gray-700 hover:text-blue-600 font-medium">검색</a>
        </nav>
      </div>
      <div className="relative flex-grow mx-4 max-w-md">
        <input
          type="text"
          placeholder="기업, 코드, 초성을 입력해 주세요."
          className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
      </div>
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
  );
}
