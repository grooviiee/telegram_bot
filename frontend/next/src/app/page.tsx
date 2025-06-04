// src/app/page.tsx
"use client"; // 이 컴포넌트는 클라이언트 컴포넌트임을 명시합니다.

import React, { useState } from 'react';

// 페이지 컴포넌트
export default function HomePage(): JSX.Element {
  const [apiKey, setApiKey] = useState<string>('');
  const [message, setMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  const handleDownload = async (): Promise<void> => {
    if (!apiKey) {
      setMessage('API 키를 입력해주세요.');
      return;
    }

    setLoading(true);
    setMessage('다운로드 요청 중...');

    try {
      const flaskBackendUrl: string = `http://localhost:5000/download-corp-code?api_key=${apiKey}`;

      const response: Response = await fetch(flaskBackendUrl);
      const data: { status?: string; message?: string; error?: string; warning?: string } = await response.json();

      if (response.ok) {
        setMessage(`성공: ${data.message}`);
      } else {
        setMessage(`오류: ${data.message || data.error || data.warning || '알 수 없는 오류가 발생했습니다.'}`);
      }
    } catch (error: any) {
      setMessage(`네트워크 오류: ${error.message}. Flask 서버가 실행 중인지 확인해주세요.`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <h1 style={styles.heading}>OpenDART 기업개황정보 다운로더</h1>
      <p style={styles.paragraph}>아래에 OpenDART API 키를 입력하고 다운로드 버튼을 클릭하세요.</p>
      <input
        type="text"
        placeholder="OpenDART API 키"
        value={apiKey}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)}
        style={styles.input}
        disabled={loading}
      />
      <button
        onClick={handleDownload}
        style={styles.button}
        disabled={loading}
      >
        {loading ? '다운로드 중...' : 'ZIP 파일 다운로드 요청'}
      </button>
      {message && (
        <p style={{
          ...styles.message,
          color: message.startsWith('오류') || message.startsWith('네트워크') ? '#dc3545' : '#28a745'
        }}>
          {message}
        </p>
      )}
    </div>
  );
}

interface Styles {
  [key: string]: React.CSSProperties;
}

const styles: Styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: '20px',
    fontFamily: 'Arial, sans-serif',
    backgroundColor: '#f8f9fa',
    color: '#343a40',
  },
  heading: {
    fontSize: '2.5em',
    color: '#0056b3',
    marginBottom: '20px',
    textAlign: 'center',
  },
  paragraph: {
    fontSize: '1.1em',
    marginBottom: '25px',
    textAlign: 'center',
    maxWidth: '600px',
    lineHeight: '1.5',
  },
  input: {
    width: '100%',
    maxWidth: '400px',
    padding: '12px 15px',
    marginBottom: '20px',
    borderRadius: '8px',
    border: '1px solid #ced4da',
    fontSize: '1em',
    boxSizing: 'border-box',
  },
  button: {
    padding: '12px 25px',
    fontSize: '1.1em',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#007bff',
    color: 'white',
    cursor: 'pointer',
    transition: 'background-color 0.3s ease',
  },
  message: {
    marginTop: '25px',
    padding: '10px 20px',
    borderRadius: '5px',
    backgroundColor: '#e9ecef',
    border: '1px solid #dee2e6',
    textAlign: 'center',
  },
};