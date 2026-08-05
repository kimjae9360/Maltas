"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
// next-themes: 라이트/다크 테마 전환을 처리해주는 라이브러리. 실제로 하는 일은 <html> 태그에
// class="dark"를 붙였다 뗐다 하고, 선택한 테마를 localStorage에 기억해두는 것 — 그 값을
// globals.css의 `.dark { ... }` 규칙이 읽어서 색상 변수들을 바꿔치기한다 (apps/web/app/layout.tsx의
// <ThemeProvider>가 이 라이브러리를 최상단에서 감싸고 있어야 useTheme()이 동작한다).

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line
    setMounted(true);
  }, []);
  // 왜 굳이 mounted 상태를 따로 둘까? Next.js는 서버에서 먼저 HTML을 그려놓고(SSR) 브라우저에서
  // "하이드레이션"(그 HTML에 이벤트 리스너 등을 붙여 실제로 살아있는 컴포넌트로 만드는 과정)을
  // 한다. 그런데 서버는 사용자가 이전에 로컬에 저장해둔 테마 값을 알 수 없어서, 서버가 그린
  // 첫 화면과 브라우저가 실제로 아는 테마가 서로 다를 수 있다(예: 서버는 "라이트"라고 그렸는데
  // 브라우저엔 "다크"가 저장돼 있는 경우). 이 상태로 바로 theme 값을 읽어서 렌더링하면 "서버가
  // 그린 것과 클라이언트가 그리려는 것이 다르다"는 하이드레이션 경고/깜빡임이 생긴다. 그래서
  // 처음 렌더링(mounted === false)에는 테마와 무관한 빈 자리표시자만 보여주고, 브라우저에서
  // useEffect가 실행된 뒤(= 하이드레이션이 끝난 뒤)에야 실제 버튼을 그리는 안전한 패턴이다.
  if (!mounted) {
    return <div className="h-8 w-16" />; // placeholder — 버튼과 비슷한 크기의 빈 공간만 차지해서 레이아웃이 안 흔들리게
  }

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="shrink-0 whitespace-nowrap rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)]"
      // whitespace-nowrap + shrink-0: 좁은 화면에서 이 버튼이 들어있는 flex 줄이 비좁아지면,
      // 브라우저가 이 버튼 "안의 글자"를 줄바꿈해서 억지로 욱여넣으려는 경우가 있었다
      // ("🌙"과 "다크"가 따로 줄바뀜) — 대신 버튼은 항상 한 줄을 유지하게 강제하고,
      // 자리가 부족하면 (부모의 flex-wrap이 있는 경우) 버튼째로 다음 줄로 넘어가게 한다.
      title="테마 변경"
    >
      {theme === "dark" ? "🌞 라이트" : "🌙 다크"}
    </button>
  );
}
