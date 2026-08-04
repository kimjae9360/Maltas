"use client";

import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";

interface Props {
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  minHeight?: string;
}

// 코드 에디터는 라이트/다크 테마 무관하게 항상 다크 테마를 유지한다.
// (VS Code, Jupyter 등 대부분의 개발 도구와 동일한 방식)
export function CodeEditor({ value, onChange, readOnly = false, minHeight = "220px" }: Props) {
  return (
    <div className="overflow-hidden rounded-xl border-2 border-[var(--code-border)] focus-within:border-[var(--brand)]">
      <CodeMirror
        value={value}
        onChange={onChange}
        editable={!readOnly}
        theme="dark"
        extensions={[python(), EditorView.lineWrapping]}
        basicSetup={{ lineNumbers: true, foldGutter: false }}
        style={{ fontSize: "15px" }}
        minHeight={minHeight}
      />
    </div>
  );
}
