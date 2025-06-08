// "use client"
import Link from 'next/link'
import "./globals.css";
import { useEffect, useState } from 'react';

// export const metadata = {
//   title: "Butler.works",
//   description: 'This is duplicated version of butler.works',
// } 

export default async function RootLayout({ children }) {
  // const [topics, setTopics] = useState([]);
  // useEffect(() => {
  //  fetch('http://localhost:9999/topics')
  //  .then(resp=>resp.json())
  //  .then(result=>{setTopics(result)});
  //  }, []);
  const resp = await fetch ("localhost:9999/topics")
  const topics = await resp.json()

  return (
    <html>
      <body>
        <ol>
        {topics.map((topic) => {
          return <li key={topic.id}>
            <Link href={`/${topic.id}`}>{topic.title}</Link>
          </li>
        })}
          <h1><Link href="/homepage">Go to Homepage</Link></h1>
          <h1><Link href="/dividend">Go to Dividend check</Link></h1>
          <h1><Link href="/">Go to Company description</Link></h1>
        </ol>
        {children}
      </body>
    </html>
  )
}