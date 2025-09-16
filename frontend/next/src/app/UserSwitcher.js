"use client";

export function UserSwitcher({ setUserId }) {
  return (
    <div className="p-4 bg-gray-100 rounded-lg">
      <label htmlFor="userId" className="block text-sm font-medium text-gray-700 mb-2">User ID:</label>
      <input
        id="userId"
        type="text"
        placeholder="e.g., 'admin' or 'user'"
        onChange={(e) => setUserId(e.target.value)}
        className="w-full px-3 py-2 text-gray-900 placeholder-gray-400 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      />
    </div>
  );
}
