"use client";

import { useEffect, useRef, useState } from "react";
import { StudyPractice, StudyRunResult } from "@/lib/api";
import { PracticeResult } from "@/lib/storage";
import { CodeEditor } from "./CodeEditor";
import { MarkdownView } from "./MarkdownView";
import { PlotViewer } from "./PlotViewer";

interface Props {
  practice: StudyPractice;
  code: string;
  onCodeChange: (code: string) => void;
  onRun: () => Promise<void>;
  running: boolean;
  disabled: boolean;
  result?: PracticeResult;
  lastRun?: StudyRunResult;
  revealed: boolean;
  onReveal: () => void;
  answerCode?: string;
  cardRef?: (el: HTMLDivElement | null) => void;
}

export function StudyPracticeCard({
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
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [running]);

  function getRunningMsg(sec: number) {
    if (sec < 5) return "채점 중...";
    if (sec < 20) return `서버 실행 중... (${sec}초)`;
    if (sec < 50) return `서버 워밍업 중... (${sec}초) — 잠시만 기다려주세요`;
    return `코드 실행 중... (${sec}초) — 딥러닝은 최대 3분 소요`;
  }

  const statusColor = result
    ? result.is_correct
      ? "border-l-4 border-l-[var(--ok)]"
      : "border-l-4 border-l-[var(--warn)]"
    : "border-l-4 border-l-transparent";

  return (
    <div ref={cardRef} className={`card ${statusColor} p-5`}>
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

      <CodeEditor value={code} onChange={onCodeChange} minHeight="140px" />

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={onRun}
          disabled={disabled}
          className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--brand-dark)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? getRunningMsg(elapsed) : "✅ 채점하기"}
        </button>
        <button
          onClick={() => {
            onReveal();
            setTab("answer");
          }}
          disabled={disabled}
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)]"
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
              {revealed && answerCode ? answerCode : "힌트/정답 보기를 눌러야 확인할 수 있습니다."}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
