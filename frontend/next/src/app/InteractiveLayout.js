"use client";

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Sidebar } from './Sidebar';
import CreatePage from './create/page';
import DividendPage from './dividend/page';
import FinancialPage from './financial/page';
import HomePage from './page';
import Link from 'next/link';
import { Header } from '@/components/header/Header';

export function InteractiveLayout({ menu_items, error }) {
  const [companyName, setCompanyName] = useState('');
  const [activePage, setActivePage] = useState('home');
  const params = useParams();
  const router = useRouter();
  const id = params.id;
  const isAdmin = companyName === 'butler';

  const handleDelete = async () => {
    if (window.confirm('Are you sure you want to delete this topic?')) {
      const resp = await fetch(`http://localhost:9999/topics/${id}`, {
        method: 'DELETE',
      });
      if (resp.ok) {
        router.push('/');
        router.refresh();
      } else {
        alert('Failed to delete the topic.');
      }
    }
  };

  const renderPage = () => {
    switch (activePage) {
      case 'home':
        return <HomePage />;
      case 'create':
        return <CreatePage />;
      case 'dividend':
        return <DividendPage />;
      case 'financial':
        return <FinancialPage />;
      default:
        return <HomePage />;
    }
  };

  return (
    <>
      <Header setCompanyName={setCompanyName} />
      <div className="flex">
        <Sidebar setActivePage={setActivePage} />
        <div className="main-content flex-grow p-4">
          <nav className="p-4">
            <div className="flex items-center space-x-2 bg-gray-100 p-2 rounded-full">
              <Link href="/" className="px-4 py-2 text-sm font-medium text-gray-700 rounded-full hover:bg-white hover:text-black">Home</Link>
              {error ? (
                <p className="text-red-500">Error: Could not load menu_items. Please start the server.</p>
              ) : (
                menu_items.map(topic => (
                  <Link href={`/${topic.id}`} key={topic.id} className="px-4 py-2 text-sm font-medium text-gray-700 rounded-full hover:bg-white hover:text-black">
                    {topic.title}
                  </Link>
                ))
              )}
            </div>
          </nav>
          {isAdmin && id && (
            <button onClick={handleDelete} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-full hover:bg-red-700">
              Delete
            </button>
          )}
          {renderPage()}
        </div>
      </div>
    </>
  );
}
