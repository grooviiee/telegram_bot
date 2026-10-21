"use client";

import { useEffect, useState } from 'react';

interface Props {
  // 서버가 진행률을 제공하기 전에는 단계 완료를 추정하지 않습니다.
  steps: { label: string; after: number }[];
  active: boolean;
}

export function ProgressIndicator({ active }: Props) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) { setSeconds(0); return; }
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [active]);
  if (!active) return null;
  return (
    <div className="my-4 max-w-2xl rounded-xl border border-blue-100 bg-blue-50 p-4">
      <div role="status" className="flex items-center gap-3 text-sm font-medium text-blue-800">
        <span aria-hidden="true" className="h-5 w-5 shrink-0 animate-spin rounded-full border-[3px] border-blue-500 border-t-transparent motion-reduce:animate-none" />
        데이터를 불러오고 있습니다
      </div>
      <p aria-hidden="true" className="mt-2 text-xs text-blue-700">{seconds}초 경과</p>
      <p role="status" className="mt-2 text-xs leading-relaxed text-blue-800">
        {seconds >= 15 ? '공시 조회나 AI 분석이 길어지고 있습니다. 처음 조회하는 기업은 수 분 걸릴 수 있어요.' : '공시 조회와 분석에 시간이 걸릴 수 있습니다. 잠시 기다려주세요.'}
      </p>
    </div>
  );
}
