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
  const [reviewMode, setReviewMode] = useState(false);
  const [lastRuns, setLastRuns] = useState<Record<number, StudyRunResult>>({});
  const [runningUnit, setRunningUnit] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [exampleTab, setExampleTab] = useState<"console" | "plot">("console");

  const sessionRef = useRef<StudySession | null>(null);
  sessionRef.current = session;
  const initedChapterId = useRef<string | null>(null);

  useEffect(() => {
    api.getChapter(chapterId).then(setChapter).catch(() => setLoadError(true));
  }, [chapterId]);

  useEffect(() => {
    if (!chapter) return;
    if (initedChapterId.current === chapter.chapter_id) return;
    initedChapterId.current = chapter.chapter_id;
    studyStorage.findLatestSession(chapter.chapter_id).then((found) => {
      if (found && !found.is_completed) {
        setSession(found);
        setCurrentSectionNo(found.current_section_no);
      } else {
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

  const codeByUnit = useMemo(() => {
    if (!chapter || !session) return {} as Record<string, string>;
    const map: Record<string, string> = {};
    for (const s of chapter.sections) {
      map[String(unitIdx(s.no))] = s.example_code;
    }
    Object.assign(map, session.practice_code_by_unit);
    return map;
  }, [chapter, session]);

  const section = chapter?.sections.find((s) => s.no === currentSectionNo);

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
    } finally {
      setRunningUnit(null);
    }
  };

  const getPracticeCode = (unit: number, starter: string) => session?.practice_code_by_unit[String(unit)] ?? starter;

  const setPracticeCode = (unit: number, code: string) => {
    const s = sessionRef.current;
    if (!s) return;
    persist({ ...s, practice_code_by_unit: { ...s.practice_code_by_unit, [String(unit)]: code } });
  };

  const runPractice = async (unit: number, code: string) => {
    const s = sessionRef.current;
    if (!s || !chapter || runningUnit !== null) return;
    setRunningUnit(unit);
    try {
      const res = await api.runStudyUnit(chapter.chapter_id, { unit, current_code: code, code_by_unit: codeByUnit });
      setLastRuns((prev) => ({ ...prev, [unit]: res }));

      const prevResult = s.practice_results_by_unit[String(unit)];
      const isCorrect = !!res.is_correct;
      const nextWrong = isCorrect
        ? s.wrong_units.filter((u) => u !== unit)
        : s.wrong_units.includes(unit)
          ? s.wrong_units
          : [...s.wrong_units, unit];

      persist({
        ...s,
        practice_code_by_unit: { ...s.practice_code_by_unit, [String(unit)]: code },
        practice_results_by_unit: {
          ...s.practice_results_by_unit,
          [String(unit)]: {
            is_correct: isCorrect,
            attempts: (prevResult?.attempts ?? 0) + 1,
            revealed_answer: prevResult?.revealed_answer ?? false,
          },
        },
        wrong_units: nextWrong,
      });
    } finally {
      setRunningUnit(null);
    }
  };

  const revealAnswer = async (unit: number) => {
    const s = sessionRef.current;
    if (!s || !chapter) return;
    const res = await api.getPracticeAnswer(chapter.chapter_id, unit);
    setAnswers((prev) => ({ ...prev, [unit]: res.answer_code }));
    const prevResult = s.practice_results_by_unit[String(unit)];
    persist({
      ...s,
      practice_results_by_unit: {
        ...s.practice_results_by_unit,
        [String(unit)]: {
          is_correct: prevResult?.is_correct ?? false,
          attempts: prevResult?.attempts ?? 0,
          revealed_answer: true,
        },
      },
      wrong_units: s.wrong_units.includes(unit) ? s.wrong_units : [...s.wrong_units, unit],
    });
  };

  const goToSection = (no: number) => {
    const s = sessionRef.current;
    if (!s || !chapter) return;
    const completed = s.completed_sections.includes(currentSectionNo)
      ? s.completed_sections
      : [...s.completed_sections, currentSectionNo];
    const isLast = no > chapter.sections.length;
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

  const wrongItems = session.wrong_units
    .map((unit) => {
      for (const s of chapter.sections) {
        const p = s.practices.find((pp) => unitIdx(s.no, pp.no) === unit);
        if (p) return { section: s, practice: p, unit };
      }
      return null;
    })
    .filter((x): x is { section: (typeof chapter.sections)[number]; practice: (typeof section.practices)[number]; unit: number } => !!x);

  const hasTheory = section.theory_markdown.trim().length > 0;
  const hasExample = section.example_code.trim().length > 0;

  return (
    <div className="flex flex-1">
      <aside className="sticky top-0 hidden h-screen w-52 shrink-0 flex-col gap-1 overflow-y-auto border-r border-[var(--border)] bg-[var(--surface)] p-4 sm:flex">
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
          <div className="flex flex-col gap-5">
            <h2 className="text-xl font-extrabold">📝 복습 모드 — 못 풀었거나 정답을 본 문제</h2>
            {wrongItems.length === 0 && <p className="text-[var(--muted)]">복습할 문제가 없어요. 🎉</p>}
            {wrongItems.map(({ practice, unit }) => (
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
                revealed={session.practice_results_by_unit[String(unit)]?.revealed_answer ?? false}
                onReveal={() => revealAnswer(unit)}
                answerCode={answers[unit]}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-extrabold">
                {section.no}. {section.title}
              </h1>
              <OpenBookPanel />
            </div>

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
                  className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white"
                >
                  다음 섹션 →
                </button>
              ) : (
                <button
                  onClick={() => {
                    goToSection(chapter.sections.length + 1);
                    if (session.wrong_units.length > 0) {
                      setReviewMode(true);
                    } else {
                      router.push("/study");
                    }
                  }}
                  className="rounded-lg bg-[var(--ok)] px-4 py-2 text-sm font-bold text-white"
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
