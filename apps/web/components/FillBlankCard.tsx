"use client";

import { useState } from "react";
import { ExamProblem, BlankCheckResult } from "@/lib/api";
import { GradedResult } from "@/lib/storage";
import { MarkdownView } from "./MarkdownView";

// 실제 AICE Associate 시험에 실제로 나오는 "빈칸 채우기" 문제 유형 — 코드 뼈대는 이미 주어지고,
// 빈칸(함수 이름, 파라미터 이름 등 짧은 단어 하나)만 채우면 되는 형식이다. ExamProblemCard처럼
// 코드를 처음부터 다 쓰는 게 아니라서 전용 컴포넌트로 따로 만들었다 — CodeEditor(전체 코드 편집)
// 대신 "읽기 전용 코드 + 빈칸마다 작은 입력창"을 그린다.
//
// code_template 예시: "df_preset = pd.{{b1}}(data=df_na, {{b2}}=['Address1'])"
// 이 문자열을 "{{b1}}" 같은 마커 기준으로 쪼개서, 마커 자리에는 <input>을, 나머지는 코드 텍스트
// 그대로 렌더링한다.

interface Props {
  problem: ExamProblem;
  answers: Record<string, string>;               // blank id -> 지금까지 입력한 값 (부모 상태)
  onAnswerChange: (blankId: string, value: string) => void;
  onCheck: () => Promise<void>;
  checking: boolean;
  disabled: boolean;
  result?: GradedResult;                          // 세션에 저장된 채점 결과(정답/오답/점수)
  lastCheck?: BlankCheckResult;                   // 방금 채점 응답 — 빈칸별 정오답 표시에 사용
  flagged: boolean;
  onToggleFlag: () => void;
  cardRef: (el: HTMLDivElement | null) => void;
}

/** code_template을 "{{id}}" 마커 기준으로 [텍스트, 빈칸id, 텍스트, 빈칸id, ...] 형태로 쪼갠다. */
function splitTemplate(template: string): { text: string; blankId: string | null }[] {
  const parts: { text: string; blankId: string | null }[] = [];
  const regex = /\{\{(\w+)\}\}/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(template)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ text: template.slice(lastIndex, match.index), blankId: null });
    }
    parts.push({ text: "", blankId: match[1] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < template.length) {
    parts.push({ text: template.slice(lastIndex), blankId: null });
  }
  return parts;
}

export function FillBlankCard({
  problem,
  answers,
  onAnswerChange,
  onCheck,
  checking,
  disabled,
  result,
  lastCheck,
  flagged,
  onToggleFlag,
  cardRef,
}: Props) {
  const [showHint, setShowHint] = useState(false);
  const parts = splitTemplate(problem.code_template);

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
          <span className="rounded-md bg-[var(--brand-tint)] px-2 py-0.5 text-[10px] font-bold text-[var(--brand-dark)]">
            🧩 빈칸 채우기
          </span>
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

      {/* 코드 템플릿: 일반 텍스트는 <span>으로, {{blank}} 자리는 <input>으로 인라인 렌더링.
          실제 코드 에디터가 아니라 <pre> 안에 흐르는 문장처럼 배치해서 "코드 안의 빈칸"이라는
          느낌을 살렸다. */}
      <pre className="overflow-x-auto rounded-xl border-2 border-[var(--code-border)] bg-[var(--code-bg)] p-4 font-mono text-[15px] leading-relaxed whitespace-pre-wrap">
        <code>
          {parts.map((part, i) =>
            part.blankId ? (
              <input
                key={i}
                value={answers[part.blankId] ?? ""}
                onChange={(e) => onAnswerChange(part.blankId as string, e.target.value)}
                disabled={disabled}
                placeholder="___"
                // 입력창 너비를 입력된 글자 수에 맞춰 늘어나게 해서, 코드 문장 흐름이 안 어색하도록 함
                style={{ width: `${Math.max(4, (answers[part.blankId] ?? "").length + 2)}ch` }}
                className={`mx-0.5 rounded border-b-2 bg-transparent px-1 text-center font-mono text-[15px] text-[#e6e6f0] outline-none ${
                  lastCheck
                    ? lastCheck.results[part.blankId]
                      ? "border-b-[var(--ok)]"
                      : "border-b-[var(--bad)]"
                    : "border-b-[var(--brand)]"
                }`}
              />
            ) : (
              <span key={i}>{part.text}</span>
            )
          )}
        </code>
      </pre>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={onCheck}
          disabled={disabled}
          className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--brand-dark)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {checking ? "채점 중..." : "✅ 채점하기"}
        </button>
        <button
          onClick={() => setShowHint((v) => !v)}
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)]"
        >
          {showHint ? "힌트 숨기기" : "💡 힌트"}
        </button>
        {result && (
          <span className={`text-sm font-bold ${result.is_correct ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>
            {result.is_correct ? "✅ 정답" : "❌ 오답"} ({result.points_earned}점)
          </span>
        )}
      </div>

      {showHint && (
        <p className="mt-2 rounded-lg bg-[var(--brand-tint)] px-3 py-2 text-xs text-[var(--brand-dark)]">
          💡 빈칸에는 보통 함수 이름이나 파라미터 이름처럼 짧은 단어 하나가 들어갑니다. 문제 설명에 나온
          함수/메서드 이름을 그대로 입력해보세요 (대소문자까지 정확히 일치해야 정답 처리됩니다).
        </p>
      )}
    </div>
  );
}
