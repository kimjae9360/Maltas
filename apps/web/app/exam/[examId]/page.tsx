"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ExamDetail, RunResult } from "@/lib/api";
import { ExamSession, examStorage } from "@/lib/storage";
import { ExamProblemCard } from "@/components/ExamProblemCard";
import { OpenBookPanel } from "@/components/OpenBookPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import Link from "next/link";

// 이 파일은 이 프로젝트에서 가장 복잡한 화면이다 — 모의고사를 실제로 "응시"하는 화면이라
// 타이머, 세션 복구("이어서 풀기"), 자동저장, 여러 문제의 코드/채점 상태, 최종 제출까지
// 한 컴포넌트 안에서 전부 관리한다. 아래에 처음 보는 사람이 헷갈리기 쉬운 부분마다
// "왜 이렇게 짰는지"를 설명해뒀다.

/** 초 단위 숫자를 "05:23" 같은 mm:ss 형태로 바꾼다. */
function formatTime(totalSeconds: number) {
  const s = Math.max(0, Math.floor(totalSeconds)); // 음수로 내려가지 않게 방어
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

  // --- 이 화면이 들고 있는 상태들 ---
  const [exam, setExam] = useState<ExamDetail | null>(null);            // 서버에서 받아온 시험 문제 데이터
  const [loadError, setLoadError] = useState(false);                    // 잘못된 exam_id 등으로 못 불러왔을 때
  const [session, setSession] = useState<ExamSession | null>(null);     // IndexedDB에 저장/복원되는 "지금 응시 상태"
  const [resumeCandidate, setResumeCandidate] = useState<ExamSession | null>(null); // "이어서 풀기?" 배너에 쓸 후보
  const [lastRuns, setLastRuns] = useState<Record<number, RunResult>>({}); // 문제별 "가장 최근 실행" 콘솔/그래프 결과
  const [runningNo, setRunningNo] = useState<number | null>(null);      // 지금 채점 중인 문제 번호 (null이면 아무것도 안 돌아가는 중)
  const [answers, setAnswers] = useState<Record<number, string>>({});   // 정답 보기를 누른 문제들의 실제 정답 코드
  const [remaining, setRemaining] = useState(0);                        // 남은 시간(초) — 화면에 표시되는 타이머 숫자
  const [report, setReport] = useState<{ earned: number; total: number; pct: number; pass: boolean; wrong: number[] } | null>(null);
  // report가 null이 아니게 되는 순간 = 제출 완료 화면으로 전환된다.

  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  // 문항 번호 -> 그 문제 카드의 실제 DOM 엘리먼트. "네비게이션에서 3번 클릭하면 3번 카드로
  // 스크롤"하는 기능(scrollTo)에 쓰인다. DOM 엘리먼트 자체는 리렌더링을 유발할 필요가 없는
  // 값이라 useState가 아니라 useRef로 들고 있다.

  // --- "최신 값을 항상 들고 있는 참조"가 필요한 이유 ---
  // setInterval 콜백이나 async 함수(runProblem 등)는 "함수가 정의된 시점"의 state 값을
  // 그대로 기억(클로저)하는 경향이 있다. 예를 들어 setInterval을 세션이 A였을 때 등록해두면,
  // 그 뒤로 세션이 B로 바뀌어도 그 setInterval 콜백 안에서는 여전히 "A"를 참조하게 되는
  // 문제가 생길 수 있다(= "오래된 클로저" 문제). 이를 피하려고, "지금 가장 최신 값"을
  // 매 렌더링마다 ref에 복사해두고, 타이머/비동기 콜백에서는 상태(session) 대신 이
  // ref(sessionRef.current)를 읽도록 한다.
  const sessionRef = useRef<ExamSession | null>(null);
  const remainingRef = useRef<number>(0);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    remainingRef.current = remaining;
  }, [remaining]);
  // React Strict Mode(개발 모드)에서 effect가 두 번 실행되면, find-or-create 로직이 겹쳐 실행되어
  // 방금 우리가 만든 세션을 "이전에 풀던 세션"으로 잘못 인식하는 경쟁 상태가 생길 수 있다.
  // exam_id별로 한 번만 find-or-create를 실행하도록 막는다.
  const initedExamId = useRef<string | null>(null);
  // (참고) Strict Mode는 개발 중에만 컴포넌트의 effect를 일부러 두 번 실행해서 "정리(cleanup)를
  // 제대로 안 하는 버그"를 미리 잡아내라고 만든 React의 안전장치다. 운영 배포(production
  // build)에서는 두 번 실행되지 않지만, 개발 중에 "세션이 이상하게 두 개 생긴다"는 버그를
  // 겪지 않으려면 이렇게 방어적으로 짜두는 게 안전하다.

  // 1) 페이지 진입 시 서버에서 이 시험의 문제 데이터를 가져온다.
  useEffect(() => {
    api.ping(); // Render cold start 방지
    api.getExam(examId).then(setExam).catch(() => setLoadError(true));
  }, [examId]);

  // 2) 문제 데이터를 받아온 뒤(exam이 채워진 뒤), "이어서 풀 세션이 있는지" 확인하고
  //    없으면 새 세션을 만든다.
  useEffect(() => {
    if (!exam) return;
    if (initedExamId.current === exam.exam_id) return;
    initedExamId.current = exam.exam_id;
    examStorage.findUnfinishedSession(exam.exam_id).then((found) => {
      if (found) {
        setResumeCandidate(found); // "이어서 풀까요?" 화면을 띄운다 (사용자가 선택해야 session이 확정됨)
      } else {
        examStorage
          .createSession(exam.exam_id, exam.title, exam.time_limit_minutes, exam.total_points_v1)
          .then(setSession);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exam]);

  // 3) session이 정해지면(새로 만들었든 복구했든), 그 세션의 남은 시간을 타이머 상태에 반영한다.
  useEffect(() => {
    if (session) setRemaining(session.time_limit_minutes * 60 - session.elapsed_seconds);
  }, [session?.sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  /** 세션을 갱신하고(화면 리렌더링용) 동시에 IndexedDB에도 저장하는 공통 헬퍼. */
  const persist = useCallback((s: ExamSession) => {
    setSession(s);
    examStorage.save(s);
  }, []);

  /** 최종 제출 — 지금까지의 채점 결과를 집계해서 점수를 계산하고 "결과 화면"으로 전환한다. */
  const submitExam = useCallback(() => {
    const s = sessionRef.current;
    if (!s || !exam) return;
    const results = exam.problems.map((p) => ({
      no: p.no,
      points: p.points,
      correct: s.graded_results[String(p.no)]?.is_correct ?? false,
      // ?. 와 ?? 를 같이 쓴 이유: 아직 한 번도 채점 안 한 문제는 graded_results에 그 번호의
      // 항목 자체가 없다(undefined) -> ?.is_correct도 undefined -> ?? false로 "미채점=오답" 취급.
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
        // 함수형 업데이트(r => ...)를 쓰는 이유: setInterval 콜백은 effect가 처음 등록될 때의
        // remaining 값을 계속 기억하는 클로저라서, 그냥 "remaining - 1"이라고 쓰면 항상 같은
        // 값에서 1을 빼는 꼴이 된다. r => r - 1 처럼 함수로 넘기면 React가 "그 시점의 진짜
        // 최신 상태"를 인자로 넣어주기 때문에 매초 정확히 1씩 줄어든다.
        const next = r - 1;
        if (next <= 0) {
          clearInterval(interval);
          submitExam(); // 시간 종료 = 자동 제출
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(interval); // effect가 다시 실행되거나 컴포넌트가 사라질 때 반드시 정리
  }, [session?.sessionId, session?.is_submitted, submitExam]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!session || session.is_submitted) return;
    const saveInterval = setInterval(() => {
      const s = sessionRef.current;
      if (!s) return;
      const elapsed = s.time_limit_minutes * 60 - remainingRef.current;
      examStorage.save({ ...s, elapsed_seconds: elapsed });
      // 매초 저장하지 않고 5초마다 저장하는 이유: IndexedDB 쓰기도 공짜가 아니고, 초 단위
      // 정밀도로 저장할 필요는 없다 — 브라우저가 갑자기 꺼져도 최대 5초치 진행상황만
      // 잃는 정도면 "이어서 풀기" 기능의 목적(완전히 처음부터 다시 하지 않아도 됨)엔 충분하다.
    }, 5000);
    return () => clearInterval(saveInterval);
  }, [session?.sessionId, session?.is_submitted]);

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

      // ⚠️ 경쟁 상태(race condition) 방지: 위 await가 끝나길 기다리는 동안, 사용자가 다른
      // 문제에 "검토 표시"(toggleFlag)를 누르는 등 session을 바꿨을 수 있다. await 전에
      // 찍어둔 `s`를 그대로 쓰면 그 사이의 변경사항이 persist에서 통째로 덮어써져 사라진다.
      // 그래서 여기서 sessionRef.current를 다시 읽어 "지금 이 순간의 최신 세션"을 기준으로
      // 병합한다 — s는 위쪽 guard(runningNo 등) 체크에만 쓰고, 실제로 저장할 때는 항상
      // 이 latest를 스프레드해야 안전하다.
      const latest = sessionRef.current;
      if (!latest) return;

      const revealed = latest.revealed_problem_nos.includes(no);
      const entry = revealed
        // 이미 정답을 본 문제는 서버가 실제로 뭐라고 채점했든 무조건 오답(0점) 처리한다 —
        // "정답 보기"의 페널티가 실제로 적용되는 지점이 바로 여기.
        ? { is_correct: false, points_earned: 0, detail: res.detail, note: "정답 보기 사용" }
        : { is_correct: res.is_correct, points_earned: res.points_earned, detail: res.detail };

      persist({ ...latest, graded_results: { ...latest.graded_results, [String(no)]: entry } });
    } catch (err: any) {
      setLastRuns((prev) => ({
        ...prev,
        [no]: { stdout: "", error: `❌ 서버 요청 중 오류가 발생했습니다.\n${err.message}`, is_correct: false, points_earned: 0, detail: "", plots: [] },
      }));
    } finally {
      // try 블록이 성공하든 에러가 나든(예: 네트워크 오류) 반드시 실행되어 "채점 중" 상태를
      // 풀어준다 — 이게 없으면 에러가 났을 때 버튼이 영원히 "실행 중..."에 멈춰있게 된다.
      setRunningNo(null);
    }
  };

  const revealAnswer = async (no: number) => {
    const s = sessionRef.current;
    if (!s || !exam) return;

    // API 통신 없이 프론트엔드에 전달된 base64 인코딩 정답을 즉시 디코딩
    const problem = exam.problems.find((p) => p.no === no);
    if (problem) {
      if (problem.answer_code_b64) {
        try {
          const binString = atob(problem.answer_code_b64);
          const bytes = Uint8Array.from(binString, (m) => m.codePointAt(0)!);
          const decodedAnswer = new TextDecoder().decode(bytes);
          setAnswers((prev) => ({ ...prev, [no]: decodedAnswer }));
        } catch (e) {
          console.error("Base64 decode failed:", e);
          setAnswers((prev) => ({ ...prev, [no]: "정답 데이터를 읽는 중 오류가 발생했습니다." }));
        }
      } else {
        setAnswers((prev) => ({ ...prev, [no]: "아직 서버 배포가 완료되지 않아 정답 데이터를 불러올 수 없습니다. 브라우저를 새로고침(F5) 해주세요." }));
      }
    }

    // runProblem과 동일한 이유로, await 이후에는 s(낡은 스냅샷)가 아니라 sessionRef.current를
    // 다시 읽어서 최신 상태 위에 병합한다. revealAnswer는 runningNo를 건드리지 않아서(버튼이
    // 잠기지 않아서) 이 await가 도는 동안 다른 문제의 채점(runProblem)이 먼저 끝나 세션이
    // 바뀌어 있을 가능성이 오히려 runProblem 쪽보다 더 크다.
    const latest = sessionRef.current;
    if (!latest) return;
    persist({
      ...latest,
      revealed_problem_nos: [...latest.revealed_problem_nos, no],
      graded_results: {
        ...latest.graded_results,
        [String(no)]: { is_correct: false, points_earned: 0, detail: "정답 확인함", note: "정답 보기 사용" },
      },
    });
  };

  const scrollTo = (no: number) => {
    cardRefs.current[no]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // useMemo: session이 바뀔 때만 "작성한 문제 개수"를 다시 세고, 그 외 렌더링에서는
  // 이전 계산값을 재사용한다 (문제 개수가 많아지면 매 렌더링마다 다시 세는 비용이 아까워서).
  const answeredCount = useMemo(
    () => (session ? Object.keys(session.code_by_problem).filter((k) => session.code_by_problem[k].trim()).length : 0),
    [session]
  );

  // --- 아래부터는 "지금 어떤 상태인가"에 따라 완전히 다른 화면을 보여주는 분기들이다.
  // 순서가 중요하다: 에러 -> 로딩 -> 이어서풀기 확인 -> 세션준비중 -> 제출완료 -> (전부 통과하면) 실제 응시 화면.

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
    // 제출까지 끝났으면, 그 아래 실제 응시 화면(사이드바+문제 카드들)은 아예 렌더링하지 않고
    // 결과 화면으로 완전히 대체한다.
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

  // --- 여기부터가 실제 "시험 응시 중" 화면 ---
  return (
    <div className="flex flex-1">
      {/* 좌측 사이드바: 문항 네비게이션 (sm 이상 화면에서만 보임 — hidden sm:flex) */}
      <aside className="sticky top-0 hidden h-screen w-48 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] p-4 sm:flex">
        <Link href="/exams" className="mb-4 text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
          ← 모의고사 목록으로
        </Link>
        <div className="mb-3 text-xs font-bold text-[var(--muted)]">
          작성 {answeredCount}/{exam.problems.length}
        </div>
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-3">
          {exam.problems.map((p) => {
            const result = session.graded_results[String(p.no)];
            const flagged = session.flagged_problem_nos.includes(p.no);
            // 채점 결과에 따라 버튼 색을 정답(초록)/오답(빨강)/미채점(기본)으로 구분해서,
            // 사이드바만 보고도 "어느 문제가 아직 안 풀렸는지" 한눈에 파악할 수 있게 한다.
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
          // mt-auto : flex-col 컨테이너 안에서 이 버튼을 맨 아래로 밀어붙인다(사이드바가
          // 화면보다 짧아도 "제출하기" 버튼이 항상 하단에 고정되도록).
        >
          제출하기
        </button>
      </aside>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:px-6">
        <div className="mb-4 sm:hidden">
          <Link href="/exams" className="text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
            ← 모의고사 목록으로
          </Link>
        </div>
        {/* 모바일: 좌측 사이드바 대신 가로 스크롤 문항 네비게이션 (sm 이상에서는 sm:hidden으로 숨김 —
            데스크톱은 왼쪽 <aside>가 이미 같은 역할을 하므로 중복해서 보여줄 필요가 없다) */}
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
                // shrink-0 : 가로 스크롤 컨테이너 안에서 이 버튼들이 좁아지지 않고 원래
                // 크기를 유지하게 한다(안 하면 flex가 억지로 다 우겨넣으려고 찌그러뜨릴 수 있음).
              >
                {p.no}
              </button>
            );
          })}
        </div>

        {/* 상단 고정 헤더: 시험 제목, 테마/오픈북, 작성 현황, 타이머 */}
        <div className="sticky top-0 z-10 mb-6 flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--surface)]/90 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <Link href="/exams" className="text-sm font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
              ←
            </Link>
            <div className="font-bold">{exam.title}</div>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <OpenBookPanel />
            <span className="text-sm text-[var(--muted)]">{answeredCount}/{exam.problems.length} 작성</span>
            <span className={`font-mono text-lg font-bold ${remaining < 300 ? "text-[var(--bad)]" : ""}`}>
              {formatTime(remaining)}
              {/* 남은 시간이 5분(300초) 미만이면 빨간색으로 바뀌어 시간이 얼마 안 남았음을 강조 */}
            </span>
            <button
              onClick={submitExam}
              className="rounded-lg bg-[var(--bad)] px-3 py-1.5 text-sm font-bold text-white sm:hidden"
              // sm:hidden : 데스크톱은 왼쪽 사이드바에 이미 "제출하기" 버튼이 있으니,
              // 여긴 사이드바가 없는 모바일 화면에서만 보이면 된다.
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
              // disabled는 "이 문제가 채점 중"일 때뿐 아니라 "다른 어떤 문제라도 채점 중"이면
              // 전부 true가 된다(runningNo !== null). 즉 한 번에 한 문제만 채점 요청을 보낼 수
              // 있다 — 서버의 ProcessPoolExecutor(max_workers=1)와도 자연스럽게 맞물리는 제약이다.
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
