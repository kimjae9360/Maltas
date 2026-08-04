"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ExamSummary } from "@/lib/api";
import { examStorage, ExamSession } from "@/lib/storage";

function bestResult(sessions: ExamSession[], examId: string) {
  const submitted = sessions.filter((s) => s.exam_id === examId && s.is_submitted);
  if (submitted.length === 0) return null;
  const latest = submitted.sort((a, b) => (a.started_at < b.started_at ? 1 : -1))[0];
  const earned = Object.values(latest.graded_results).reduce((sum, r) => sum + (r.is_correct ? r.points_earned : 0), 0);
  const pct = latest.total_points_v1 ? (earned / latest.total_points_v1) * 100 : 0;
  return { earned, total: latest.total_points_v1, pass: pct >= 80 };
}

export default function ExamsPage() {
  const [exams, setExams] = useState<ExamSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ExamSession[]>([]);

  useEffect(() => {
    api.listExams().then(setExams).catch((e) => setError(String(e)));
    examStorage.listAll().then(setSessions);
  }, []);

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <div className="mb-8">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          ← 홈으로
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-3xl font-extrabold tracking-tight">📝 모의고사 선택</h1>
          <Link href="/history" className="text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
            히스토리 →
          </Link>
        </div>
        <p className="mt-1.5 text-[15px] text-[var(--muted)]">
          시작하면 타이머가 켜지고, 실제 시험처럼 딥러닝 문제까지 전부 실제 코드로 채점됩니다.
        </p>
      </div>

      {error && <p className="text-[var(--bad)]">{error} (서버가 실행 중인지 확인해주세요)</p>}

      <div className="flex flex-col gap-3">
        {exams?.map((e) => {
          const result = bestResult(sessions, e.exam_id);
          return (
            <Link
              key={e.exam_id}
              href={`/exam/${encodeURIComponent(e.exam_id)}`}
              className="card flex items-center justify-between p-5 transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div>
                <div className="text-[15px] font-bold">{e.title}</div>
                <div className="mt-1 flex gap-2 text-xs text-[var(--muted)]">
                  <span className="pill">{e.problem_count}문항</span>
                  <span className="pill">{e.time_limit_minutes}분</span>
                  <span className="pill">{e.total_points_v1}점 만점</span>
                  {result && (
                    <span className={`pill ${result.pass ? "" : "opacity-60"}`}>
                      최근 {result.earned}/{result.total}점 {result.pass ? "합격" : "미달"}
                    </span>
                  )}
                </div>
              </div>
              <span className="text-[var(--brand)]">{result ? "다시 풀기" : "시작"} →</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
