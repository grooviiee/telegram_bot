import "./globals.css";

export const metadata = {
  title: "Butler.works",
  description: 'DART 공시 기반 기업 재무 · 사업 분석과 AI 투자 상담',
}

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>
        {children}
      </body>
    </html>
  );
}
