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
  const { autoFetch = true } = options;

  const requestId = useRef(0);
  const inFlight = useRef<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const onSearchedRef = useRef(onSearched);
  onSearchedRef.current = onSearched;
  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [data, setData] = useState<T | null>(null);
  const [resolvedName, setResolvedName] = useState('');

  const fetchData = useCallback(async (nameOverride?: string): Promise<void> => {
    const name = (nameOverride ?? companyName).trim();
    if (!name) { setMessage('오류: 회사명을 입력해주세요.'); return; }
    if (inFlight.current === name) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const { buildPath, extractData, extractCompanyName, timeout = 300_000 } = optionsRef.current;
    const timer = setTimeout(() => abort.abort(), timeout);
    inFlight.current = name;
    const id = ++requestId.current;
    setCompanyName(name);
    setLoading(true); setMessage(''); setData(null); setResolvedName('');
    try {
      const res = await fetch(
        `${API_BASE}${buildPath(encodeURIComponent(name))}`,
        { signal: abort.signal }
      );
      const json = await res.json().catch(() => {
        if (res.ok) throw new Error('서버 응답을 읽지 못했습니다. 잠시 후 다시 시도해주세요.');
        return {};
      }) as Record<string, unknown>;
      if (id !== requestId.current) return;
      if (!res.ok) {
        const detail = typeof json.detail === 'string' ? json.detail : '';
        throw new Error(detail || (res.status === 404
          ? '해당 기업의 데이터를 찾지 못했습니다. 정식 회사명을 확인해주세요.'
          : '데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.'));
      }
      const resolved = extractCompanyName?.(json) || (typeof json.company_name === 'string' ? json.company_name : name);
      const result = extractData(json);
      setResolvedName(resolved);
      setData(result);
      setMessage(`'${resolved}' 데이터 조회 완료`);
    } catch (e: unknown) {
      if (id !== requestId.current) return;
      const reason = abort.signal.aborted
        ? '조회 시간이 길어져 중단했습니다. 잠시 후 다시 시도해주세요.'
        : e instanceof TypeError ? '서버에 연결하지 못했습니다. 연결 상태를 확인하고 다시 시도해주세요.'
        : e instanceof Error ? e.message : '조회 중 문제가 발생했습니다. 다시 시도해주세요.';
      setMessage(`오류: ${reason}`);
    } finally {
      clearTimeout(timer);
      if (id === requestId.current) {
        inFlight.current = null;
        setLoading(false);
        onSearchedRef.current?.();
      }
    }
  }, [companyName]);

  useEffect(() => {
    // 부모가 검색 완료 후 initialCompany를 지워도 현재 결과는 유지합니다.
    if (initialCompany === undefined) return;
    ++requestId.current;
    controller.current?.abort();
    inFlight.current = null;
    setData(null); setMessage(''); setResolvedName(''); setLoading(false);
    setCompanyName(initialCompany);
    if (autoFetch && initialCompany.trim()) fetchData(initialCompany);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCompany, autoFetch]);

  useEffect(() => () => { ++requestId.current; controller.current?.abort(); inFlight.current = null; }, []);

  return { data, loading, message, resolvedName, fetchData, companyName, setCompanyName };
}
