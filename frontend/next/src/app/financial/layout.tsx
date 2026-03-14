import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "재무 정보 분석",
  description: "기업의 분기별 재무 정보(매출액, 영업이익, 순이익)를 분석합니다.",
};

export default function FinancialLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
