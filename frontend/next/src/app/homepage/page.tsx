// src/app/page.tsx
"use client"; // 이 컴포넌트는 클라이언트 컴포넌트임을 명시합니다.

import React, { JSX, useState } from 'react';
import Link from 'next/link'
import { useRouter } from 'next/router';



// 페이지 컴포넌트
export default function HomePage(): JSX.Element {
  const [apiKey, setApiKey] = useState<string>('aaf2ed404abd73c00ab27a6ba80476131e6f9a73');
  const [message, setMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [downloadSuccess, setDownloadSuccess] = useState<boolean>(false);


  const handleGoToNextPage = (): void => {
    const router = useRouter();
    router.push('/dashboard'); // 이동하려는 페이지 경로로 변경하세요.
  };

  const handleDownload = async (): Promise<void> => {
    if (!apiKey) {
      setMessage('API 키를 입력해주세요.');
    }
    setLoading(true);
    const flaskBackendUrl: string = `http://localhost:5002/download-corp-code?api_key=12345`;
    try {
      setMessage(`다운로드 요청 중... (URL: ${flaskBackendUrl})`);
      const response: Response = await fetch(flaskBackendUrl, {method: 'GET'});
      const data: { status?: string; message?: string; error?: string; warning?: string } = await response.json();
      console.log('Full Response Object:', response); // 전체 Response 객체 출력
      console.log('Parsed Data (JSON):', data);     // 파싱된 JSON 데이터 출력
      if (response.ok) {
        setMessage(`성공: ${data.message}`);
      } else {
        setMessage(`오류: ${data.message || data.error || data.warning || '알 수 없는 오류가 발생했습니다.'}`);
      }
    } catch (error: any) {
      // 네트워크 오류 또는 JSON 파싱 오류 등 실제 예외가 발생했을 때 처리
      console.log('error:', error.message)
      setMessage(`네트워크 오류: ${error.message}.\nFlask 서버가 실행 중인지 확인해주세요. (요청 URL: ${flaskBackendUrl})`);
      setDownloadSuccess(false); // 오류 발생 시 downloadSuccess 상태 초기화
    } finally {
      // 요청이 성공하든 실패하든, 로딩 상태는 항상 비활성화
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <h1 style={styles.heading}>OpenDART 데이터 조회 앱</h1>
      <p style={styles.paragraph}>
        OpenDART에서 제공하는 기업 정보를 조회하고 시각화하는 애플리케이션입니다.
      </p>
      <Link href="/dividend" passHref> {/* /dividend 경로로 이동하는 Link 컴포넌트 */}
        <button style={styles.button}>
          기업 배당 내역 조회 페이지로 이동
        </button>
      </Link>
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
        {loading ? '확인 중...' : 'API 확인 시작'}
      </button>
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
      {/* 다운로드가 성공했을 때만 이 버튼을 렌더링합니다 */}
            {downloadSuccess && (
        <button
          onClick={handleGoToNextPage}
          style={{
            marginTop: '20px',
            padding: '10px 20px',
            backgroundColor: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '5px',
            cursor: 'pointer',
          }}
        >
          다음 페이지로 이동
        </button>
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