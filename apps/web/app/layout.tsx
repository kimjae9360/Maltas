import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import Link from "next/link";
import { ServerPinger } from "@/components/ServerPinger";
import "./globals.css";
// 이 파일은 Next.js App Router의 "루트 레이아웃" — app/ 폴더 아래 모든 페이지가 공통으로
// 이 안에 감싸져서 렌더링된다. 여기 적어둔 <header>(상단 네비게이션 바)는 페이지를 이동해도
// 매번 다시 그려지지 않고 계속 유지된다. globals.css를 여기서 한 번만 import하는 것도
// "앱 전체에 적용되는 스타일은 루트 레이아웃에서 불러온다"는 Next.js의 규칙을 따른 것.

// next/font/google: Google 폰트를 빌드 시점에 미리 다운로드해서 자체 호스팅하는 Next.js 기능.
// 이렇게 하면 브라우저가 매번 Google 서버에 폰트를 요청하지 않아도 되고(속도·개인정보 이점),
// variable 옵션으로 만든 이름(--font-geist-sans)은 CSS 변수로 등록되어 body의 className에서
// 바로 참조할 수 있다.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Next.js가 이 값을 읽어서 <head>의 <title>, <meta name="description"> 등을 자동으로 채워준다.
// 검색엔진/브라우저 탭 제목에 쓰이는 메타데이터.
export const metadata: Metadata = {
  title: "AICE Simulator",
  description: "AICE Associate 이론 공부 · 실무 연습 · 모의고사",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // children = 지금 방문한 페이지의 실제 내용 (예: app/exams/page.tsx의 결과물).
  // Next.js가 URL에 맞는 page.tsx를 렌더링한 결과를 이 자리에 자동으로 끼워넣어 준다.
  return (
    <html
      lang="ko"
      suppressHydrationWarning
      // suppressHydrationWarning: next-themes가 브라우저에서 <html> 태그에 class="dark"를
      // 붙였다 뗐다 하기 때문에, 서버가 그린 초기 HTML과 브라우저에서 최종적으로 보이는
      // HTML의 class 속성이 다를 수 있다. 이건 의도된 동작이라, React가 그 차이를 "버그"로
      // 오인해 콘솔에 경고를 띄우지 않도록 이 속성으로 명시적으로 막아둔 것.
    >
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-full flex flex-col antialiased`}>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
          {/* attribute="class": 테마를 <html class="dark">처럼 클래스로 표현하겠다는 설정
              (다른 방식으로 data-theme 속성을 쓸 수도 있지만, Tailwind의 dark: 접두사가
              기본적으로 class 방식을 기대하므로 이렇게 맞췄다).
              defaultTheme="light": 브라우저에 저장된 값이 없는 첫 방문자는 라이트로 시작.
              enableSystem={false}: OS가 다크 모드여도 "시스템 설정을 따라가지 않고" 무조건
              라이트로 시작하게 강제 — 사용자가 화이트 테마를 기본으로 원했기 때문. 다만 이후
              ThemeToggle 버튼으로 사용자가 직접 다크로 바꾸는 것 자체는 막지 않는다. */}
          <ServerPinger />
          <header className="sticky top-0 z-50 flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface)]/95 px-4 py-2.5 backdrop-blur">
            {/* sticky top-0: 페이지를 아래로 스크롤해도 이 헤더는 화면 맨 위에 계속 붙어있는다.
                bg-.../95 + backdrop-blur: 배경을 95% 불투명 + 블러 처리해서, 헤더 뒤로 콘텐츠가
                스크롤될 때 살짝 비치면서도 글자는 잘 읽히는 "젖빛 유리" 느낌을 준다. */}
            <Link
              href="/"
              className="flex items-center gap-2 text-sm font-extrabold text-[var(--brand)] hover:opacity-80"
            >
              🏠 AICE Simulator
            </Link>
            <nav className="flex items-center gap-4 text-xs font-semibold text-[var(--muted)]">
              {/* next/link의 <Link>는 일반 <a> 태그와 달리 페이지 전체를 새로고침하지 않고
                  필요한 부분만 다시 그리는 클라이언트 사이드 네비게이션을 해준다(SPA처럼 빠른 전환). */}
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
