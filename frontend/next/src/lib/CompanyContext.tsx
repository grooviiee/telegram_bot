"use client";

import { createContext, useContext, useEffect } from 'react';

export const CompanyContext = createContext<{ company: string; rememberCompany: (company: string) => void }>({
  company: '',
  rememberCompany: () => {},
});

/** 조회에 성공한 기업을 다른 분석 화면에서도 이어서 사용합니다. */
export function useRememberCompany(company: string) {
  const { rememberCompany } = useContext(CompanyContext);
  useEffect(() => {
    if (company) rememberCompany(company);
  }, [company, rememberCompany]);
}
