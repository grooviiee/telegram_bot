import Link from 'next/link'
import "./globals.css";
import { Control } from './Control';

export const metadata = {
  title: "Butler.works",
  description: 'This is duplicated version of butler.works',
} 

var date_info = "12345"

export default async function RootLayout({ children }) {
  const resp = await fetch(`http://localhost:9999/topics`, {next: {revalidate: 0} });
  const topics = await resp.json()

  return (
    <html>
      <body>
        <Control />
        <nav className="p-4">
          <div className="flex items-center space-x-2 bg-gray-100 p-2 rounded-full">
            {topics.map(topic => (
              <Link href={`/${topic.id}`} key={topic.id} className="px-4 py-2 text-sm font-medium text-gray-700 rounded-full hover:bg-white hover:text-black">
                {topic.id}
              </Link> 
            ))}
          </div>
        </nav>

        <h1>------Start of Children (page.js) ({date_info})-----</h1>
        {children}
        <h1>------End of Children-----</h1>
      </body>
    </html>
  )
}