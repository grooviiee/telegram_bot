"use client";
import { useState, useCallback, useEffect, useRef } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface UseDartDataOptions<T> {
  buildPath: (company: string) => string;
  extractData: (json: unknown) => T;
  extractCompanyName?: (json: unknown) => string;
  timeout?: number;
  autoFetch?: boolean;
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
  const { buildPath, extractData, timeout = 300_000, autoFetch = true } = options;

  const requestId = useRef(0);
  const inFlight = useRef<string | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [data, setData] = useState<T | null>(null);
  const [resolvedName, setResolvedName] = useState('');

  const fetchData = useCallback(async (nameOverride?: string): Promise<void> => {
    const name = (nameOverride ?? companyName).trim();
    if (!name) { setMessage('회사명을 입력해주세요.'); return; }
    if (inFlight.current === name) return;
    inFlight.current = name;
    const id = ++requestId.current;
    setLoading(true); setMessage(''); setData(null); setResolvedName('');
    try {
      const res = await fetch(
        `${API_BASE}${buildPath(encodeURIComponent(name))}`,
        { signal: AbortSignal.timeout(timeout) }
      );
      const json = await res.json() as Record<string, unknown>;
      if (id !== requestId.current) return;
      if (!res.ok) throw new Error((json.detail as string) || '데이터 조회에 실패했습니다.');
      setResolvedName(json.company_name as string);
      setData(extractData(json));
      setMessage(`'${json.company_name}' 데이터 조회 완료`);
    } catch (e: unknown) {
      if (id !== requestId.current) return;
      setMessage(`오류: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      if (id === requestId.current) {
        inFlight.current = null;
        setLoading(false);
        onSearched?.();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyName, buildPath, extractData, timeout]);

  useEffect(() => {
    // 부모가 검색 완료 후 initialCompany를 지워도 현재 결과는 유지합니다.
    if (!initialCompany) return;
    ++requestId.current;
    inFlight.current = null;
    setData(null); setMessage(''); setResolvedName(''); setLoading(false);
    setCompanyName(initialCompany);
    if (autoFetch) fetchData(initialCompany);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCompany, autoFetch]);

  useEffect(() => () => { ++requestId.current; inFlight.current = null; }, []);

  return { data, loading, message, resolvedName, fetchData, companyName, setCompanyName };
}
