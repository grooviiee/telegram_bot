import Link from 'next/link'
import "./globals.css";
import { Control } from './Control';

export const metadata = {
  title: "Butler.works",
  description: 'This is duplicated version of butler.works',
} 

export default async function RootLayout({ children }) {

  const resp = await fetch (`http://localhost:9999/topics`, {next: {revalidate: 10} });
  const topics = await resp.json()

  return (
    <html>
      <body>
        <h1>[Here is layout area]</h1>
        <h2>---Topic list--</h2>
        <ol>
        {topics.map((topic) => {
          return <li key={topic.id}>
            <Link href={`/${topic.id}`}>Go to &#39;{topic.id}&#39;</Link>
          </li>
        })}
        </ol>
        <Control />
        <h2>-----</h2>
        <h1>------&lt;Start of Children&gt;-----</h1>
        {children}
        <h1>------&lt;End of Children&gt;-----</h1>
        <h1>[End of layout area]</h1>
      </body>
    </html>
  )
}