"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { examStorage, studyStorage, ExamSession, StudySession } from "@/lib/storage";

/** ISO 날짜 문자열("2026-08-04T12:34:56.000Z")을 "2026.08.04 21:34" 같은 한국식 표기로 바꾼다. */
function formatDate(iso: string) {
  const d = new Date(iso);
  // padStart(2, "0") : "4" -> "04" 처럼 한 자리 숫자 앞에 0을 채워 항상 두 자리로 맞춘다.
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  // getMonth()는 0(1월)부터 시작하는 JS의 악명 높은 함정이라 +1을 꼭 해줘야 한다.
}

/** exams/page.tsx의 bestResult와 비슷하지만, 세션 하나의 점수를 그대로 계산해주는 버전. */
function examScore(s: ExamSession) {
  const earned = Object.values(s.graded_results).reduce((sum, r) => sum + (r.is_correct ? r.points_earned : 0), 0);
  const pct = s.total_points_v1 ? (earned / s.total_points_v1) * 100 : 0;
  return { earned, pct, pass: pct >= 80 };
}

export default function HistoryPage() {
  const [examSessions, setExamSessions] = useState<ExamSession[] | null>(null);
  const [studySessions, setStudySessions] = useState<StudySession[] | null>(null);

  useEffect(() => {
    // IndexedDB에서 읽어온 뒤, 최신 시작일이 맨 위로 오도록 미리 정렬해서 상태에 저장해둔다
    // (이후 화면에서 다시 정렬할 필요 없게).
    examStorage.listAll().then((all) => setExamSessions(all.sort((a, b) => (a.started_at < b.started_at ? 1 : -1))));
    studyStorage.listAll().then((all) => setStudySessions(all.sort((a, b) => (a.started_at < b.started_at ? 1 : -1))));
  }, []);

  // useMemo: submittedExams를 계산하는 비용 자체는 크지 않지만, examSessions가 바뀔 때만
  // 다시 계산하고 그 외의 리렌더링(예: 다른 상태 변경)에서는 이전 계산 결과를 그대로
  // 재사용하도록 "기억"해두는 훅. 아래 stats도 이 submittedExams가 바뀔 때만 다시 계산된다 —
  // 이렇게 계산을 단계별로 나눠 캐싱해두면 화면이 복잡해져도 불필요한 재계산을 피할 수 있다.
  const submittedExams = useMemo(() => examSessions?.filter((s) => s.is_submitted) ?? [], [examSessions]);

  const stats = useMemo(() => {
    if (!submittedExams.length) return null;
    const scores = submittedExams.map((s) => examScore(s).pct);
    const passCount = scores.filter((p) => p >= 80).length;
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    return { count: submittedExams.length, passCount, avg };
  }, [submittedExams]);

  const completedChapters = useMemo(() => studySessions?.filter((s) => s.is_completed).length ?? 0, [studySessions]);

  // 두 IndexedDB 조회가 "둘 다" 끝나야 "로딩 완료"로 본다 (하나만 끝나면 통계 숫자가
  // 반쯤만 채워진 어중간한 화면이 잠깐 보일 수 있어서, 둘 다 기다렸다가 한 번에 보여준다).
  const loading = examSessions === null || studySessions === null;

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <div className="mb-8">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          ← 홈으로
        </Link>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight">📊 히스토리</h1>
        <p className="mt-1.5 text-[15px] text-[var(--muted)]">이 브라우저에 저장된 모의고사 응시 기록과 학습 진행 상황이에요. 다른 기기/브라우저에서는 별도로 기록돼요.</p>
      </div>

      {loading && <p className="text-[var(--muted)]">불러오는 중...</p>}

      {!loading && (
        <>
          {/* 요약 통계 4칸 — 모바일에서는 2x2, sm 이상에서는 가로 4칸 */}
          <div className="mb-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="card p-4">
              <div className="text-2xl font-extrabold text-[var(--brand)]">{stats?.count ?? 0}</div>
              <div className="text-xs text-[var(--muted)]">모의고사 응시</div>
            </div>
            <div className="card p-4">
              <div className="text-2xl font-extrabold text-[var(--ok)]">{stats?.passCount ?? 0}</div>
              <div className="text-xs text-[var(--muted)]">합격 (80점 이상)</div>
            </div>
            <div className="card p-4">
              <div className="text-2xl font-extrabold">{stats ? `${stats.avg.toFixed(0)}점` : "-"}</div>
              <div className="text-xs text-[var(--muted)]">평균 점수</div>
            </div>
            <div className="card p-4">
              <div className="text-2xl font-extrabold">{completedChapters}</div>
              <div className="text-xs text-[var(--muted)]">완료한 학습 챕터</div>
            </div>
          </div>

          <section className="mb-10">
            <h2 className="mb-3 text-lg font-bold">📝 모의고사 응시 기록</h2>
            {submittedExams.length === 0 ? (
              // 빈 상태(empty state): 기록이 없을 때 그냥 "없음"이라고만 하지 않고,
              // 바로 행동으로 이어지는 버튼(모의고사 보러가기)을 같이 보여준다.
              <div className="card p-6 text-center text-sm text-[var(--muted)]">
                아직 제출한 모의고사가 없어요.
                <div className="mt-3">
                  <Link href="/exams" className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white">
                    모의고사 보러가기 →
                  </Link>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {submittedExams.map((s) => {
                  const { earned, pct, pass } = examScore(s);
                  return (
                    <div key={s.sessionId} className="card flex items-center justify-between p-4">
                      <div>
                        <div className="font-bold">{s.title}</div>
                        <div className="text-xs text-[var(--muted)]">{formatDate(s.started_at)}</div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`text-sm font-bold ${pass ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>
                          {earned}/{s.total_points_v1}점 ({pct.toFixed(0)}%)
                        </span>
                        <span className={`pill ${pass ? "" : "opacity-60"}`}>{pass ? "합격" : "미달"}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-3 text-lg font-bold">📖 학습 진행 기록</h2>
            {!studySessions || studySessions.length === 0 ? (
              <div className="card p-6 text-center text-sm text-[var(--muted)]">
                아직 시작한 학습 챕터가 없어요.
                <div className="mt-3">
                  <Link href="/study?mode=theory" className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white">
                    이론 공부 시작하기 →
                  </Link>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {studySessions.map((s) => (
                  <div key={s.sessionId} className="card flex items-center justify-between p-4">
                    <div>
                      <div className="font-bold">{s.title}</div>
                      <div className="text-xs text-[var(--muted)]">{formatDate(s.started_at)}</div>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-[var(--muted)]">섹션 {s.completed_sections.length}개 완료</span>
                      {s.wrong_units.length > 0 && <span className="pill">복습 {s.wrong_units.length}</span>}
                      {s.is_completed && <span className="pill">완료</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
