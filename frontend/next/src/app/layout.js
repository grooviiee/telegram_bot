import "./globals.css";
import { InteractiveLayout } from './InteractiveLayout';

export const metadata = {
  title: "Butler.works",
  description: 'This is duplicated version of butler.works',
}

export default async function RootLayout({ children }) {
  let menu_items = [];
  let error = null;
  try {
    const resp = await fetch(`http://localhost:9999/menu`, {next: {revalidate: 0} });
    if (!resp.ok) {
      throw new Error('Failed to fetch menu_items');
    }
    menu_items = await resp.json();
  } catch (e) {
    error = e.message;
    console.error(e);
  }

  return (
    <html>
      <body>
        <div className="layout-container">
          <InteractiveLayout menu_items={menu_items} error={error} />
        </div>
      </body>
    </html>
  )
}