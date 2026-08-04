"use client";

import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  minHeight?: string;
}

// 골든래빗 사이트의 답안 입력창(코드 줄 중간에 끼워넣는 작은 인라인 박스)이 잘 안 보인다는
// 피드백에 따라, 여기서는 넉넉한 높이/패딩/폰트 크기의 전체 코드 에디터를 기본값으로 둔다.
export function CodeEditor({ value, onChange, readOnly = false, minHeight = "220px" }: Props) {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // eslint-disable-next-line
  useEffect(() => setMounted(true), []);

  return (
    <div className="overflow-hidden rounded-xl border-2 border-[var(--code-border)] focus-within:border-[var(--brand)]">
      <CodeMirror
        value={value}
        onChange={onChange}
        editable={!readOnly}
        theme={mounted && theme === "dark" ? "dark" : "light"}
        extensions={[python(), EditorView.lineWrapping]}
        basicSetup={{ lineNumbers: true, foldGutter: false }}
        style={{ fontSize: "15px" }}
        minHeight={minHeight}
      />
    </div>
  );
}
