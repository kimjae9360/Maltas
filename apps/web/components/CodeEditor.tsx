"use client";
// "use client" 지시문: Next.js(App Router)는 기본적으로 컴포넌트를 서버에서 렌더링(Server
// Component)하려고 한다. 하지만 이 컴포넌트는 브라우저 안에서만 동작하는 CodeMirror(에디터
// UI, 키 입력 처리 등)를 쓰기 때문에, 파일 맨 위에 "use client"를 적어서 "이건 반드시
// 브라우저에서 실행돼야 하는 컴포넌트"라고 Next.js에게 알려준다.

import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";

// 이 컴포넌트를 쓰는 쪽(부모)이 넘겨줘야 하는 props(속성)들의 타입 정의.
interface Props {
  value: string;                       // 에디터에 지금 표시할 코드 (부모가 상태로 들고 있음)
  onChange: (value: string) => void;   // 사용자가 타이핑할 때마다 호출되는 콜백 — 여기서 부모의 상태를 갱신한다
  readOnly?: boolean;                  // true면 편집 불가 (예: "정답 보기" 탭에 정답 코드를 보여줄 때)
  minHeight?: string;                  // 에디터 최소 높이 (CSS 값 문자열, 예: "220px")
}

// 코드 에디터는 라이트/다크 테마 무관하게 항상 다크 테마를 유지한다.
// (VS Code, Jupyter 등 대부분의 개발 도구와 동일한 방식)
export function CodeEditor({ value, onChange, readOnly = false, minHeight = "220px" }: Props) {
  // { value, onChange, ... } 형태의 인자는 구조 분해 할당(destructuring) — props 객체에서
  // 필요한 값들을 바로 꺼내 쓰는 문법. "readOnly = false"처럼 "="를 쓰면 그 prop이 안 넘어왔을 때
  // 쓸 기본값을 지정하는 것 (Props 타입에서 "?"가 붙은 선택적 필드들이 여기서 기본값을 받는다).
  return (
    <div className="overflow-hidden rounded-xl border-2 border-[var(--code-border)] focus-within:border-[var(--brand)]">
      {/* focus-within: 이 div 안의 자식(에디터 내부)이 포커스를 받으면 테두리 색이 브랜드 색으로 바뀐다 */}
      <CodeMirror
        value={value}
        onChange={onChange}
        editable={!readOnly}
        theme="dark"
        extensions={[python(), EditorView.lineWrapping]}
        // extensions = CodeMirror의 기능을 조립하는 방식. python()은 파이썬 문법 하이라이팅/들여쓰기
        // 규칙을 추가하는 확장이고, EditorView.lineWrapping은 긴 줄을 가로 스크롤 대신 자동 줄바꿈하게 한다.
        basicSetup={{ lineNumbers: true, foldGutter: false }}
        // foldGutter: false — 코드 블록을 접었다 펼 수 있는 화살표 UI를 꺼둔다(짧은 문제 코드에는
        // 불필요한 기능이라 화면을 더 단순하게 유지하려는 선택).
        style={{ fontSize: "15px" }}
        minHeight={minHeight}
      />
    </div>
  );
}
