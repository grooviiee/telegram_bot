"use client";
import React from 'react';

export const DashboardCard = ({ title, children, className }) => (
  <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
    <h2 className="text-lg font-semibold text-gray-800 mb-4">{title}</h2>
    {children}
  </div>
);
