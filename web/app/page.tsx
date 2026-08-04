import Link from "next/link";

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

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="mb-10 text-center">
        <span className="pill mb-3">AICE Associate</span>
        <h1 className="text-3xl font-extrabold tracking-tight">AICE Simulator</h1>
        <p className="mt-2 text-[var(--muted)]">이론부터 모의고사까지, 웹에서 바로 실행하며 준비하세요.</p>
      </div>
      <div className="grid w-full max-w-4xl grid-cols-1 gap-5 sm:grid-cols-3">
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
