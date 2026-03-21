/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState } from 'react';
import { ProgressIndicator } from '@/components/ProgressIndicator';
import { useDartData } from '@/lib/useDartData';

interface Block {
  type: 'text' | 'table';
  content?: string;
  html?: string;
}

interface Section {
  number: number;
  title: string;
  blocks: Block[];
}

interface BusinessOverview {
  sections: Section[];
  report_name: string;
  report_year: string;
  rcept_no: string;
}

const PAGE_KEY = 'business';

const BUSINESS_STEPS = [
  { label: '회사명으로 DART 기업 정보를 검색하는 중', after: 0 },
  { label: '최신 사업보고서를 조회하는 중',           after: 1_500 },
  { label: '보고서 문서를 다운로드하는 중',           after: 3_000 },
  { label: '사업의 내용 1~4항을 추출하는 중',        after: 7_000 },
];

interface Props {
  toggleFavorite?: (company: string, page: string) => void;
  isFavorite?: (company: string, page: string) => boolean;
  initialCompany?: string;
  onSearched?: () => void;
}

function renderTextBlock(content: string) {
  return content
    .split(/\n\n+/)
    .map((para) => para.trim())
    .filter((para) => para.length > 0)
    .map((para, i) => (
      <p key={i} className="text-sm text-gray-700 leading-relaxed mb-3 last:mb-0">
        {para.split('\n').map((line, j, arr) => (
          <React.Fragment key={j}>
            {line}
            {j < arr.length - 1 && <br />}
          </React.Fragment>
        ))}
      </p>
    ));
}

function renderBlocks(blocks: Block[]) {
  return blocks.map((block, i) => {
    if (block.type === 'table' && block.html) {
      return (
        <div
          key={i}
          className="dart-table-wrapper my-4 overflow-x-auto"
          dangerouslySetInnerHTML={{ __html: block.html }}
        />
      );
    }
    return (
      <div key={i}>
        {renderTextBlock(block.content ?? '')}
      </div>
    );
  });
}

function SectionCard({ section }: { section: Section }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition-colors"
      >
        <span className="font-semibold text-gray-800 text-sm">
          {section.number}. {section.title}
        </span>
        <span className="text-gray-400 text-lg leading-none">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-gray-100">
          <div className="pt-4">
            {renderBlocks(section.blocks)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function BusinessPage({
  toggleFavorite,
  isFavorite,
  initialCompany,
  onSearched,
}: Props = {}) {
  const { companyName, setCompanyName, loading, message, resolvedName, fetchData, data } =
    useDartData<BusinessOverview>(
      {
        buildPath: (n) => `/business-overview/${n}`,
        extractData: (j: any) => ({
          sections:     j.sections,
          report_name:  j.report_name,
          report_year:  j.report_year,
          rcept_no:     j.rcept_no,
        }),
      },
      initialCompany,
      onSearched,
    );

  const isError = message.startsWith('오류');
  const starred = resolvedName && isFavorite ? isFavorite(resolvedName, PAGE_KEY) : false;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">사업 분석</h1>
      <p className="text-sm text-gray-500 mb-6">DART 최신 사업보고서 — 사업의 내용 1~4항</p>

      {/* 검색 */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="회사명 입력 (예: 삼성전자)"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetchData()}
          disabled={loading}
          className="flex-1 max-w-xs px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={() => fetchData()}
          disabled={loading}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? '조회 중...' : '조회'}
        </button>
        {resolvedName && toggleFavorite && (
          <button
            onClick={() => toggleFavorite(resolvedName, PAGE_KEY)}
            title={starred ? '즐겨찾기 해제' : '즐겨찾기 추가'}
            className={`px-3 py-2 rounded-lg text-xl leading-none transition-colors ${
              starred
                ? 'text-yellow-400 hover:text-gray-300'
                : 'text-gray-300 hover:text-yellow-400'
            }`}
          >
            {starred ? '★' : '☆'}
          </button>
        )}
      </div>

      <ProgressIndicator steps={BUSINESS_STEPS} active={loading} />

      {message && (
        <p className={`mb-5 text-sm font-medium ${isError ? 'text-red-500' : 'text-green-600'}`}>
          {message}
        </p>
      )}

      {data && (
        <>
          {/* 보고서 메타 정보 */}
          <div className="flex items-center gap-3 mb-5 text-sm text-gray-500">
            <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded-full font-medium">
              {data.report_year}년
            </span>
            <span>{data.report_name}</span>
            <span className="text-gray-300">|</span>
            <span className="text-gray-400">접수번호 {data.rcept_no}</span>
          </div>

          {/* 섹션 카드 목록 */}
          <div className="flex flex-col gap-4 max-w-4xl">
            {data.sections.map((section) => (
              <SectionCard key={section.number} section={section} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
