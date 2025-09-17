"use client";

import { UserSwitcher } from "@/app/UserSwitcher";

export function Header({ setCompanyName }) {
  return (
    <header className="bg-gray-800 text-white p-4 flex justify-between items-center">
      <div className="text-lg font-bold">My App</div>
      <div className="w-1/4">
        <UserSwitcher setCompanyName={setCompanyName} />
      </div>
    </header>
  );
}
