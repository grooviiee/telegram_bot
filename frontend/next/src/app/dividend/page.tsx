"use client"; // 이 컴포넌트는 클라이언트 컴포넌트임을 명시합니다.

import React, { useState } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

// Chart.js에 필요한 컴포넌트들을 등록합니다.
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

// 배당 데이터를 위한 인터페이스 정의
interface DividendData {
  year: number;
  amount: number;
}

// 차트 데이터를 위한 인터페이스 정의
interface ChartDataItem {
  labels: string[];
  datasets: {
    label: string;
    data: number[];
    backgroundColor: string;
    borderColor: string;
    borderWidth: number;
  }[];
}

export default function DividendChartPage(): JSX.Element {
  // 환경 변수에서 기본 회사 고유번호를 가져옵니다.
  // NEXT_PUBLIC_DEFAULT_CORP_CODE가 정의되어 있지 않으면 빈 문자열을 기본값으로 사용합니다.
  const defaultCorpCode = process.env.NEXT_PUBLIC_DEFAULT_CORP_CODE || '';
  const [companyCorpCode, setCompanyCorpCode] = useState<string>(defaultCorpCode); // 회사 고유번호 입력 필드
  const [message, setMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [chartData, setChartData] = useState<ChartDataItem | null>(null);

  const handleFetchDividend = async (): Promise<void> => {
    if (!companyCorpCode) {
      setMessage('회사 고유번호를 입력해주세요.');
      return;
    }

    setLoading(true);
    setMessage('배당 내역을 불러오는 중...');
    setChartData(null); // 새로운 조회 시작 시 이전 차트 데이터 초기화

    try {
      // Flask 백엔드의 /get_dividend 엔드포인트 호출
      const response: Response = await fetch(`http://localhost:5000/get_dividend?company=${companyCorpCode}`);
      const data: { status?: string; company_corp_code?: string; dividend_history?: DividendData[]; error?: string; message?: string } = await response.json();

      if (response.ok && data.status === "success" && data.dividend_history) {
        setMessage(`'${companyCorpCode}'의 배당 내역을 성공적으로 조회했습니다.`);
        
        // Chart.js 데이터 형식으로 변환
        const labels = data.dividend_history.map(item => String(item.year)); // 연도를 문자열로 변환
        const amounts = data.dividend_history.map(item => item.amount); // 배당액

        setChartData({
          labels: labels,
          datasets: [
            {
              label: '주당 현금 배당액 (원)',
              data: amounts,
              backgroundColor: 'rgba(75, 192, 192, 0.6)',
              borderColor: 'rgba(75, 192, 192, 1)',
              borderWidth: 1,
            },
          ],
        });
      } else {
        setMessage(`오류: ${data.message || data.error || '알 수 없는 오류가 발생했습니다.'}`);
      }
    } catch (error: any) {
      setMessage(`네트워크 오류: ${error.message}. Flask 서버가 실행 중인지 확인하세요.`);
    } finally {
      setLoading(false);
    }
  };

  // Chart.js 옵션 설정
  const options = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: `${companyCorpCode} 배당 내역 (최근 5개년)`,
      },
      tooltip: { // 툴팁에 콤마 추가
        callbacks: {
          label: function(context: any) {
            let label = context.dataset.label || '';
            if (label) {
              label += ': ';
            }
            if (context.parsed.y !== null) {
              label += context.parsed.y.toLocaleString() + '원';
            }
            return label;
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: '배당액 (원)',
        },
        ticks: { // Y축 눈금에 콤마 추가
            callback: function(value: string | number) {
                return Number(value).toLocaleString();
            }
        }
      },
      x: {
        title: {
          display: true,
          text: '사업연도',
        }
      }
    }
  };

  return (
    <div style={styles.container}>
      <h1 style={styles.heading}>기업 배당 내역 조회 및 차트</h1>
      <p style={styles.paragraph}>OpenDART 회사 고유번호 (8자리)를 입력하고 배당 내역을 조회하세요.</p>

      <div style={styles.inputGroup}>
        <input
          type="text"
          placeholder="회사 고유번호 (예: 00126380)" // 삼성전자 고유번호
          value={companyCorpCode}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCompanyCorpCode(e.target.value)}
          style={styles.input}
          disabled={loading}
        />
        <button
          onClick={handleFetchDividend}
          style={styles.button}
          disabled={loading}
        >
          {loading ? '조회 중...' : '배당 내역 조회'}
        </button>
      </div>

      {message && (
        <p style={{
          ...styles.message,
          color: message.startsWith('오류') || message.startsWith('네트워크') ? '#dc3545' : '#28a745'
        }}>
          {message}
        </p>
      )}

      {/* 차트 표시 조건: 차트 데이터가 있고, 데이터셋의 데이터가 0이 아닌 값이 하나라도 있을 때 */}
      {chartData && chartData.datasets[0].data.some(amount => amount > 0) ? (
        <div style={styles.chartContainer}>
          <Bar options={options} data={chartData} />
        </div>
      ) : (
        // 데이터가 없거나 모두 0일 때 메시지 표시
        chartData && !loading && message.startsWith("성공") && (
            <p style={styles.noDataMessage}>조회된 배당 데이터가 없거나 모든 연도의 배당액이 0입니다.</p>
        )
      )}
    </div>
  );
}

// 스타일 (이전 예시와 동일하며, 필요에 따라 조정 가능)
interface Styles {
  [key: string]: React.CSSProperties;
}

const styles: Styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as 'column',
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
    textAlign: 'center' as 'center',
  },
  paragraph: {
    fontSize: '1.1em',
    marginBottom: '25px',
    textAlign: 'center' as 'center',
    maxWidth: '600px',
    lineHeight: '1.5',
  },
  inputGroup: {
    display: 'flex',
    marginBottom: '20px',
    gap: '10px',
  },
  input: {
    width: '100%',
    maxWidth: '300px',
    padding: '12px 15px',
    borderRadius: '8px',
    border: '1px solid #ced4da',
    fontSize: '1em',
    boxSizing: 'border-box' as 'border-box',
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
    textAlign: 'center' as 'center',
  },
  chartContainer: {
    width: '100%',
    maxWidth: '800px',
    marginTop: '30px',
    padding: '20px',
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)',
  },
  noDataMessage: {
    marginTop: '30px',
    fontSize: '1.2em',
    color: '#6c757d',
  }
};
