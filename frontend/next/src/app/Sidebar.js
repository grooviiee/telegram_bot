'use client';

import { useState } from 'react';
import { UserSwitcher } from './UserSwitcher';

export function Sidebar({ setUserId, setActivePage }) {
  return (
    <div className="sidebar">
      <h2 className="text-lg font-semibold mb-4">User Management</h2>
      <UserSwitcher setUserId={setUserId} />
      <nav className="mt-8">
        <h3 className="text-md font-semibold mb-2">Navigation</h3>
        <button onClick={() => setActivePage('home')} className="w-full text-left px-4 py-2 text-sm font-medium text-gray-700 rounded-md hover:bg-gray-200">Home</button>
        <button onClick={() => setActivePage('create')} className="w-full text-left px-4 py-2 text-sm font-medium text-gray-700 rounded-md hover:bg-gray-200">Create</button>
        <button onClick={() => setActivePage('dividend')} className="w-full text-left px-4 py-2 text-sm font-medium text-gray-700 rounded-md hover:bg-gray-200">Dividend</button>
      </nav>
    </div>
  );
}

