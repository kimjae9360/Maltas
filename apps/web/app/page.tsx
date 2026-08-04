"use client";

import Link from "next/link";
import { useEffect } from "react";
import { api } from "@/lib/api";

// 홈 화면(주소 "/")에 보여줄 3개 카드의 데이터. 컴포넌트 함수 바깥에 둬서 렌더링마다
// 새로 만들어지지 않게 한 건 OpenBookPanel의 LINKS와 같은 이유.
const cards = [
  {
    href: "/study?mode=theory",
    emoji: "📖",
    title: "이론 공부",
    desc: "개념 설명과 핵심 정리를 읽고, 예제를 직접 실행하며 익혀요.",
  },
  {
    href: "/study?mode=practice",
    emoji: "💻",
    title: "실무 연습",
    desc: "이론 없이 실전 문제만 빠르게 반복해서 손에 익혀요. 힌트·정답 확인 가능.",
  },
  {
    href: "/exams",
    emoji: "📝",
    title: "모의고사",
    desc: "실제 시험처럼 타이머를 켜고 딥러닝까지 전부 실제 코드로 응시해요.",
  },
];
// "이론 공부"와 "실무 연습"이 둘 다 /study로 가면서 쿼리스트링(?mode=...)만 다른 이유:
// 두 모드가 사실상 같은 화면 컴포넌트(app/study/page.tsx)를 쓰고, "이론 설명을 보여줄지
// 말지"만 다르기 때문이다. 페이지 자체를 두 벌 만들지 않고 쿼리 파라미터 하나로 분기한다.

export default function Home() {
  // 홈 진입 즉시 백엔드 서버를 워밍업 — Render free-tier cold start 방지
  // useEffect(..., []) : 두 번째 인자로 빈 배열을 주면 "이 컴포넌트가 처음 화면에 나타났을 때
  // 딱 한 번만" 실행된다는 뜻. 사용자가 실제로 문제 풀기 버튼을 누르기 전에 미리 서버를 깨워
  // 두려는 목적이라, 렌더링마다 반복 호출할 필요 없이 최초 1회면 충분하다.
  useEffect(() => {
    api.ping();
  }, []);

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="mb-10 text-center">
        <span className="pill mb-3">AICE Associate</span>
        <h1 className="text-3xl font-extrabold tracking-tight">AICE Simulator</h1>
        <p className="mt-2 text-[var(--muted)]">이론부터 모의고사까지, 웹에서 바로 실행하며 준비하세요.</p>
      </div>
      <div className="grid w-full max-w-4xl grid-cols-1 gap-5 sm:grid-cols-3">
        {/* grid-cols-1 sm:grid-cols-3 : 모바일 화면(좁은 너비)에서는 카드를 세로로 1열로,
            sm 이상(태블릿/데스크톱)에서는 가로로 3열로 배치 — Tailwind의 반응형 접두사 패턴. */}
        {cards.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="card flex flex-col gap-2 p-6 transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="text-3xl">{c.emoji}</div>
            <div className="text-lg font-bold">{c.title}</div>
            <div className="text-sm text-[var(--muted)]">{c.desc}</div>
          </Link>
        ))}
      </div>
      <Link href="/history" className="mt-6 text-sm font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
        📊 내 히스토리 보기 →
      </Link>
    </div>
  );
}
