"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, ChapterSummary } from "@/lib/api";
import { studyStorage, StudySession } from "@/lib/storage";

function StudyPageInner() {
  const params = useSearchParams();
  const mode = params.get("mode") === "practice" ? "practice" : "theory";

  const [chapters, setChapters] = useState<ChapterSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<StudySession[]>([]);

  useEffect(() => {
    api.listChapters().then(setChapters).catch((e) => setError(String(e)));
    studyStorage.listAll().then(setSessions);
  }, []);

  const filtered = chapters?.filter((c) => c.is_practice_only === (mode === "practice"));

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <div className="mb-8">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          ← 홈으로
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-3xl font-extrabold tracking-tight">
            {mode === "theory" ? "📖 이론 공부 — 챕터 선택" : "💻 실무 연습 — 챕터 선택"}
          </h1>
          <Link href="/history" className="text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
            히스토리 →
          </Link>
        </div>
        <p className="mt-1.5 text-[15px] text-[var(--muted)]">
          {mode === "theory"
            ? "개념 설명 → 핵심 정리 → 예제 → TODO 문제 순서로 진행돼요. 막히면 언제든 힌트/정답을 볼 수 있어요."
            : "이론 설명 없이 TODO 문제만 밀도 있게 이어집니다. 손에 익히는 반복 연습용이에요."}
        </p>
      </div>

      {error && <p className="text-[var(--bad)]">{error} (서버가 실행 중인지 확인해주세요)</p>}
      
      {!error && chapters === null && (
        <div className="mt-8 flex justify-center">
          <p className="text-[var(--muted)]">데이터를 불러오는 중입니다...</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {filtered?.map((c) => {
          const session = sessions.find((s) => s.chapter_id === c.chapter_id);
          return (
            <Link
              key={c.chapter_id}
              href={`/study/${encodeURIComponent(c.chapter_id)}`}
              className="card flex flex-col gap-1 p-5 transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="text-[15px] font-bold">{c.title}</div>
              <div className="flex flex-wrap gap-2 text-xs text-[var(--muted)]">
                <span className="pill">{c.section_count}섹션</span>
                <span className="pill">TODO {c.practice_count}개</span>
                {session && (
                  <span className="pill">
                    {session.is_completed ? "완료" : `진행중 ${session.completed_sections.length}/${c.section_count}`}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default function StudyPage() {
  return (
    <Suspense>
      <StudyPageInner />
    </Suspense>
  );
}
