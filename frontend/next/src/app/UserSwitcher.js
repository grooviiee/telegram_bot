"use client";

export function UserSwitcher({ setUserId }) {
  return (
    <div className="p-4">
      <label htmlFor="userId" className="mr-2 font-medium">User ID:</label>
      <input
        id="userId"
        type="text"
        placeholder="e.g., 'admin' or 'user'"
        onChange={(e) => setUserId(e.target.value)}
        className="border rounded px-2 py-1"
      />
    </div>
  );
}
