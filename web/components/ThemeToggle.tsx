"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="h-8 w-16" />; // placeholder
  }

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)]"
      title="테마 변경"
    >
      {theme === "dark" ? "🌞 라이트" : "🌙 다크"}
    </button>
  );
}
