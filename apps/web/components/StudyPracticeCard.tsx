"use client";

import { memo, useEffect, useRef, useState } from "react";
import { StudyPractice, StudyRunResult } from "@/lib/api";
import { PracticeResult } from "@/lib/storage";
import { CodeEditor } from "./CodeEditor";
import { MarkdownView } from "./MarkdownView";
import { PlotViewer } from "./PlotViewer";

// ExamProblemCard와 구조가 거의 같은 형제 컴포넌트지만, "시험"이 아니라 "연습"이라는 성격
// 차이가 세부 동작에 그대로 드러난다: 오답이어도 감점 개념이 없고(그냥 다시 시도), 정답
// 보기를 여러 번 눌러도 페널티가 없다(💡 힌트/정답 보기라는 이름 자체가 그 톤을 반영).
//
// memo()로 감싸고 콜백에 unit을 먼저 붙여 부모에 넘기는 이유는 ExamProblemCard와 동일 —
// 한 챕터 섹션(또는 복습 모드)에 TODO 카드가 여러 개 동시에 떠 있을 때, 하나에 타이핑해도
// 나머지 카드가 리렌더되지 않게 하기 위함.
interface Props {
  unit: number;                                          // section.no*100 + practice.no — 이 TODO를 서버/세션에서 식별하는 번호
  practice: StudyPractice;
  code: string;
  onCodeChange: (unit: number, code: string) => void;
  onRun: (unit: number) => void;
  running: boolean;
  disabled: boolean;
  result?: PracticeResult;
  lastRun?: StudyRunResult;
  revealed: boolean;
  onReveal: (unit: number) => void;
  answerCode?: string;
  cardRef?: (unit: number, el: HTMLDivElement | null) => void;
}

export const StudyPracticeCard = memo(function StudyPracticeCard({
  unit,
  practice,
  code,
  onCodeChange,
  onRun,
  running,
  disabled,
  result,
  lastRun,
  revealed,
  onReveal,
  answerCode,
  cardRef,
}: Props) {
  const [tab, setTab] = useState<"console" | "plot" | "answer">("console");

  // --- 채점 중 경과시간 표시 ---
  // Render 무료 티어는 느릴 때가 있어서, 버튼을 누른 뒤 아무 반응이 없어 보이면 사용자가
  // "멈췄나?"하고 오해하기 쉽다. 그래서 버튼 라벨 자체에 초 단위로 흐르는 시간을 보여줘서
  // "지금도 계속 진행 중"이라는 걸 눈으로 확인할 수 있게 한다.
  const [elapsed, setElapsed] = useState(0);
  // setInterval이 반환하는 타이머 ID를 담아두는 ref. useState 대신 useRef를 쓰는 이유:
  // 이 ID 값 자체는 화면에 그려지는 것과 무관하고(리렌더링을 일으킬 필요가 없고), 그냥
  // "다음에 clearInterval할 때 쓸 참조값"만 어딘가에 붙잡아두면 되기 때문이다.
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      // 채점이 막 시작됐다(running이 false -> true로 바뀐 순간) — 0초부터 다시 세기 시작.
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } else {
      // 채점이 끝났다(또는 애초에 안 하고 있다) — 타이머를 멈춘다.
      if (timerRef.current) clearInterval(timerRef.current);
    }
    // useEffect의 return에 넣은 함수는 "정리(cleanup) 함수" — 이 컴포넌트가 화면에서
    // 사라지거나(unmount), 이 effect가 다시 실행되기 직전에 자동으로 호출된다. setInterval을
    // 여기서 확실히 정리해주지 않으면, 카드가 사라진 뒤에도 타이머가 백그라운드에서 계속
    // 돌면서 이미 없어진 컴포넌트의 상태를 바꾸려는 메모리 누수/경고가 생길 수 있다.
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [running]);
  // [running] = 의존성 배열. running 값이 바뀔 때만(채점 시작/종료 시점에만) 이 effect를
  // 다시 실행한다는 뜻 — 매 렌더링마다 무의미하게 타이머를 새로 만들지 않도록.

  /** 경과 시간(초)에 따라 점점 더 자세한 안내 문구로 바꿔서, "왜 오래 걸리는지" 짐작하게 해준다. */
  function getRunningMsg(sec: number) {
    if (sec < 5) return "채점 중...";
    if (sec < 20) return `서버 실행 중... (${sec}초)`;
    if (sec < 50) return `서버 워밍업 중... (${sec}초) — 잠시만 기다려주세요`;
    return `코드 실행 중... (${sec}초) — 딥러닝은 최대 3분 소요`;
  }

  // 모의고사 카드(ExamProblemCard)는 오답을 --bad(빨강)로 강하게 표시하지만, 학습 모드는
  // "틀려도 괜찮다"는 톤을 주려고 오답/정답확인을 --warn(주황) 하나로 부드럽게 표시한다.
  const statusColor = result
    ? result.is_correct
      ? "border-l-4 border-l-[var(--ok)]"
      : "border-l-4 border-l-[var(--warn)]"
    : "border-l-4 border-l-transparent";

  return (
    <div ref={(el) => cardRef?.(unit, el)} className={`card ${statusColor} p-5`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="pill">TODO {practice.no}</span>
        {result && (
          <span className={`text-sm font-bold ${result.is_correct ? "text-[var(--ok)]" : "text-[var(--warn)]"}`}>
            {result.is_correct ? "✅ 정답" : revealed ? "🔎 정답 확인함" : "🙈 다시 시도"}
          </span>
        )}
      </div>

      <div className="mb-3 text-sm leading-relaxed">
        <MarkdownView>{practice.prompt_markdown}</MarkdownView>
      </div>

      <CodeEditor value={code} onChange={(c) => onCodeChange(unit, c)} minHeight="140px" />

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => onRun(unit)}
          disabled={disabled}
          className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--brand-dark)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? getRunningMsg(elapsed) : "✅ 채점하기"}
        </button>
        <button
          onClick={() => {
            setTab("answer");
            onReveal(unit);
          }}
          // ExamProblemCard의 "정답 보기"와 같은 이유로 disabled(채점 진행 중 잠금)를 안 건다 —
          // 정답 보기는 서버(채점 워커)를 안 거치는 순수 클라이언트 동작이라 채점 요청이
          // 서버 응답을 기다리는 동안에도 항상 즉시 눌려야 한다.
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)] disabled:opacity-50"
        >
          💡 힌트 / 정답 보기
        </button>
      </div>

      <div className="mt-3 rounded-lg border border-[var(--border)]">
        <div className="flex border-b border-[var(--border)] text-xs font-semibold">
          {(["console", "plot", "answer"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-2 ${tab === t ? "border-b-2 border-[var(--brand)] text-[var(--brand)]" : "text-[var(--muted)]"}`}
            >
              {t === "console" ? "콘솔 출력" : t === "plot" ? "시각화" : "정답"}
            </button>
          ))}
        </div>
        <div className="min-h-[50px] max-h-72 overflow-auto">
          {tab === "console" && (
            <pre className="whitespace-pre-wrap p-3 font-mono text-xs">
              {lastRun ? lastRun.stdout + (lastRun.error ? `\n${lastRun.error}` : "") || "(출력 없음)" : "채점하기를 누르면 결과가 여기에 표시됩니다."}
            </pre>
          )}
          {tab === "plot" && <PlotViewer plots={lastRun?.plots ?? []} />}
          {tab === "answer" && (
            <pre className="whitespace-pre-wrap p-3 font-mono text-xs">
              {revealed && answerCode ? answerCode : "위쪽의 [💡 힌트 / 정답 보기] 버튼을 클릭하셔야 정답이 표시됩니다.\n(아래 탭을 누르는 것이 아니라 버튼을 누르셔야 합니다!)"}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
});
