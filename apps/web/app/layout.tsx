import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AICE Simulator",
  description: "AICE Associate 이론 공부 · 실무 연습 · 모의고사",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      suppressHydrationWarning
    >
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-full flex flex-col antialiased`}>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
          <header className="sticky top-0 z-50 flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface)]/95 px-4 py-2.5 backdrop-blur">
            <Link
              href="/"
              className="flex items-center gap-2 text-sm font-extrabold text-[var(--brand)] hover:opacity-80"
            >
              🏠 AICE Simulator
            </Link>
            <nav className="flex items-center gap-4 text-xs font-semibold text-[var(--muted)]">
              <Link href="/study" className="hover:text-[var(--brand)]">📖 학습</Link>
              <Link href="/exams" className="hover:text-[var(--brand)]">📝 모의고사</Link>
              <Link href="/history" className="hover:text-[var(--brand)]">📊 히스토리</Link>
            </nav>
          </header>
          <div className="flex flex-1 flex-col">
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
