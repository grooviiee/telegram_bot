import Link from 'next/link';
import { ReactNode } from 'react';

export default function DividendLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <nav className="w-full p-4 bg-gray-800 text-white flex items-center justify-start space-x-4">
        <Link href="/dividend/input" className="hover:text-gray-300">
          Input Dividends
        </Link>
        <Link href="/dividend/overview" className="hover:text-gray-300">
          Overview
        </Link>
      </nav>
      <main className="flex-grow overflow-auto">{children}</main>
    </div>
  );
}
