export interface FinancialDataItem {
  year: number;
  quarter: string;
  value: number;
  unit: string;
}

export interface FinancialMetricsResponse {
  company_name: string;
  metrics: {
    revenue?: FinancialDataItem[];
    operating_income?: FinancialDataItem[];
    net_income?: FinancialDataItem[];
  };
}

export type MetricType = 'all' | 'revenue' | 'operating_income' | 'net_income';
