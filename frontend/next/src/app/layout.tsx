import Link from 'next/link'
import "./globals.css";

export const metadata = {
  title: "Butler.works",
  description: 'This is duplicated version of butler.works',
} 

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        <ol>
          <h1><Link href="/homepage">Go to Homepage</Link></h1>
          <h1><Link href="/dividend">Go to Dividend check</Link></h1>
          <h1><Link href="/">Go to Company description</Link></h1>
        </ol>
        {children}
      </body>
    </html>
  )
}