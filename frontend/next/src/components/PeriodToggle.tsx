"use client";

interface PeriodToggleProps {
  value: 'annual' | 'quarterly';
  onChange: (period: 'annual' | 'quarterly') => void;
  disabled?: boolean;
}

export function PeriodToggle({ value, onChange, disabled = false }: PeriodToggleProps) {
  return (
    <div className={`inline-flex rounded-lg border border-gray-200 overflow-hidden text-sm font-medium ${disabled ? 'opacity-50 pointer-events-none' : ''}`}>
      {(['annual', 'quarterly'] as const).map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          disabled={disabled}
          className={`px-4 py-1.5 transition-colors ${
            value === p
              ? 'bg-blue-600 text-white'
              : 'bg-white text-gray-600 hover:bg-gray-50'
          }`}
        >
          {p === 'annual' ? '연도별' : '분기별'}
        </button>
      ))}
    </div>
  );
}
