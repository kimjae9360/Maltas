"use client";

import { memo, useState } from "react";
import { ExamProblem, RunResult } from "@/lib/api";
import { GradedResult } from "@/lib/storage";
import { CodeEditor } from "./CodeEditor";
import { MarkdownView } from "./MarkdownView";
import { PlotViewer } from "./PlotViewer";

// 모의고사 응시 화면(app/exam/[examId]/page.tsx)에서 문제 하나를 통째로 그리는 카드 컴포넌트.
// "제어 컴포넌트(controlled component)" 패턴을 쓴다 — 이 컴포넌트 자신은 상태(코드 내용, 채점
// 결과 등)를 거의 안 들고 있고, 전부 부모(page.tsx)로부터 props로 받아서 화면에 보여주기만 하며,
// 사용자가 뭔가 하면(코드 입력, 실행 버튼 클릭 등) 부모가 넘겨준 콜백을 불러서 "부모에게 알린다".
// 이렇게 하면 여러 문제 카드들 사이의 데이터(예: code_by_problem 전체)를 부모 한 곳에서만
// 관리하면 되고, "이어서 풀기"를 위해 세션 전체를 저장할 때도 부모의 상태 하나만 IndexedDB에
// 저장하면 된다.
//
// memo()로 감싼 이유: 모의고사 한 회당 문제 카드가 최대 17개까지 동시에 화면에 떠 있는데(각
// 카드마다 CodeMirror 에디터+마크다운 렌더러가 들어있어 결코 가볍지 않다), 콜백들을 모두
// "번호가 이미 적용된" 안정적인 함수로 부모(page.tsx)에서 받도록 바꿔서(onCodeChange(no, code)
// 형태), 문제 5번에 타이핑할 때 나머지 16개 카드는 props가 하나도 안 바뀌어 리렌더를 건너뛰게
// 만든다. (부모가 매 렌더링마다 새 화살표 함수를 만들어 넘기면 memo는 무용지물이 된다는 점이
// 이 최적화의 핵심 전제)
interface Props {
  problem: ExamProblem;
  code: string;                                          // 이 문제에 대해 지금까지 작성된 코드 (부모의 code_by_problem[no])
  onCodeChange: (no: number, code: string) => void;      // 에디터에 타이핑할 때마다 호출 — 부모 상태를 갱신
  onRun: (no: number) => void;                            // "실행" 버튼 클릭 시 호출 — 실제 API 요청은 부모가 담당
  running: boolean;                                       // 지금 이 문제(또는 다른 문제)가 채점 중인지
  disabled: boolean;                                      // 버튼 비활성화 여부 (running 중이거나 시험 제출 후 등)
  result?: GradedResult;                                  // 이 문제의 채점 결과 (없으면 아직 안 풀었거나 안 채점됨)
  lastRun?: RunResult;                                    // 가장 최근 실행의 콘솔 출력/그래프 (result와 별개로 관리)
  flagged: boolean;                                       // "검토 표시"(나중에 다시 볼 문제) 깃발이 켜져 있는지
  onToggleFlag: (no: number) => void;
  revealed: boolean;                                      // 정답 보기를 이미 눌렀는지 (누르면 이 문제는 0점 처리됨)
  onReveal: (no: number) => void;
  answerCode?: string;                                    // 정답 보기를 눌렀을 때만 채워지는 실제 정답 코드
  cardRef: (no: number, el: HTMLDivElement | null) => void;
  // 문제 번호를 클릭해서 "그 문제로 스크롤 이동"하는 네비게이션 기능을 위해, 부모가 이 DOM
  // 엘리먼트를 참조(ref)로 잡아둘 수 있게 넘겨받는 콜백. React의 ref 콜백 패턴.
}

export const ExamProblemCard = memo(function ExamProblemCard({
  problem,
  code,
  onCodeChange,
  onRun,
  running,
  disabled,
  result,
  lastRun,
  flagged,
  onToggleFlag,
  revealed,
  onReveal,
  answerCode,
  cardRef,
}: Props) {
  // tab: 이 카드 안에서 "콘솔 출력 / 시각화 / 정답" 중 지금 어떤 탭이 보이는지.
  // 이건 다른 문제로 넘어가면 다시 초기화돼도 되는 순전히 이 카드만의 화면 상태라서,
  // 부모가 아니라 이 컴포넌트 안에서 useState로 직접 관리한다(제어 컴포넌트 패턴의 예외).
  const [tab, setTab] = useState<"console" | "plot" | "answer">("console");

  // 채점 결과에 따라 카드 왼쪽 테두리 색을 다르게 — 정답(초록)/오답(빨강)/미채점(투명)을
  // 한눈에 구분할 수 있게 해서, 여러 문제를 쭉 내려보며 스크롤할 때 상태 파악이 쉽도록 한다.
  const statusColor = result
    ? result.is_correct
      ? "border-l-4 border-l-[var(--ok)]"
      : "border-l-4 border-l-[var(--bad)]"
    : "border-l-4 border-l-transparent";

  return (
    <div ref={(el) => cardRef(problem.no, el)} className={`card ${statusColor} p-5`}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="pill">문항 {problem.no}</span>
          {problem.question_type === "bug_fix" && (
            <span className="rounded-md bg-[var(--warn-tint)] px-2 py-0.5 text-[10px] font-bold text-[var(--warn)]">
              🐛 오류 정정
            </span>
          )}
          <span className="text-xs text-[var(--muted)]">{problem.session}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[var(--muted)]">{problem.points}점</span>
          <button
            onClick={() => onToggleFlag(problem.no)}
            className={`rounded-md border px-2 py-1 text-xs font-semibold transition ${
              flagged
                ? "border-[var(--warn)] bg-[var(--warn-tint)] text-[var(--warn)]"
                : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            🚩 검토 표시
          </button>
        </div>
      </div>

      <div className="mb-3 text-sm leading-relaxed">
        <MarkdownView>{problem.prompt_markdown}</MarkdownView>
      </div>

      <CodeEditor value={code} onChange={(c) => onCodeChange(problem.no, c)} minHeight="180px" />

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => onRun(problem.no)}
          disabled={disabled}
          className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--brand-dark)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "실행 중..." : "▶ 실행"}
        </button>
        <button
          onClick={() => {
            setTab("answer");
            onReveal(problem.no);
          }}
          disabled={disabled || revealed}
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          정답 보기
        </button>
        {result && (
          <span className={`text-sm font-bold ${result.is_correct ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>
            {result.is_correct ? "✅ 정답" : "❌ 오답"} ({result.points_earned}점)
          </span>
        )}
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
        <div className="min-h-[60px] max-h-72 overflow-auto">
          {tab === "console" && (
            <pre className="whitespace-pre-wrap p-3 font-mono text-xs">
              {lastRun ? lastRun.stdout + (lastRun.error ? `\n${lastRun.error}` : "") || "(출력 없음)" : "실행하면 결과가 여기에 표시됩니다."}
            </pre>
            // lastRun이 있으면 stdout(+에러가 있으면 이어붙여서) 보여주고, 그마저도 빈 문자열이면
            // "||"로 "(출력 없음)" 문구로 대체한다. lastRun 자체가 없으면(한 번도 실행 안 함)
            // 아예 다른 안내 문구를 보여준다 — "출력 없음"과 "아직 실행 안 함"을 구분해서 헷갈리지 않게.
          )}
          {tab === "plot" && <PlotViewer plots={lastRun?.plots ?? []} />}
          {tab === "answer" && (
            <pre className="whitespace-pre-wrap p-3 font-mono text-xs">
              {revealed && answerCode ? answerCode : "위쪽의 [정답 보기] 버튼을 클릭하셔야 정답이 표시됩니다.\n(아래 탭을 누르는 것이 아니라 버튼을 누르셔야 합니다!)"}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
});
