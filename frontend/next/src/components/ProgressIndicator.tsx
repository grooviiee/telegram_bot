"use client";

import { useEffect, useState } from 'react';

interface Step {
  label: string;
  /** loading 시작 후 이 단계로 전환될 때까지의 ms */
  after: number;
}

interface Props {
  steps: Step[];
  active: boolean;
}

export function ProgressIndicator({ steps, active }: Props) {
  const [stepIdx, setStepIdx] = useState(0);
  const [dots, setDots] = useState('');

  useEffect(() => {
    if (!active) {
      setStepIdx(0);
      setDots('');
      return;
    }

    // 점 애니메이션 (500ms 간격)
    const dotsTimer = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
    }, 500);

    // 단계 전환 타이머
    const stepTimers = steps.map((step, i) =>
      setTimeout(() => setStepIdx(i), step.after)
    );

    return () => {
      clearInterval(dotsTimer);
      stepTimers.forEach(clearTimeout);
    };
  }, [active, steps]);

  if (!active) return null;

  const current = steps[stepIdx];
  const progress = Math.round(((stepIdx + 1) / steps.length) * 100);

  return (
    <div className="my-4 p-4 bg-blue-50 border border-blue-100 rounded-xl max-w-lg">
      {/* 스피너 + 현재 단계 메시지 */}
      <div className="flex items-center gap-3 mb-3">
        <div className="w-5 h-5 border-[3px] border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-sm font-medium text-blue-700">
          {current.label}{dots}
        </span>
      </div>

      {/* 프로그레스 바 */}
      <div className="h-1.5 bg-blue-100 rounded-full overflow-hidden mb-2">
        <div
          className="h-full bg-blue-500 rounded-full transition-all duration-700 ease-in-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* 단계 점 표시 */}
      <div className="flex items-center gap-1.5">
        {steps.map((step, i) => (
          <div
            key={i}
            title={step.label}
            className={`h-1.5 flex-1 rounded-full transition-all duration-500 ${
              i <= stepIdx ? 'bg-blue-500' : 'bg-blue-100'
            }`}
          />
        ))}
        <span className="text-xs text-blue-400 ml-1 flex-shrink-0">
          {stepIdx + 1}/{steps.length}
        </span>
      </div>
    </div>
  );
}
