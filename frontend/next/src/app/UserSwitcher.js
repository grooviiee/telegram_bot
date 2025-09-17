"use client";

export function UserSwitcher({ setCompanyName }) {
  return (
    <div className="p-4 bg-gray-100 rounded-lg">
      <label htmlFor="companyName" className="block text-sm font-medium text-gray-700 mb-2">Company Name:</label>
      <input
        id="companyName"
        type="text"
        placeholder="e.g., 'butler' or 'user'"
        onChange={(e) => setCompanyName(e.target.value)}
        className="w-full px-3 py-2 text-gray-900 placeholder-gray-400 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      />
    </div>
  );
}
