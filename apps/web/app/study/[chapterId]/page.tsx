"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ChapterDetail, StudyRunResult } from "@/lib/api";
import { StudySession, studyStorage } from "@/lib/storage";
import { CodeEditor } from "@/components/CodeEditor";
import { MarkdownView } from "@/components/MarkdownView";
import { PlotViewer } from "@/components/PlotViewer";
import { StudyPracticeCard } from "@/components/StudyPracticeCard";
import { OpenBookPanel } from "@/components/OpenBookPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import Link from "next/link";

// 학습 챕터 화면 — exam/[examId]/page.tsx와 형제뻘 구조지만, "시험"이 아니라 "챕터를 순서대로
// 공부하는 흐름"이라는 차이가 있다: 섹션 단위로 진행하고, 복습 모드가 있고, 타이머가 없다.

/** section_no*100 + practice_no 로 "섹션 몇 번의 몇 번째 문제"를 숫자 하나로 표현한다.
 * 서버(app.py)의 _find_section_practice와 완전히 같은 규칙을 프론트에서도 그대로 써야
 * 서버가 unit 숫자만 보고 어떤 문제인지 되찾을 수 있다. practiceNo를 생략하면(기본값 0)
 * "그 섹션의 예제 코드"를 가리키는 unit이 된다. */
function unitIdx(sectionNo: number, practiceNo = 0) {
  return sectionNo * 100 + practiceNo;
}

export default function StudyChapterPage() {
  const { chapterId: rawChapterId } = useParams<{ chapterId: string }>();
  const chapterId = decodeURIComponent(rawChapterId);
  const router = useRouter();

  const [chapter, setChapter] = useState<ChapterDetail | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [session, setSession] = useState<StudySession | null>(null);
  const [currentSectionNo, setCurrentSectionNo] = useState(1);
  const [reviewMode, setReviewMode] = useState(false);       // true면 "복습 모드" 화면으로 전환
  const [lastRuns, setLastRuns] = useState<Record<number, StudyRunResult>>({}); // unit -> 최근 실행 결과
  const [runningUnit, setRunningUnit] = useState<number | null>(null); // 지금 실행/채점 중인 unit
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [exampleTab, setExampleTab] = useState<"console" | "plot">("console"); // 예제 코드 결과 탭

  // exam 페이지와 동일한 이유(오래된 클로저 방지)로, session의 "최신 값"을 ref에도 복사해둔다.
  const sessionRef = useRef<StudySession | null>(null);
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);
  const initedChapterId = useRef<string | null>(null); // Strict Mode 이중 실행 방지 (exam 페이지와 동일 패턴)

  useEffect(() => {
    api.ping(); // Render cold start 방지: 챕터 데이터 로딩과 동시에 서버 워밍업
    api.getChapter(chapterId).then(setChapter).catch(() => setLoadError(true));
  }, [chapterId]);

  useEffect(() => {
    if (!chapter) return;
    if (initedChapterId.current === chapter.chapter_id) return;
    initedChapterId.current = chapter.chapter_id;
    studyStorage.findLatestSession(chapter.chapter_id).then((found) => {
      if (found && !found.is_completed) {
        // 모의고사와 다르게 여긴 "이어서 할까요?" 확인 화면 없이 바로 이어서 보여준다 —
        // 시험이 아니라 학습이라 시간 압박이 없고, 중간에 끊겨도 부담 없이 재개하면 되기 때문.
        setSession(found);
        setCurrentSectionNo(found.current_section_no);
      } else {
        // 완료된 세션만 있거나 아예 없으면 새 세션을 만든다.
        studyStorage.createSession(chapter.chapter_id, chapter.title).then((s) => {
          setSession(s);
          setCurrentSectionNo(1);
        });
      }
    });
  }, [chapter]);

  const persist = useCallback((s: StudySession) => {
    setSession(s);
    studyStorage.save(s);
  }, []);

  /**
   * 지금까지 "재현 가능한 모든 코드"를 unit -> 코드 문자열 맵으로 만든다. 채점 요청을 보낼 때
   * 서버에 code_by_unit으로 그대로 넘기면, 서버(worker.py의 build_full_code)가 "지금 채점할
   * unit보다 번호가 작은 것들만" 걸러서 순서대로 이어붙여 실행한다.
   *
   * 모든 섹션의 example_code를 넣어두는 게 "혹시 아직 다다르지 않은 섹션 코드까지 새는 거
   * 아닌가?" 싶을 수 있는데, 서버가 어차피 unit 번호로 필터링하므로 안전하다 — 예를 들어
   * 5번 섹션의 예제 코드는 unit 500인데, 2번 섹션의 문제(unit 2xx)를 채점할 때는
   * "500 < 2xx"가 거짓이라 자동으로 제외된다. 그래서 이 맵에 나중 섹션 것까지 미리 다
   * 넣어놔도 실제 채점 결과에는 영향이 없다.
   */
  const codeByUnit = useMemo(() => {
    if (!chapter || !session) return {} as Record<string, string>;
    const map: Record<string, string> = {};
    for (const s of chapter.sections) {
      map[String(unitIdx(s.no))] = s.example_code;
    }
    Object.assign(map, session.practice_code_by_unit); // 사용자가 실제로 작성한 TODO 코드로 덮어씀
    return map;
  }, [chapter, session]);

  const section = chapter?.sections.find((s) => s.no === currentSectionNo);

  /** "예제 실행해보기" 버튼 — 채점 대상이 아니라 그냥 예제 코드를 돌려서 결과를 보여주기만 한다. */
  const runExample = async () => {
    const s = sessionRef.current;
    if (!s || !chapter || !section || runningUnit !== null) return;
    const unit = unitIdx(section.no);
    setRunningUnit(unit);
    try {
      const res = await api.runStudyUnit(chapter.chapter_id, {
        unit,
        current_code: section.example_code,
        code_by_unit: codeByUnit,
      });
      setLastRuns((prev) => ({ ...prev, [unit]: res }));
    } catch (err: any) {
      setLastRuns((prev) => ({
        ...prev,
        [unit]: { stdout: "", error: `❌ 서버 요청 중 오류가 발생했습니다.\n${err.message}`, plots: [] },
      }));
    } finally {
      setRunningUnit(null);
    }
  };

  const getPracticeCode = (unit: number, starter: string) => session?.practice_code_by_unit[String(unit)] ?? starter;
  // 아직 한 번도 손 안 댄 TODO는 starter_code(문제에 딸려오는 기본 뼈대 코드)를 보여준다.

  const setPracticeCode = (unit: number, code: string) => {
    const s = sessionRef.current;
    if (!s) return;
    persist({ ...s, practice_code_by_unit: { ...s.practice_code_by_unit, [String(unit)]: code } });
  };

  /** "채점하기" 버튼 — 서버에 실제로 실행/채점을 요청하고, 성공/실패 이력을 세션에 기록한다. */
  const runPractice = async (unit: number, code: string) => {
    const s = sessionRef.current;
    if (!s || !chapter || runningUnit !== null) return;
    setRunningUnit(unit);
    try {
      const res = await api.runStudyUnit(chapter.chapter_id, { unit, current_code: code, code_by_unit: codeByUnit });
      setLastRuns((prev) => ({ ...prev, [unit]: res }));

      // ⚠️ 경쟁 상태(race condition) 방지: exam/[examId]/page.tsx의 runProblem과 같은 이유로,
      // await 이전에 캡처해둔 `s`가 아니라 지금 이 시점의 최신 세션(sessionRef.current)을
      // 다시 읽어서 그 위에 병합한다. 예를 들어 이 채점이 도는 동안 사용자가 다른 TODO의
      // 정답을 봤다면(revealAnswer), 그 변경이 여기서 지워지지 않아야 한다.
      const latest = sessionRef.current;
      if (!latest) return;

      const prevResult = latest.practice_results_by_unit[String(unit)];
      const isCorrect = !!res.is_correct;
      // !!res.is_correct : res.is_correct가 boolean이 아니라 null일 수도 있는 타입이라
      // (StudyRunResult.is_correct: boolean | null), "!!"로 null/undefined를 확실히
      // false로, true는 true로 정규화한다.
      const nextWrong = isCorrect
        ? latest.wrong_units.filter((u) => u !== unit)   // 이번엔 맞혔으니 복습 목록에서 제거
        : latest.wrong_units.includes(unit)
          ? latest.wrong_units                            // 이미 복습 목록에 있으면 중복 추가 방지
          : [...latest.wrong_units, unit];                // 처음 틀린 거면 복습 목록에 추가

      persist({
        ...latest,
        practice_code_by_unit: { ...latest.practice_code_by_unit, [String(unit)]: code },
        practice_results_by_unit: {
          ...latest.practice_results_by_unit,
          [String(unit)]: {
            is_correct: isCorrect,
            attempts: (prevResult?.attempts ?? 0) + 1,   // 시도 횟수 누적 (처음이면 0+1=1)
            revealed_answer: prevResult?.revealed_answer ?? false, // 이전에 정답을 본 적 있으면 그 기록 유지
          },
        },
        wrong_units: nextWrong,
      });
    } catch (err: any) {
      setLastRuns((prev) => ({
        ...prev,
        [unit]: { stdout: "", error: `❌ 서버 요청 중 오류가 발생했습니다.\n${err.message}`, plots: [] },
      }));
    } finally {
      setRunningUnit(null);
    }
  };

  const revealAnswer = async (unit: number) => {
    const s = sessionRef.current;
    if (!s || !chapter) return;
    const res = await api.getPracticeAnswer(chapter.chapter_id, unit);
    setAnswers((prev) => ({ ...prev, [unit]: res.answer_code }));

    // runPractice와 동일한 이유로 await 이후에는 최신 세션을 다시 읽어서 병합한다.
    // (runExample/runPractice와 달리 이 함수는 runningUnit을 건드리지 않아서 버튼이 안
    // 잠기므로, 이 await가 도는 동안 다른 TODO를 채점해 세션이 바뀌어 있을 가능성이 특히 크다.)
    const latest = sessionRef.current;
    if (!latest) return;
    const prevResult = latest.practice_results_by_unit[String(unit)];
    persist({
      ...latest,
      practice_results_by_unit: {
        ...latest.practice_results_by_unit,
        [String(unit)]: {
          is_correct: prevResult?.is_correct ?? false,
          attempts: prevResult?.attempts ?? 0,
          revealed_answer: true,
        },
      },
      // 정답을 본 문제도 "완전히 못 푼 것"으로 간주해 복습 목록에 넣는다 —
      // sectionIncomplete 가드는 "채점했거나 정답을 본" 것만 확인하지, 정답 유무는 안 따진다.
      wrong_units: latest.wrong_units.includes(unit) ? latest.wrong_units : [...latest.wrong_units, unit],
    });
  };

  /** 섹션 이동(이전/다음/완료) — 지금 섹션을 "완료됨"으로 표시하고 목표 섹션으로 넘어간다. */
  const goToSection = (no: number) => {
    const s = sessionRef.current;
    if (!s || !chapter) return;
    const completed = s.completed_sections.includes(currentSectionNo)
      ? s.completed_sections
      : [...s.completed_sections, currentSectionNo];
    const isLast = no > chapter.sections.length;
    // no가 마지막 섹션 번호를 넘어서면(= "챕터 완료" 버튼을 눌러서 호출된 경우) 챕터 전체를
    // 완료 처리한다. Math.min(no, length)로 current_section_no는 존재하는 섹션 범위 안으로 고정.
    persist({ ...s, current_section_no: Math.min(no, chapter.sections.length), completed_sections: completed, is_completed: isLast || s.is_completed });
    if (!isLast) setCurrentSectionNo(no);
    setReviewMode(false);
  };

  if (loadError) {
    return (
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="card w-full p-8">
          <div className="mb-2 text-3xl">😕</div>
          <h2 className="text-lg font-bold">챕터를 찾을 수 없습니다</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">주소가 잘못됐거나 삭제된 챕터예요.</p>
          <button
            onClick={() => router.push("/study")}
            className="mt-6 rounded-lg bg-[var(--brand)] px-5 py-2 font-bold text-white"
          >
            챕터 목록으로
          </button>
        </div>
      </div>
    );
  }

  if (!chapter) {
    return <div className="flex flex-1 items-center justify-center text-[var(--muted)]">불러오는 중...</div>;
  }
  if (!session || !section) {
    return <div className="flex flex-1 items-center justify-center text-[var(--muted)]">세션 준비 중...</div>;
  }

  // wrong_units(틀렸거나 정답을 본 unit 번호들)를 실제 { section, practice } 객체로 되찾는다.
  // unit 번호만으로는 화면에 뭘 그려야 할지 모르니, 전체 섹션을 순회하며 그 unit에 해당하는
  // practice를 찾아낸다.
  const wrongItems = session.wrong_units
    .map((unit) => {
      for (const s of chapter.sections) {
        const p = s.practices.find((pp) => unitIdx(s.no, pp.no) === unit);
        if (p) return { section: s, practice: p, unit };
      }
      return null;
      // (이론상 wrong_units에는 항상 실제로 존재하는 practice의 unit만 들어가지만, 챕터
      // 데이터가 바뀌는 등의 예외적인 경우를 대비해 못 찾으면 null을 반환하도록 방어했다)
    })
    .filter((x): x is { section: (typeof chapter.sections)[number]; practice: (typeof section.practices)[number]; unit: number } => !!x);
    // filter(...): !!x 로 null을 걸러내면서, 타입 가드 함수로 선언해 TypeScript에게
    // "이 필터를 통과한 배열은 이제 null이 아니다"라는 걸 알려준다(안 하면 여전히
    // null이 섞인 타입으로 취급되어 아래에서 x.section 접근 시 타입 에러가 난다).

  const hasTheory = section.theory_markdown.trim().length > 0;
  const hasExample = section.example_code.trim().length > 0;
  // 채점하기(정답 보기 포함)를 한 번도 안 한 TODO가 남아있으면 다음 섹션으로 못 넘어가게 막는다.
  const sectionIncomplete = section.practices.some(
    (p) => !session.practice_results_by_unit[String(unitIdx(section.no, p.no))]
  );

  return (
    <div className="flex flex-1">
      {/* 좌측 사이드바: 섹션 목록 (sm 이상에서만) */}
      <aside className="sticky top-0 hidden h-screen w-52 shrink-0 flex-col gap-1 overflow-y-auto border-r border-[var(--border)] bg-[var(--surface)] p-4 sm:flex">
        <div className="mb-3 flex flex-col gap-1">
          <Link href="/" className="flex items-center gap-1 rounded-lg bg-[var(--brand-tint)] px-3 py-1.5 text-xs font-bold text-[var(--brand)] hover:bg-[var(--brand)] hover:text-white transition">
            🏠 홈으로
          </Link>
          <Link href="/study" className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-semibold text-[var(--muted)] hover:bg-[var(--brand-tint)] hover:text-[var(--brand)] transition">
            ← 챕터 목록
          </Link>
        </div>
        <div className="mb-2 text-xs font-bold text-[var(--muted)]">{chapter.title}</div>
        {chapter.sections.map((s) => {
          const done = session.completed_sections.includes(s.no);
          const active = !reviewMode && s.no === currentSectionNo;
          return (
            <button
              key={s.no}
              onClick={() => {
                setReviewMode(false);
                setCurrentSectionNo(s.no);
                // 여기서는 goToSection을 안 쓰고 currentSectionNo만 직접 바꾼다는 점에 주의 —
                // 사이드바에서 섹션을 자유롭게 "미리보기"처럼 건너뛰어 봐도, goToSection이
                // 하는 "이전 섹션을 완료 처리"는 하지 않는다(완료 처리는 이전/다음 버튼을
                // 눌러 순서대로 진행할 때만 일어난다).
              }}
              className={`rounded-lg px-3 py-2 text-left text-xs font-semibold ${
                active
                  ? "bg-[var(--brand)] text-white"
                  : done
                    ? "bg-[var(--ok-tint)] text-[var(--ok)]"
                    : "text-[var(--muted)] hover:bg-[var(--brand-tint)]"
              }`}
            >
              {s.no}. {s.title}
            </button>
          );
        })}
        <button
          onClick={() => setReviewMode(true)}
          disabled={session.wrong_units.length === 0}
          className={`mt-auto rounded-lg py-2 text-xs font-bold ${
            reviewMode ? "bg-[var(--warn)] text-white" : "border border-[var(--warn)] text-[var(--warn)]"
          } disabled:cursor-not-allowed disabled:opacity-40`}
        >
          📝 복습 모드 ({session.wrong_units.length})
        </button>
      </aside>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:px-6">
        <div className="mb-3 flex items-center gap-2 sm:hidden">
          <Link href="/" className="rounded-lg bg-[var(--brand-tint)] px-3 py-1.5 text-xs font-bold text-[var(--brand)] hover:bg-[var(--brand)] hover:text-white transition">
            🏠 홈
          </Link>
          <Link href="/study" className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)] transition">
            ← 챕터 목록
          </Link>
        </div>
        {/* 모바일: 좌측 사이드바 대신 가로 스크롤 섹션 네비게이션 */}
        <div className="sticky top-0 z-10 mb-3 -mx-4 flex items-center gap-2 overflow-x-auto border-b border-[var(--border)] bg-[var(--surface)]/95 px-4 py-2 backdrop-blur sm:hidden">
          {chapter.sections.map((s) => (
            <button
              key={s.no}
              onClick={() => {
                setReviewMode(false);
                setCurrentSectionNo(s.no);
              }}
              className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-bold ${
                !reviewMode && s.no === currentSectionNo
                  ? "border-[var(--brand)] bg-[var(--brand)] text-white"
                  : session.completed_sections.includes(s.no)
                    ? "border-[var(--ok)] bg-[var(--ok-tint)] text-[var(--ok)]"
                    : "border-[var(--border)] text-[var(--muted)]"
              }`}
            >
              {s.no}
            </button>
          ))}
          <button
            onClick={() => setReviewMode(true)}
            disabled={session.wrong_units.length === 0}
            className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-bold ${
              reviewMode ? "border-[var(--warn)] bg-[var(--warn)] text-white" : "border-[var(--warn)] text-[var(--warn)]"
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            📝 {session.wrong_units.length}
          </button>
        </div>

        {reviewMode ? (
          // --- 복습 모드: 지금까지 틀렸거나 정답을 본 문제들만 모아서 다시 풀어보는 화면 ---
          <div className="flex flex-col gap-5">
            <h2 className="text-xl font-extrabold">📝 복습 모드 — 못 풀었거나 정답을 본 문제</h2>
            {wrongItems.length === 0 && <p className="text-[var(--muted)]">복습할 문제가 없어요. 🎉</p>}
            {wrongItems.map(({ practice, unit }) => {
              // 복습 모드에서는 "과거에 정답을 봤던 기록(session의 revealed_answer)" 때문에
              // 시작하자마자 "정답 확인함"이 뜨는 것을 막기 위해,
              // 이번 복습 세션에서 새로 정답을 요청해 answers 객체에 들어있는 경우에만 revealed 처리한다.
              const isRevealedNow = !!answers[unit];
              return (
                <StudyPracticeCard
                  key={unit}
                  practice={practice}
                  code={getPracticeCode(unit, practice.starter_code)}
                  onCodeChange={(c) => setPracticeCode(unit, c)}
                  onRun={() => runPractice(unit, getPracticeCode(unit, practice.starter_code))}
                  running={runningUnit === unit}
                  disabled={runningUnit !== null}
                  result={session.practice_results_by_unit[String(unit)]}
                  lastRun={lastRuns[unit]}
                  revealed={isRevealedNow}
                  onReveal={() => revealAnswer(unit)}
                  answerCode={answers[unit]}
                />
              );
            })}
          </div>
        ) : (
          // --- 평소 모드: 지금 섹션의 이론 -> 개념표 -> 예제 -> TODO들을 순서대로 보여준다 ---
          <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Link href="/" className="rounded-lg bg-[var(--brand-tint)] px-3 py-1.5 text-xs font-bold text-[var(--brand)] hover:bg-[var(--brand)] hover:text-white transition">
                  🏠 홈으로
                </Link>
                <Link href="/study" className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)] transition">
                  ← 챕터 목록
                </Link>
              </div>
              <div className="flex items-center gap-3">
                <ThemeToggle />
                <OpenBookPanel />
              </div>
            </div>
            <h1 className="text-2xl font-extrabold">
              {section.no}. {section.title}
            </h1>

            {hasTheory && (
              <div className="card p-5">
                <MarkdownView>{section.theory_markdown}</MarkdownView>
                {section.concept_table_markdown && (
                  <div className="mt-3">
                    <MarkdownView>{section.concept_table_markdown}</MarkdownView>
                  </div>
                )}
              </div>
            )}

            {hasExample && (
            <div className="card p-5">
              <div className="mb-2 flex items-center justify-between">
                <span className="pill">예제 코드</span>
                <button
                  onClick={runExample}
                  disabled={runningUnit !== null}
                  className="rounded-lg bg-[var(--brand)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50"
                >
                  {runningUnit === unitIdx(section.no) ? "실행 중..." : "▶ 예제 실행해보기"}
                </button>
              </div>
              <CodeEditor value={section.example_code} onChange={() => {}} readOnly minHeight="120px" />
              {/* onChange={() => {}} : readOnly라 실제로 값이 안 바뀌지만, CodeEditor 컴포넌트가
                  onChange을 필수(required) prop으로 요구하기 때문에 "아무것도 안 하는 함수"라도
                  넘겨줘야 한다. */}
              <div className="mt-3 rounded-lg border border-[var(--border)]">
                <div className="flex border-b border-[var(--border)] text-xs font-semibold">
                  {(["console", "plot"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setExampleTab(t)}
                      className={`px-3 py-2 ${exampleTab === t ? "border-b-2 border-[var(--brand)] text-[var(--brand)]" : "text-[var(--muted)]"}`}
                    >
                      {t === "console" ? "콘솔 출력" : "시각화"}
                    </button>
                  ))}
                </div>
                <div className="min-h-[50px] max-h-72 overflow-auto">
                  {exampleTab === "console" && (
                    <pre className="whitespace-pre-wrap p-3 font-mono text-xs">
                      {lastRuns[unitIdx(section.no)]
                        ? lastRuns[unitIdx(section.no)].stdout || "(출력 없음 — 정상 실행됐어요)"
                        : "실행해보면 결과가 여기에 표시됩니다."}
                    </pre>
                  )}
                  {exampleTab === "plot" && <PlotViewer plots={lastRuns[unitIdx(section.no)]?.plots ?? []} />}
                </div>
              </div>
            </div>
            )}

            {section.practices.map((p) => {
              const unit = unitIdx(section.no, p.no);
              return (
                <StudyPracticeCard
                  key={unit}
                  practice={p}
                  code={getPracticeCode(unit, p.starter_code)}
                  onCodeChange={(c) => setPracticeCode(unit, c)}
                  onRun={() => runPractice(unit, getPracticeCode(unit, p.starter_code))}
                  running={runningUnit === unit}
                  disabled={runningUnit !== null}
                  result={session.practice_results_by_unit[String(unit)]}
                  lastRun={lastRuns[unit]}
                  revealed={session.practice_results_by_unit[String(unit)]?.revealed_answer ?? false}
                  onReveal={() => revealAnswer(unit)}
                  answerCode={answers[unit]}
                />
              );
            })}

            {sectionIncomplete && section.practices.length > 0 && (
              <p className="text-right text-xs text-[var(--warn)]">
                ⚠️ 이 섹션의 TODO를 전부 채점하거나(또는 힌트/정답 보기) 확인해야 다음으로 넘어갈 수 있어요.
              </p>
            )}
            <div className="flex justify-between border-t border-[var(--border)] pt-4">
              <button
                onClick={() => goToSection(currentSectionNo - 1)}
                disabled={currentSectionNo <= 1}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-semibold disabled:opacity-40"
              >
                ← 이전 섹션
              </button>
              {currentSectionNo < chapter.sections.length ? (
                <button
                  onClick={() => goToSection(currentSectionNo + 1)}
                  disabled={sectionIncomplete}
                  className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  다음 섹션 →
                </button>
              ) : (
                <button
                  onClick={() => {
                    goToSection(chapter.sections.length + 1); // 마지막 섹션 다음 번호 -> "완료" 신호
                    if (session.wrong_units.length > 0) {
                      setReviewMode(true); // 틀린 문제가 있으면 바로 복습 모드로
                    } else {
                      router.push("/study"); // 다 맞았으면 챕터 목록으로
                    }
                  }}
                  disabled={sectionIncomplete}
                  className="rounded-lg bg-[var(--ok)] px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  🎉 챕터 완료
                </button>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
