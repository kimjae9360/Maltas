"use client";

import { useState } from "react";
import { ExamProblem, RunResult } from "@/lib/api";
import { GradedResult } from "@/lib/storage";
import { CodeEditor } from "./CodeEditor";
import { MarkdownView } from "./MarkdownView";
import { PlotViewer } from "./PlotViewer";

interface Props {
  problem: ExamProblem;
  code: string;
  onCodeChange: (code: string) => void;
  onRun: () => Promise<void>;
  running: boolean;
  disabled: boolean;
  result?: GradedResult;
  lastRun?: RunResult;
  flagged: boolean;
  onToggleFlag: () => void;
  revealed: boolean;
  onReveal: () => void;
  answerCode?: string;
  cardRef: (el: HTMLDivElement | null) => void;
}

export function ExamProblemCard({
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
  const [tab, setTab] = useState<"console" | "plot" | "answer">("console");

  const statusColor = result
    ? result.is_correct
      ? "border-l-4 border-l-[var(--ok)]"
      : "border-l-4 border-l-[var(--bad)]"
    : "border-l-4 border-l-transparent";

  return (
    <div ref={cardRef} className={`card ${statusColor} p-5`}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="pill">문항 {problem.no}</span>
          <span className="text-xs text-[var(--muted)]">{problem.session}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[var(--muted)]">{problem.points}점</span>
          <button
            onClick={onToggleFlag}
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

      <CodeEditor value={code} onChange={onCodeChange} minHeight="180px" />

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={onRun}
          disabled={disabled}
          className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--brand-dark)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "실행 중..." : "▶ 실행"}
        </button>
        <button
          onClick={onReveal}
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
          )}
          {tab === "plot" && <PlotViewer plots={lastRun?.plots ?? []} />}
          {tab === "answer" && (
            <pre className="whitespace-pre-wrap p-3 font-mono text-xs">
              {revealed && answerCode ? answerCode : "정답 보기를 눌러야 확인할 수 있습니다."}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
