import "./globals.css";
import { InteractiveLayout } from './InteractiveLayout';

export const metadata = {
  title: "Butler.works",
  description: 'This is duplicated version of butler.works',
}

export default function RootLayout() {
  return (
    <html>
      <body>
        <InteractiveLayout />
      </body>
    </html>
  );
}
