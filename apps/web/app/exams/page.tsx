"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ExamSummary } from "@/lib/api";
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
  // Object.values(graded_results) : { "1": {...}, "2": {...} } 형태의 객체를 값들의 배열로 바꿔서
  // reduce로 합산하기 쉽게 만든다. is_correct인 문제의 points_earned만 더한다(오답은 0으로 취급).
  const earned = Object.values(latest.graded_results).reduce((sum, r) => sum + (r.is_correct ? r.points_earned : 0), 0);
  const pct = latest.total_points_v1 ? (earned / latest.total_points_v1) * 100 : 0;
  return { earned, total: latest.total_points_v1, pass: pct >= 80 };
  // 80점 = 실제 AICE Associate 시험의 합격 기준선을 그대로 반영한 것.
}

export default function ExamsPage() {
  const [exams, setExams] = useState<ExamSummary[] | null>(null);
  // exams는 처음엔 null(아직 못 불러옴), 서버 응답이 오면 배열로 바뀐다. 이렇게 "null이냐
  // 배열이냐"로 로딩 상태를 구분하는 건, 빈 배열([])과 "아직 안 불러온 상태"를 헷갈리지 않게
  // 하려는 흔한 패턴이다(빈 배열이면 "시험이 0개"라는 뜻인데, null이면 "아직 모른다"는 뜻).
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ExamSession[]>([]);

  useEffect(() => {
    // 서버 목록(api)과 로컬 기록(examStorage)을 동시에, 서로 독립적으로 불러온다.
    // 두 호출이 await로 서로를 기다리지 않고 각자 알아서 끝나는 대로 화면을 갱신하므로,
    // 둘 중 하나가 느려도 다른 하나는 먼저 화면에 반영된다.
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
        {/* exams?.map(...) : exams가 아직 null이면(옵셔널 체이닝) map을 아예 호출하지 않고
            undefined를 반환한다 — React는 undefined를 그냥 "아무것도 안 그림"으로 처리한다.
            (참고: 이 페이지는 로딩 중일 때 스피너/안내 문구가 따로 없어서, exams가 null인
             동안은 카드 목록 자리가 그냥 비어 보인다 — study 목록 페이지에는 "불러오는
             중입니다..." 문구가 있는데 이 페이지엔 없는 사소한 비일관성이다.) */}
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
