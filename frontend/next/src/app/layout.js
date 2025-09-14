import Link from 'next/link'
import "./globals.css";
import { Control } from './Control';

export const metadata = {
  title: "Butler.works",
  description: 'This is duplicated version of butler.works',
} 

var date_info = "12345"

export default async function RootLayout({ children }) {
  return (
    <html>
      <body>
        <h1>[Here is layout area]</h1>
        <h2>---Topic list--</h2>
        <Control />
        <h2>-----</h2>
        <h1>------&lt;Start of Children.. (page.js) ({date_info})&gt;-----</h1>
        {children}
        <h1>------&lt;End of Children&gt;-----</h1>
        <h1>[End of layout area]</h1>
      </body>
    </html>
  )
}