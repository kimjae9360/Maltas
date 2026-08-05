// 문제 지문(prompt_markdown), 이론 설명(theory_markdown) 등 서버가 마크다운 "문자열"로
// 내려주는 텍스트를 실제 HTML(제목, 목록, 표, 굵은 글씨 등)로 바꿔서 보여주는 공용 컴포넌트.
import { memo, useState, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
// remark-gfm: GitHub Flavored Markdown 확장 — 표(table), 취소선 같은 기본 마크다운에
// 없는 문법을 지원하게 해준다. 개념표(concept_table_markdown)를 표로 렌더링하려면 필수.

// 실제 AICE 시험은 파일명·컬럼명·변수명을 문제 화면에서 그대로 "복사"해서 코드에 붙여넣을 수
// 있게 해준다 — 오타로 틀리는 걸 막기 위해서다. 이 시뮬레이터의 문제 지문은 그런 이름들을
// 이미 백틱(`data/train.csv` 같은 인라인 코드)으로 표시해두고 있으므로, 그 인라인 코드를
// 클릭하면 클립보드로 복사되게만 하면 별도 데이터 필드 없이도 같은 효과를 낼 수 있다.
function CopyableInlineCode({ children }: { children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const text = typeof children === "string" ? children : String(children ?? "");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
      // 1.2초 뒤 원래 표시로 되돌아온다 — 계속 "복사됨"으로 남아있으면 다시 눌러도 되는지
      // 헷갈리기 때문에, 짧게 확인만 보여주고 원상복구한다.
    } catch {
      // 클립보드 접근이 막힌 환경(권한 거부 등)에서는 조용히 무시한다 — 텍스트 자체는
      // 화면에 그대로 보이니 수동으로 드래그해서 복사하는 대안이 항상 남아있다.
    }
  };

  return (
    <code
      onClick={handleCopy}
      title="클릭하면 복사됩니다"
      className={`cursor-pointer rounded px-1 transition ${
        copied
          ? "bg-[var(--ok-tint)] text-[var(--ok)]"
          : "hover:bg-[var(--brand-tint)] hover:text-[var(--brand)]"
      }`}
    >
      {copied ? "✓ 복사됨" : children}
    </code>
  );
}

// react-markdown은 인라인 코드(`text`)와 여러 줄짜리 코드블록(```lang\n...\n```)을
// 똑같이 <code> 엘리먼트로 넘겨준다 — 구분하는 유일한 단서는 코드블록에만 rehype가
// 붙여주는 className(예: "language-python")이 있다는 것. className이 없으면 인라인
// 코드로 보고 클릭 복사를 붙이고, 있으면(코드블록) 원래대로 그냥 렌더링한다.
function CodeRenderer({ className, children, ...rest }: ComponentProps<"code">) {
  if (className) {
    return (
      <code className={className} {...rest}>
        {children}
      </code>
    );
  }
  return <CopyableInlineCode>{children}</CopyableInlineCode>;
}

// memo()로 감싼 이유: ReactMarkdown은 렌더링될 때마다 마크다운 문자열을 처음부터 다시
// 파싱한다(캐싱을 자체적으로 하지 않음). study/[chapterId]/page.tsx의 이론 설명·개념표처럼
// memo 카드 "밖"에 직접 놓인 MarkdownView는, 같은 화면의 TODO 카드에 글자 하나만 쳐도
// (부모 페이지 전체가 리렌더되므로) 매번 다시 파싱되고 있었다. children(문자열) 값이
// 그대로면 건너뛰도록 이 컴포넌트 자체를 memo로 감쌌다.
export const MarkdownView = memo(function MarkdownView({ children }: { children: string }) {
  // children으로 마크다운 "문자열"을 받는다. 보통 <MarkdownView>텍스트</MarkdownView> 처럼
  // 태그 사이에 내용을 적으면 React가 자동으로 children prop에 그 내용을 넣어준다.
  return (
    <div
      // Tailwind Typography 플러그인(`prose` 클래스)을 쓰면, ReactMarkdown이 만들어낸
      // <h1>/<p>/<table> 같은 평범한 HTML 태그들에 자동으로 보기 좋은 글꼴 크기·줄간격·여백을 입혀준다.
      // dark:prose-invert — 다크 테마일 때 글자색을 자동으로 반전(밝게)시키는 프리셋.
      // prose-table:text-sm — 표 안의 글자만 살짝 작게. prose-code:before/after:content-none —
      // 인라인 코드(`code`)에 기본으로 붙는 백틱(`) 장식을 없애서 더 깔끔하게 보이도록.
      className="prose prose-sm max-w-none dark:prose-invert prose-table:text-sm prose-code:before:content-none prose-code:after:content-none"
      style={{ color: "var(--foreground)" }}
      // globals.css의 --tw-prose-* 커스텀 변수들만으로는 일부 색이 옅게 나오는 경우가 있어서,
      // 컨테이너 자체의 글자색을 우리 테마 변수로 한 번 더 명시해준다(라이트 모드 가독성 버그 수정 이력).
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeRenderer }}>
        {children}
      </ReactMarkdown>
    </div>
  );
});
