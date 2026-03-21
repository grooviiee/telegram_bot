"use client";
import { useState, useCallback, useEffect } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface UseDartDataOptions<T> {
  buildPath: (company: string) => string;
  extractData: (json: unknown) => T;
  extractCompanyName?: (json: unknown) => string;
  timeout?: number;
}

export interface UseDartDataResult<T> {
  data: T | null;
  loading: boolean;
  message: string;
  resolvedName: string;
  fetchData: (nameOverride?: string) => Promise<void>;
  companyName: string;
  setCompanyName: (name: string) => void;
}

export function useDartData<T>(
  options: UseDartDataOptions<T>,
  initialCompany?: string,
  onSearched?: () => void,
): UseDartDataResult<T> {
  const { buildPath, extractData, timeout = 300_000 } = options;

  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [data, setData] = useState<T | null>(null);
  const [resolvedName, setResolvedName] = useState('');

  const fetchData = useCallback(async (nameOverride?: string): Promise<void> => {
    const name = (nameOverride ?? companyName).trim();
    if (!name) { setMessage('회사명을 입력해주세요.'); return; }
    setLoading(true); setMessage(''); setData(null); setResolvedName('');
    try {
      const res = await fetch(
        `${API_BASE}${buildPath(encodeURIComponent(name))}`,
        { signal: AbortSignal.timeout(timeout) }
      );
      const json = await res.json() as Record<string, unknown>;
      if (!res.ok) throw new Error((json.detail as string) || '데이터 조회에 실패했습니다.');
      setResolvedName(json.company_name as string);
      setData(extractData(json));
      setMessage(`'${json.company_name}' 데이터 조회 완료`);
    } catch (e: unknown) {
      setMessage(`오류: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
      onSearched?.();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyName, buildPath, extractData, timeout]);

  useEffect(() => {
    if (initialCompany) {
      setCompanyName(initialCompany);
      fetchData(initialCompany);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCompany]);

  return { data, loading, message, resolvedName, fetchData, companyName, setCompanyName };
}
