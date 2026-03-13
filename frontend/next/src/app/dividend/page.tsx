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
interface DividendDataItem {
  year: number;
  quarter: string;
  dividend: number;
  report_date: string;
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
  const [companyName, setCompanyName] = useState<string>('삼성전자'); // 회사명 입력 필드
  const [message, setMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [chartData, setChartData] = useState<ChartDataItem | null>(null);
  const [dividendData, setDividendData] = useState<DividendDataItem[]>([]);

  const handleFetchDividend = async (): Promise<void> => {
    if (!companyName.trim()) {
      setMessage('회사명을 입력해주세요.');
      return;
    }

    setLoading(true);
    setMessage('배당 내역을 불러오는 중...');
    setChartData(null);
    setDividendData([]);

    try {
      // FastAPI 백엔드의 /analyze-dividends-json/{company_name} 엔드포인트 호출
      const response: Response = await fetch(`http://localhost:8000/analyze-dividends-json/${encodeURIComponent(companyName)}`);
      const data: any = await response.json();

      if (response.ok && data.dividend_data) {
        setMessage(`'${companyName}'의 배당 내역을 성공적으로 조회했습니다.`);
        setDividendData(data.dividend_data);

        // Chart.js 데이터 형식으로 변환
        const labels = data.dividend_data.map((item: DividendDataItem) => `${item.year}-${item.quarter}`);
        const amounts = data.dividend_data.map((item: DividendDataItem) => item.dividend);

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
        setMessage(`오류: ${data.detail || '회사를 찾을 수 없습니다. 다시 확인해주세요.'}`);
      }
    } catch (error: any) {
      setMessage(`네트워크 오류: ${error.message}. FastAPI 서버(http://localhost:8000)가 실행 중인지 확인하세요.`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
      handleFetchDividend();
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
        text: `${companyName} 배당 내역 (최근 5년)`,
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
      <h1 style={styles.heading}>기업 배당 내역 조회</h1>
      <p style={styles.paragraph}>기업명을 입력하고 배당 내역을 조회하세요 (예: 삼성전자, SK하이닉스, LG전자)</p>

      <div style={styles.inputGroup}>
        <input
          type="text"
          placeholder="기업명을 입력하세요 (예: 삼성전자)"
          value={companyName}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCompanyName(e.target.value)}
          onKeyPress={handleKeyPress}
          style={styles.input}
          disabled={loading}
        />
        <button
          onClick={handleFetchDividend}
          style={styles.button}
          disabled={loading}
        >
          {loading ? '조회 중...' : '조회'}
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

          {/* 배당 데이터 테이블 */}
          {dividendData.length > 0 && (
            <div style={styles.tableContainer}>
              <h2>배당금 상세 내역</h2>
              <table style={styles.table}>
                <thead>
                  <tr style={styles.tableHeaderRow}>
                    <th style={styles.tableHeader}>연도</th>
                    <th style={styles.tableHeader}>분기</th>
                    <th style={styles.tableHeader}>주당 배당금 (원)</th>
                    <th style={styles.tableHeader}>보고서 접수일</th>
                  </tr>
                </thead>
                <tbody>
                  {dividendData.map((item, index) => (
                    <tr key={index} style={styles.tableRow}>
                      <td style={styles.tableCell}>{item.year}</td>
                      <td style={styles.tableCell}>{item.quarter}</td>
                      <td style={styles.tableCell}>{item.dividend.toLocaleString()}</td>
                      <td style={styles.tableCell}>{item.report_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        chartData && !loading && message.startsWith("성공") && (
            <p style={styles.noDataMessage}>조회된 배당 데이터가 없습니다.</p>
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
  },
  tableContainer: {
    marginTop: '30px',
    width: '100%',
    maxWidth: '800px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse' as 'collapse',
    marginTop: '15px',
    boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
  },
  tableHeaderRow: {
    backgroundColor: '#007bff',
  },
  tableHeader: {
    padding: '12px',
    textAlign: 'center' as 'center',
    color: 'white',
    fontWeight: 'bold',
    borderBottom: '2px solid #0056b3',
  },
  tableRow: {
    borderBottom: '1px solid #dee2e6',
    backgroundColor: '#fff',
    transition: 'background-color 0.2s ease',
  },
  tableCell: {
    padding: '12px',
    textAlign: 'center' as 'center',
    borderRight: '1px solid #dee2e6',
  }
};
