"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ExamSummary, KichulExamSummary } from "@/lib/api";
import { examStorage, ExamSession } from "@/lib/storage";

/**
 * 이 시험(examId)에 대해 "제출까지 끝낸 세션들" 중 가장 최근 것을 찾아, 카드에 보여줄
 * 요약({earned, total, pass})으로 요약해서 돌려준다. 한 번도 제출한 적 없으면 null.
 *
 * 서버가 아니라 IndexedDB(로컬)에서 기록을 읽어오는 것이므로, "다시 풀기 / 최근 O점" 배지는
 * 지금 이 브라우저에서 응시한 기록만 반영한다(다른 기기 기록은 안 보임 — 로컬 저장 방식의 특징).
 */
function bestResult(sessions: ExamSession[], examId: string) {
  const submitted = sessions.filter((s) => s.exam_id === examId && s.is_submitted);
  if (submitted.length === 0) return null;
  const latest = submitted.sort((a, b) => (a.started_at < b.started_at ? 1 : -1))[0];
  const earned = Object.values(latest.graded_results).reduce((sum, r) => sum + (r.is_correct ? r.points_earned : 0), 0);
  const pct = latest.total_points_v1 ? (earned / latest.total_points_v1) * 100 : 0;
  return { earned, total: latest.total_points_v1, pass: pct >= 80 };
}

export default function ExamsPage() {
  const [tab, setTab] = useState<"mock" | "kichul">("mock");
  const [exams, setExams] = useState<ExamSummary[] | null>(null);
  const [kichulExams, setKichulExams] = useState<KichulExamSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ExamSession[]>([]);

  useEffect(() => {
    api.listExams().then(setExams).catch((e) => setError(String(e)));
    api.listKichulExams().then(setKichulExams).catch(() => {});
    examStorage.listAll().then(setSessions);
  }, []);

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <div className="mb-8">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          ← 홈으로
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-3xl font-extrabold tracking-tight">📝 시험 선택</h1>
          <Link href="/history" className="text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
            히스토리 →
          </Link>
        </div>
        <p className="mt-1.5 text-[15px] text-[var(--muted)]">
          시작하면 타이머가 켜지고, 실제 시험처럼 코드를 직접 작성해 채점됩니다.
        </p>
      </div>

      {/* 탭 전환 */}
      <div className="mb-6 flex gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1">
        <button
          id="tab-mock"
          onClick={() => setTab("mock")}
          className={`flex-1 rounded-lg py-2.5 text-sm font-semibold transition ${
            tab === "mock"
              ? "bg-[var(--brand)] text-white shadow"
              : "text-[var(--muted)] hover:text-[var(--fg)]"
          }`}
        >
          🎯 모의고사 ({exams?.length ?? "…"})
        </button>
        <button
          id="tab-kichul"
          onClick={() => setTab("kichul")}
          className={`flex-1 rounded-lg py-2.5 text-sm font-semibold transition ${
            tab === "kichul"
              ? "bg-[var(--brand)] text-white shadow"
              : "text-[var(--muted)] hover:text-[var(--fg)]"
          }`}
        >
          📄 기출동형 ({kichulExams?.length ?? "…"})
        </button>
      </div>

      {error && <p className="text-[var(--bad)]">{error} (서버가 실행 중인지 확인해주세요)</p>}

      {/* 모의고사 탭 */}
      {tab === "mock" && (
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
      )}

      {/* 기출동형 탭 */}
      {tab === "kichul" && (
        <div className="flex flex-col gap-3">
          <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            💡 <strong>기출동형 문제</strong>는 실제 AICE Associate 시험과 동일한 형식 (10문항, 90분) 으로 구성됩니다.
            모의고사보다 짧고 실전에 가까운 구성으로 최종 점검용으로 활용하세요.
          </div>
          {kichulExams === null && (
            <p className="text-center text-[var(--muted)] py-8">불러오는 중...</p>
          )}
          {kichulExams?.map((e) => {
            const result = bestResult(sessions, e.exam_id);
            const diffColors: Record<string, string> = {
              "하": "text-green-600 bg-green-50 border-green-200",
              "중": "text-yellow-700 bg-yellow-50 border-yellow-200",
              "중상": "text-orange-600 bg-orange-50 border-orange-200",
              "상": "text-red-600 bg-red-50 border-red-200",
            };
            const diffCls = diffColors[e.difficulty] ?? "text-[var(--muted)] bg-[var(--surface)]";
            return (
              <Link
                key={e.exam_id}
                href={`/exam/${encodeURIComponent(e.exam_id)}?type=kichul`}
                className="card flex items-center justify-between p-5 transition hover:-translate-y-0.5 hover:shadow-md"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] font-bold">{e.title}</span>
                    {e.difficulty && (
                      <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${diffCls}`}>
                        난이도 {e.difficulty}
                      </span>
                    )}
                  </div>
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
      )}
    </div>
  );
}
