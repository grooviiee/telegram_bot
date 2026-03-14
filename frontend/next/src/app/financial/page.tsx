"use client";

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

import { FinancialDataItem, FinancialMetricsResponse, MetricType } from './types';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

// 인기 기업 목록
const POPULAR_COMPANIES = [
  '삼성전자',
  'SK하이닉스',
  'LG전자',
  'NAVER',
  'Kakao',
  '현대자동차',
  'Coupang',
  'HD현대',
];

export default function FinancialPage(): JSX.Element {
  const [companyName, setCompanyName] = useState<string>('삼성전자');
  const [selectedMetric, setSelectedMetric] = useState<MetricType>('all');
  const [message, setMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [data, setData] = useState<FinancialMetricsResponse | null>(null);

  const handleFetchFinancialData = async (): Promise<void> => {
    if (!companyName.trim()) {
      setMessage('회사명을 입력해주세요.');
      return;
    }

    setLoading(true);
    setMessage('재무 정보를 불러오는 중...');
    setData(null);

    try {
      const response: Response = await fetch(
        `http://localhost:8000/api/financial-metrics/${encodeURIComponent(companyName)}`
      );
      const responseData: FinancialMetricsResponse = await response.json();

      if (response.ok && responseData.metrics) {
        setMessage(`'${companyName}'의 재무 정보를 성공적으로 조회했습니다.`);
        setData(responseData);
      } else {
        setMessage(`오류: ${(responseData as any).detail || '재무 정보를 조회할 수 없습니다.'}`);
      }
    } catch (error: any) {
      setMessage(`네트워크 오류: ${error.message}. FastAPI 서버(http://localhost:8000)가 실행 중인지 확인하세요.`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
      handleFetchFinancialData();
    }
  };

  // 선택된 메트릭의 데이터만 필터링
  const getDisplayData = (): { [key in MetricType]?: FinancialDataItem[] } | null => {
    if (!data) return null;

    if (selectedMetric === 'all') {
      return data.metrics;
    }
    return {
      [selectedMetric]: data.metrics[selectedMetric as keyof typeof data.metrics],
    };
  };

  // 숫자 포맷팅 함수
  const formatFinancialValue = (value: number): string => {
    if (value >= 1_000_000_000_000) {
      return `${(value / 1_000_000_000_000).toFixed(1)}조`;
    } else if (value >= 100_000_000) {
      return `${(value / 100_000_000).toFixed(0)}억`;
    } else if (value >= 1_000_000) {
      return `${(value / 1_000_000).toFixed(0)}백만`;
    }
    return value.toLocaleString() + '원';
  };

  // 메트릭 이름 한글 변환
  const getMetricLabel = (metric: string): string => {
    const labels: { [key: string]: string } = {
      revenue: '매출액',
      operating_income: '영업이익',
      net_income: '순이익',
    };
    return labels[metric] || metric;
  };

  // 차트 데이터 생성 함수
  const createChartData = (metric: string, items: FinancialDataItem[] | undefined) => {
    if (!items || items.length === 0) return null;

    const labels = items.map((item) => `${item.year}-${item.quarter}`);
    const values = items.map((item) => item.value);

    const colors: { [key: string]: string } = {
      revenue: 'rgba(75, 192, 192, 0.6)',
      operating_income: 'rgba(255, 193, 7, 0.6)',
      net_income: 'rgba(76, 175, 80, 0.6)',
    };

    const borderColors: { [key: string]: string } = {
      revenue: 'rgba(75, 192, 192, 1)',
      operating_income: 'rgba(255, 193, 7, 1)',
      net_income: 'rgba(76, 175, 80, 1)',
    };

    return {
      labels,
      datasets: [
        {
          label: `${getMetricLabel(metric)} (원)`,
          data: values,
          backgroundColor: colors[metric] || 'rgba(75, 192, 192, 0.6)',
          borderColor: borderColors[metric] || 'rgba(75, 192, 192, 1)',
          borderWidth: 1,
        },
      ],
    };
  };

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: `${companyName} - ${getMetricLabel(selectedMetric === 'all' ? 'revenue' : selectedMetric)} (분기별)`,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          callback: function(value: any) {
            return formatFinancialValue(value);
          },
        },
      },
    },
  };

  const displayData = getDisplayData();

  return (
    <div style={styles.container}>
      <h1 style={styles.heading}>재무 정보 분석</h1>
      <p style={styles.paragraph}>기업명을 입력하고 분기별 재무 정보를 조회하세요.</p>

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
          onClick={handleFetchFinancialData}
          style={styles.button}
          disabled={loading}
        >
          {loading ? '조회 중...' : '조회'}
        </button>
      </div>

      {/* 인기 기업 버튼 */}
      <div style={styles.popularCompanies}>
        <p style={styles.popularLabel}>인기 기업:</p>
        <div style={styles.buttonGroup}>
          {POPULAR_COMPANIES.map((company) => (
            <button
              key={company}
              onClick={() => setCompanyName(company)}
              style={{
                ...styles.companyButton,
                backgroundColor: companyName === company ? '#007bff' : '#e9ecef',
                color: companyName === company ? 'white' : '#343a40',
              }}
              disabled={loading}
            >
              {company}
            </button>
          ))}
        </div>
      </div>

      {message && (
        <p
          style={{
            ...styles.message,
            color: message.startsWith('오류') || message.startsWith('네트워크') ? '#dc3545' : '#28a745',
          }}
        >
          {message}
        </p>
      )}

      {/* 탭 네비게이션 */}
      {data && (
        <div style={styles.tabContainer}>
          <button
            onClick={() => setSelectedMetric('all')}
            style={{
              ...styles.tab,
              backgroundColor: selectedMetric === 'all' ? '#007bff' : '#e9ecef',
              color: selectedMetric === 'all' ? 'white' : '#343a40',
            }}
          >
            전체
          </button>
          <button
            onClick={() => setSelectedMetric('revenue')}
            style={{
              ...styles.tab,
              backgroundColor: selectedMetric === 'revenue' ? '#007bff' : '#e9ecef',
              color: selectedMetric === 'revenue' ? 'white' : '#343a40',
            }}
          >
            매출액
          </button>
          <button
            onClick={() => setSelectedMetric('operating_income')}
            style={{
              ...styles.tab,
              backgroundColor: selectedMetric === 'operating_income' ? '#007bff' : '#e9ecef',
              color: selectedMetric === 'operating_income' ? 'white' : '#343a40',
            }}
          >
            영업이익
          </button>
          <button
            onClick={() => setSelectedMetric('net_income')}
            style={{
              ...styles.tab,
              backgroundColor: selectedMetric === 'net_income' ? '#007bff' : '#e9ecef',
              color: selectedMetric === 'net_income' ? 'white' : '#343a40',
            }}
          >
            순이익
          </button>
        </div>
      )}

      {/* 차트 표시 */}
      {displayData && selectedMetric !== 'all' && (
        <div style={styles.chartContainer}>
          {displayData[selectedMetric] && displayData[selectedMetric]!.length > 0 ? (
            <>
              <Bar
                options={chartOptions}
                data={createChartData(selectedMetric, displayData[selectedMetric])}
              />
              <FinancialTable
                data={displayData[selectedMetric]!}
                metricType={selectedMetric}
                formatValue={formatFinancialValue}
              />
            </>
          ) : (
            <p style={styles.noDataMessage}>해당 메트릭의 데이터가 없습니다.</p>
          )}
        </div>
      )}

      {/* 전체 메트릭 표시 */}
      {displayData && selectedMetric === 'all' && (
        <div style={styles.chartContainer}>
          {['revenue', 'operating_income', 'net_income'].map((metric) => (
            <div key={metric} style={styles.metricSection}>
              {displayData[metric as MetricType] && displayData[metric as MetricType]!.length > 0 ? (
                <>
                  <h3 style={styles.metricTitle}>{getMetricLabel(metric)}</h3>
                  <Bar
                    options={chartOptions}
                    data={createChartData(metric, displayData[metric as MetricType])}
                  />
                  <FinancialTable
                    data={displayData[metric as MetricType]!}
                    metricType={metric}
                    formatValue={formatFinancialValue}
                  />
                </>
              ) : (
                <p style={styles.noDataMessage}>{getMetricLabel(metric)} 데이터가 없습니다.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 재무 테이블 컴포넌트
interface FinancialTableProps {
  data: FinancialDataItem[];
  metricType: string;
  formatValue: (value: number) => string;
}

const FinancialTable: React.FC<FinancialTableProps> = ({ data, metricType, formatValue }) => {
  const getMetricLabel = (metric: string): string => {
    const labels: { [key: string]: string } = {
      revenue: '매출액',
      operating_income: '영업이익',
      net_income: '순이익',
    };
    return labels[metric] || metric;
  };

  return (
    <div style={styles.tableContainer}>
      <h3 style={styles.tableTitle}>{getMetricLabel(metricType)} 상세 내역</h3>
      <table style={styles.table}>
        <thead>
          <tr style={styles.tableHeaderRow}>
            <th style={styles.tableHeader}>연도</th>
            <th style={styles.tableHeader}>분기</th>
            <th style={styles.tableHeader}>{getMetricLabel(metricType)} (원)</th>
            <th style={styles.tableHeader}>{getMetricLabel(metricType)} (단위)</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item, index) => (
            <tr key={index} style={styles.tableRow}>
              <td style={styles.tableCell}>{item.year}</td>
              <td style={styles.tableCell}>{item.quarter}</td>
              <td style={styles.tableCell}>{formatValue(item.value)}</td>
              <td style={styles.tableCell}>{item.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// 스타일 정의
const styles = {
  container: {
    maxWidth: '1000px',
    margin: '0 auto',
    padding: '20px',
    fontFamily: 'Arial, sans-serif',
  },
  heading: {
    fontSize: '2em',
    marginBottom: '10px',
    color: '#333',
  },
  paragraph: {
    fontSize: '1em',
    color: '#666',
    marginBottom: '20px',
  },
  inputGroup: {
    display: 'flex',
    gap: '10px',
    marginBottom: '20px',
  },
  input: {
    flex: 1,
    padding: '10px',
    fontSize: '1em',
    border: '1px solid #ccc',
    borderRadius: '4px',
  },
  button: {
    padding: '10px 20px',
    fontSize: '1em',
    backgroundColor: '#007bff',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  message: {
    marginBottom: '20px',
    padding: '10px',
    borderRadius: '4px',
    backgroundColor: '#f0f0f0',
  },
  popularCompanies: {
    marginBottom: '20px',
    padding: '15px',
    backgroundColor: '#f8f9fa',
    borderRadius: '8px',
  },
  popularLabel: {
    fontSize: '0.95em',
    fontWeight: 'bold' as 'bold',
    marginBottom: '10px',
    color: '#495057',
  },
  buttonGroup: {
    display: 'flex',
    flexWrap: 'wrap' as 'wrap',
    gap: '8px',
  },
  companyButton: {
    padding: '8px 16px',
    borderRadius: '6px',
    border: 'none',
    fontSize: '0.9em',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
    fontWeight: '500',
  },
  tabContainer: {
    display: 'flex',
    gap: '10px',
    marginBottom: '20px',
    borderBottom: '1px solid #ddd',
  },
  tab: {
    padding: '10px 20px',
    fontSize: '0.95em',
    border: 'none',
    borderRadius: '4px 4px 0 0',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
  },
  chartContainer: {
    marginTop: '30px',
  },
  metricSection: {
    marginBottom: '40px',
    padding: '20px',
    backgroundColor: '#f9f9f9',
    borderRadius: '8px',
  },
  metricTitle: {
    fontSize: '1.3em',
    marginBottom: '15px',
    color: '#333',
  },
  tableContainer: {
    marginTop: '20px',
    width: '100%',
  },
  tableTitle: {
    fontSize: '1.1em',
    marginBottom: '10px',
    color: '#333',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse' as 'collapse',
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
  },
  tableCell: {
    padding: '12px',
    textAlign: 'center' as 'center',
    borderRight: '1px solid #dee2e6',
  },
  noDataMessage: {
    marginTop: '20px',
    fontSize: '1.1em',
    color: '#6c757d',
    textAlign: 'center' as 'center',
  },
};
