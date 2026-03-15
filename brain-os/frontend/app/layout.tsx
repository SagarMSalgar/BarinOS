import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'BrainOS - Decision Support Hub',
  description: 'Live, accurate, cited AI from your business data.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="light">
      <body className="min-h-screen theme-page-bg text-slate-800 antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
