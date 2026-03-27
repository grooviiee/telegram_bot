/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useState, useCallback, useRef, useEffect } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface Message {
  role: 'user' | 'model';
  text: string;
}

interface Props {
  initialCompany?: string;
  onSearched?: () => void;
}

const SUGGESTED_QUESTIONS = [
  '최근 매출과 영업이익 추세를 알려줘',
  '부채비율과 재무 건전성은 어때?',
  '배당금은 얼마나 지급하고 있어?',
  '주요 사업과 경쟁력이 뭐야?',
  '현재 밸류에이션은 저평가야, 고평가야?',
  '최근 주요 공시 내용이 뭐야?',
  '이 회사에 투자할 때 주요 리스크가 뭐야?',
];

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 mt-1">
          AI
        </div>
      )}
      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-white border border-gray-100 shadow-sm text-gray-800 rounded-bl-sm'
        }`}
      >
        {msg.text}
      </div>
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-gray-600 text-xs font-bold ml-2 flex-shrink-0 mt-1">
          나
        </div>
      )}
    </div>
  );
}

export default function ChatPage({ initialCompany, onSearched }: Props = {}) {
  const [companyInput, setCompanyInput] = useState(initialCompany ?? '');
  const [loadedCompany, setLoadedCompany] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [companyLoading, setCompanyLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadCompany = useCallback(async (name?: string) => {
    const target = (name ?? companyInput).trim();
    if (!target) return;
    setCompanyLoading(true);
    setMessages([]);
    try {
      // 기업 존재 여부 확인 (financials 호출)
      const res = await fetch(
        `${API_BASE}/financials/${encodeURIComponent(target)}`,
        { signal: AbortSignal.timeout(30_000) }
      );
      if (!res.ok) throw new Error('기업을 찾을 수 없습니다');
      const json = await res.json() as any;
      const name2 = json.company_name ?? target;
      setLoadedCompany(name2);
      setCompanyInput(name2);
      setMessages([{
        role: 'model',
        text: `${name2}의 DART 공시 데이터를 불러왔습니다.\n\n재무 지표, 배당 이력, 사업 내용, 최근 공시를 기반으로 질문에 답변드릴게요. 무엇이 궁금하신가요?`,
      }]);
      onSearched?.();
    } catch (e: any) {
      setMessages([{ role: 'model', text: `오류: ${e.message}` }]);
    } finally {
      setCompanyLoading(false);
    }
  }, [companyInput, onSearched]);

  useEffect(() => {
    if (initialCompany) loadCompany(initialCompany);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCompany]);

  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || !loadedCompany || loading) return;
    setInput('');

    const userMsg: Message = { role: 'user', text: msg };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setLoading(true);

    // 시스템 메시지(첫 model 인사) 제외하고 이력 전달
    const history = newMessages.slice(1).map(m => ({ role: m.role, text: m.text }));

    try {
      const res = await fetch(
        `${API_BASE}/chat/${encodeURIComponent(loadedCompany)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg, history: history.slice(0, -1), mode: 'buffett' }),
          signal: AbortSignal.timeout(60_000),
        }
      );
      const json = await res.json() as any;
      if (!res.ok) throw new Error(json.detail ?? '오류가 발생했습니다');
      setMessages(prev => [...prev, { role: 'model', text: json.answer }]);
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'model', text: `오류: ${e.message}` }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [input, loadedCompany, loading, messages]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-56px)] bg-gray-50">
      {/* 헤더 */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <div className="flex-1">
          <h1 className="text-lg font-bold text-gray-800">종목 AI 상담</h1>
          <p className="text-xs text-gray-400">DART 공시 데이터 기반 투자 상담</p>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="회사명 입력"
            value={companyInput}
            onChange={e => setCompanyInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadCompany()}
            disabled={companyLoading}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 w-40 disabled:opacity-50"
          />
          <button
            onClick={() => loadCompany()}
            disabled={companyLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {companyLoading ? '불러오는 중...' : loadedCompany ? '변경' : '시작'}
          </button>
        </div>
        {loadedCompany && (
          <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded-full text-sm font-medium">
            {loadedCompany}
          </span>
        )}
      </div>

      {/* 메시지 영역 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
              <span className="text-2xl">💬</span>
            </div>
            <p className="text-gray-500 text-sm mb-2">회사명을 입력하고 상담을 시작하세요</p>
            <p className="text-gray-400 text-xs">DART 공시 데이터를 기반으로 투자 관련 질문에 답변드립니다</p>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
            {loading && (
              <div className="flex justify-start mb-4">
                <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0">
                  AI
                </div>
                <div className="bg-white border border-gray-100 shadow-sm px-4 py-3 rounded-2xl rounded-bl-sm">
                  <div className="flex gap-1 items-center h-5">
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* 추천 질문 */}
      {loadedCompany && messages.length <= 1 && !loading && (
        <div className="px-6 pb-2">
          <p className="text-xs text-gray-400 mb-2">추천 질문</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => sendMessage(q)}
                className="px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 입력창 */}
      <div className="bg-white border-t border-gray-200 px-6 py-4">
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={loadedCompany ? `${loadedCompany}에 대해 질문하세요... (Enter로 전송)` : '먼저 회사를 선택하세요'}
            disabled={!loadedCompany || loading}
            rows={2}
            className="flex-1 px-4 py-3 border border-gray-300 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 resize-none"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!loadedCompany || loading || !input.trim()}
            className="px-5 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors flex-shrink-0"
          >
            전송
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          * 본 상담은 DART 공시 데이터 기반 AI 분석이며, 투자 결정의 책임은 투자자 본인에게 있습니다.
        </p>
      </div>
    </div>
  );
}
