"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ExamDetail, RunResult } from "@/lib/api";
import { ExamSession, examStorage } from "@/lib/storage";
import { ExamProblemCard } from "@/components/ExamProblemCard";
import { OpenBookPanel } from "@/components/OpenBookPanel";

function formatTime(totalSeconds: number) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export default function ExamPage() {
  const { examId: rawExamId } = useParams<{ examId: string }>();
  // useParams()가 이미 디코딩된 값을 주는 경로/아직 인코딩된 값을 주는 경로가 둘 다 있을 수 있어
  // 방어적으로 한 번 더 디코딩한다(순수 텍스트는 decodeURIComponent를 걸어도 그대로 반환된다).
  const examId = decodeURIComponent(rawExamId);
  const router = useRouter();

  const [exam, setExam] = useState<ExamDetail | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [session, setSession] = useState<ExamSession | null>(null);
  const [resumeCandidate, setResumeCandidate] = useState<ExamSession | null>(null);
  const [lastRuns, setLastRuns] = useState<Record<number, RunResult>>({});
  const [runningNo, setRunningNo] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [remaining, setRemaining] = useState(0);
  const [report, setReport] = useState<{ earned: number; total: number; pct: number; pass: boolean; wrong: number[] } | null>(null);

  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const sessionRef = useRef<ExamSession | null>(null);
  sessionRef.current = session;
  // React Strict Mode(개발 모드)에서 effect가 두 번 실행되면, find-or-create 로직이 겹쳐 실행되어
  // 방금 우리가 만든 세션을 "이전에 풀던 세션"으로 잘못 인식하는 경쟁 상태가 생길 수 있다.
  // exam_id별로 한 번만 find-or-create를 실행하도록 막는다.
  const initedExamId = useRef<string | null>(null);

  useEffect(() => {
    api.getExam(examId).then(setExam).catch(() => setLoadError(true));
  }, [examId]);

  useEffect(() => {
    if (!exam) return;
    if (initedExamId.current === exam.exam_id) return;
    initedExamId.current = exam.exam_id;
    examStorage.findUnfinishedSession(exam.exam_id).then((found) => {
      if (found) {
        setResumeCandidate(found);
      } else {
        examStorage
          .createSession(exam.exam_id, exam.title, exam.time_limit_minutes, exam.total_points_v1)
          .then(setSession);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exam]);

  useEffect(() => {
    if (session) setRemaining(session.time_limit_minutes * 60 - session.elapsed_seconds);
  }, [session?.sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const persist = useCallback((s: ExamSession) => {
    setSession(s);
    examStorage.save(s);
  }, []);

  const submitExam = useCallback(() => {
    const s = sessionRef.current;
    if (!s || !exam) return;
    const results = exam.problems.map((p) => ({
      no: p.no,
      points: p.points,
      correct: s.graded_results[String(p.no)]?.is_correct ?? false,
    }));
    const earned = results.filter((r) => r.correct).reduce((sum, r) => sum + r.points, 0);
    const pct = exam.total_points_v1 ? (earned / exam.total_points_v1) * 100 : 0;
    const wrong = results.filter((r) => !r.correct).map((r) => r.no);

    const updated = { ...s, is_submitted: true };
    persist(updated);
    setReport({ earned, total: exam.total_points_v1, pct, pass: pct >= 80, wrong });
  }, [exam, persist]);

  // 타이머: 1초마다 로컬에서 감소시키고, 5초마다 세션에 반영/저장한다.
  useEffect(() => {
    if (!session || session.is_submitted) return;
    const interval = setInterval(() => {
      setRemaining((r) => {
        const next = r - 1;
        if (next <= 0) {
          clearInterval(interval);
          submitExam();
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [session?.sessionId, session?.is_submitted, submitExam]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!session || session.is_submitted) return;
    const saveInterval = setInterval(() => {
      const s = sessionRef.current;
      if (!s) return;
      const elapsed = s.time_limit_minutes * 60 - remaining;
      examStorage.save({ ...s, elapsed_seconds: elapsed });
    }, 5000);
    return () => clearInterval(saveInterval);
  }, [session?.sessionId, session?.is_submitted, remaining]);

  const resume = () => {
    if (!resumeCandidate) return;
    setSession(resumeCandidate);
    setResumeCandidate(null);
  };

  const restart = () => {
    if (!exam) return;
    examStorage
      .createSession(exam.exam_id, exam.title, exam.time_limit_minutes, exam.total_points_v1)
      .then(setSession);
    setResumeCandidate(null);
  };

  const getCode = (no: number) => session?.code_by_problem[String(no)] ?? "";

  const setCode = (no: number, code: string) => {
    const s = sessionRef.current;
    if (!s) return;
    persist({ ...s, code_by_problem: { ...s.code_by_problem, [String(no)]: code } });
  };

  const toggleFlag = (no: number) => {
    const s = sessionRef.current;
    if (!s) return;
    const flagged = s.flagged_problem_nos.includes(no)
      ? s.flagged_problem_nos.filter((n) => n !== no)
      : [...s.flagged_problem_nos, no];
    persist({ ...s, flagged_problem_nos: flagged });
  };

  const runProblem = async (no: number) => {
    const s = sessionRef.current;
    if (!s || !exam || runningNo !== null) return;
    setRunningNo(no);
    try {
      const res = await api.runProblem(exam.exam_id, {
        problem_no: no,
        current_code: getCode(no),
        code_by_problem: s.code_by_problem,
      });
      setLastRuns((prev) => ({ ...prev, [no]: res }));

      const revealed = s.revealed_problem_nos.includes(no);
      const entry = revealed
        ? { is_correct: false, points_earned: 0, detail: res.detail, note: "정답 보기 사용" }
        : { is_correct: res.is_correct, points_earned: res.points_earned, detail: res.detail };

      persist({ ...s, graded_results: { ...s.graded_results, [String(no)]: entry } });
    } finally {
      setRunningNo(null);
    }
  };

  const revealAnswer = async (no: number) => {
    const s = sessionRef.current;
    if (!s || !exam) return;
    const res = await api.getAnswer(exam.exam_id, no);
    setAnswers((prev) => ({ ...prev, [no]: res.answer_code }));
    persist({
      ...s,
      revealed_problem_nos: [...s.revealed_problem_nos, no],
      graded_results: {
        ...s.graded_results,
        [String(no)]: { is_correct: false, points_earned: 0, detail: "정답 확인함", note: "정답 보기 사용" },
      },
    });
  };

  const scrollTo = (no: number) => {
    cardRefs.current[no]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const answeredCount = useMemo(
    () => (session ? Object.keys(session.code_by_problem).filter((k) => session.code_by_problem[k].trim()).length : 0),
    [session]
  );

  if (loadError) {
    return (
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="card w-full p-8">
          <div className="mb-2 text-3xl">😕</div>
          <h2 className="text-lg font-bold">모의고사를 찾을 수 없습니다</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">주소가 잘못됐거나 삭제된 모의고사예요.</p>
          <button
            onClick={() => router.push("/exams")}
            className="mt-6 rounded-lg bg-[var(--brand)] px-5 py-2 font-bold text-white"
          >
            모의고사 목록으로
          </button>
        </div>
      </div>
    );
  }

  if (!exam) {
    return <div className="flex flex-1 items-center justify-center text-[var(--muted)]">불러오는 중...</div>;
  }

  if (resumeCandidate) {
    return (
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="card w-full p-6">
          <p className="mb-4">이전에 풀던 답안이 있습니다. 이어서 진행할까요?</p>
          <div className="flex justify-center gap-3">
            <button onClick={resume} className="rounded-lg bg-[var(--brand)] px-4 py-2 font-bold text-white">
              복구
            </button>
            <button onClick={restart} className="rounded-lg border border-[var(--border)] px-4 py-2 font-semibold">
              새로 시작
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!session) {
    return <div className="flex flex-1 items-center justify-center text-[var(--muted)]">세션 준비 중...</div>;
  }

  if (report) {
    return (
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="card w-full p-8">
          <div className="mb-2 text-4xl">{report.pass ? "🎉" : "📚"}</div>
          <h2 className="text-xl font-extrabold">{report.pass ? "합격 기준 통과!" : "합격 기준 미달"}</h2>
          <p className="mt-2 text-3xl font-black text-[var(--brand)]">
            {report.earned} / {report.total}점
          </p>
          <p className="text-sm text-[var(--muted)]">({report.pct.toFixed(1)}%, 합격 기준 80점)</p>
          {report.wrong.length > 0 && (
            <p className="mt-4 text-sm">틀린 문제: {report.wrong.join(", ")}번</p>
          )}
          <button
            onClick={() => router.push("/exams")}
            className="mt-6 rounded-lg bg-[var(--brand)] px-5 py-2 font-bold text-white"
          >
            모의고사 목록으로
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1">
      {/* 좌측 사이드바: 문항 네비게이션 */}
      <aside className="sticky top-0 hidden h-screen w-48 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] p-4 sm:flex">
        <div className="mb-3 text-xs font-bold text-[var(--muted)]">
          작성 {answeredCount}/{exam.problems.length}
        </div>
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-3">
          {exam.problems.map((p) => {
            const result = session.graded_results[String(p.no)];
            const flagged = session.flagged_problem_nos.includes(p.no);
            let cls = "border-[var(--border)] text-[var(--muted)]";
            if (result?.is_correct) cls = "border-[var(--ok)] bg-[var(--ok-tint)] text-[var(--ok)]";
            else if (result) cls = "border-[var(--bad)] bg-[var(--bad-tint)] text-[var(--bad)]";
            return (
              <button
                key={p.no}
                onClick={() => scrollTo(p.no)}
                className={`relative rounded-lg border py-1.5 text-xs font-bold ${cls}`}
              >
                {p.no}
                {flagged && <span className="absolute -right-1 -top-1 text-[10px]">🚩</span>}
              </button>
            );
          })}
        </div>
        <button
          onClick={submitExam}
          className="mt-auto rounded-lg bg-[var(--bad)] py-2 text-sm font-bold text-white"
        >
          제출하기
        </button>
      </aside>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:px-6">
        {/* 모바일: 좌측 사이드바 대신 가로 스크롤 문항 네비게이션 */}
        <div className="sticky top-0 z-10 mb-3 -mx-4 flex gap-2 overflow-x-auto border-b border-[var(--border)] bg-[var(--surface)]/95 px-4 py-2 backdrop-blur sm:hidden">
          {exam.problems.map((p) => {
            const result = session.graded_results[String(p.no)];
            let cls = "border-[var(--border)] text-[var(--muted)]";
            if (result?.is_correct) cls = "border-[var(--ok)] bg-[var(--ok-tint)] text-[var(--ok)]";
            else if (result) cls = "border-[var(--bad)] bg-[var(--bad-tint)] text-[var(--bad)]";
            return (
              <button
                key={p.no}
                onClick={() => scrollTo(p.no)}
                className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-bold ${cls}`}
              >
                {p.no}
              </button>
            );
          })}
        </div>

        <div className="sticky top-0 z-10 mb-6 flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--surface)]/90 px-4 py-3 backdrop-blur">
          <div className="font-bold">{exam.title}</div>
          <div className="flex items-center gap-3">
            <OpenBookPanel />
            <span className="text-sm text-[var(--muted)]">{answeredCount}/{exam.problems.length} 작성</span>
            <span className={`font-mono text-lg font-bold ${remaining < 300 ? "text-[var(--bad)]" : ""}`}>
              {formatTime(remaining)}
            </span>
            <button
              onClick={submitExam}
              className="rounded-lg bg-[var(--bad)] px-3 py-1.5 text-sm font-bold text-white sm:hidden"
            >
              제출
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-5">
          {exam.problems.map((p) => (
            <ExamProblemCard
              key={p.no}
              problem={p}
              code={getCode(p.no)}
              onCodeChange={(c) => setCode(p.no, c)}
              onRun={() => runProblem(p.no)}
              running={runningNo === p.no}
              disabled={runningNo !== null}
              result={session.graded_results[String(p.no)]}
              lastRun={lastRuns[p.no]}
              flagged={session.flagged_problem_nos.includes(p.no)}
              onToggleFlag={() => toggleFlag(p.no)}
              revealed={session.revealed_problem_nos.includes(p.no)}
              onReveal={() => revealAnswer(p.no)}
              answerCode={answers[p.no]}
              cardRef={(el) => {
                cardRefs.current[p.no] = el;
              }}
            />
          ))}
        </div>
      </main>
    </div>
  );
}
