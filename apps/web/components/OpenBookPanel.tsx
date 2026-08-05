"use client";

import { useState } from "react";

const LINKS = [
  { name: "pandas", url: "https://pandas.pydata.org/docs/reference/index.html" },
  { name: "NumPy", url: "https://numpy.org/doc/stable/reference/index.html" },
  { name: "scikit-learn", url: "https://scikit-learn.org/stable/api/index.html" },
  { name: "Matplotlib", url: "https://matplotlib.org/stable/api/index.html" },
  { name: "seaborn", url: "https://seaborn.pydata.org/api.html" },
  { name: "TensorFlow", url: "https://www.tensorflow.org/api_docs" },
  { name: "XGBoost", url: "https://xgboost.readthedocs.io/en/stable/" },
];
// 배열을 컴포넌트 함수 "바깥"에 상수로 선언해둔 이유: 컴포넌트 안에 선언하면 렌더링될 때마다
// 이 배열이 매번 새로 만들어지는데, 어차피 내용이 절대 바뀌지 않는 고정 목록이라 굳이 그럴
// 필요가 없다. 모듈이 처음 로드될 때 딱 한 번만 만들어지고 계속 재사용된다.

// 실제 AICE 시험은 이 7개 라이브러리의 공식문서만 오픈북으로 허용된다. 답을 외우는 시험이
// 아니라 "필요한 걸 빠르게 찾아 쓰는" 시험이라, 연습할 때도 같은 방식으로 문서를 찾아보게 한다.
export function OpenBookPanel() {
  // open: 드롭다운이 펼쳐져 있는지 여부. 버튼을 누를 때마다 useState로 이 화면 상태를 토글한다.
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      {/* relative: 아래 드롭다운(absolute)이 "이 버튼을 기준으로" 위치를 잡도록 기준점을 만든다 */}
      <button
        onClick={() => setOpen((v) => !v)}
        // setOpen((v) => !v) : 함수형 업데이트 — 현재 값(v)을 받아서 반대로 뒤집는다.
        // setOpen(!open)이라고 써도 결과는 같지만, 함수형으로 쓰면 React가 상태 업데이트를
        // 여러 개 몰아서 처리(batching)해도 항상 "가장 최신 값" 기준으로 안전하게 계산된다.
        className="shrink-0 whitespace-nowrap rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)]"
        // ThemeToggle과 같은 이유로 whitespace-nowrap 추가 — 좁은 화면에서 "📚"와 "오픈북"이
        // 버튼 안에서 따로 줄바꿈되던 문제를 막는다.
      >
        📚 오픈북
      </button>
      {open && (
        // {open && (...)} : open이 true일 때만 아래 JSX를 렌더링하는 React의 흔한 조건부 렌더링 패턴.
        // (open이 false면 &&의 왼쪽에서 바로 멈추고 오른쪽은 평가되지 않아, 화면에 아무것도 안 그려짐)
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          {/* 화면 전체를 덮는 투명한 오버레이. 드롭다운이 열려있을 때 바깥 아무 곳이나 클릭하면
              (이 div가 클릭을 가로채서) 드롭다운이 닫히게 만드는 흔한 트릭이다. z-20으로 드롭다운
              본체(z-30)보다는 아래, 다른 페이지 요소들보다는 위에 두어 순서를 맞춘다. */}
          <div className="card absolute right-0 top-full z-30 mt-2 w-56 p-2">
            <p className="mb-1 px-2 text-xs font-bold text-[var(--muted)]">공식 문서 (실제 시험 오픈북과 동일)</p>
            {LINKS.map((l) => (
              <a
                key={l.name}
                // key: React가 리스트의 각 항목을 구분하기 위해 요구하는 고유값. 목록이 바뀔 때
                // "어떤 항목이 추가/삭제/이동됐는지"를 효율적으로 판단하는 데 쓰인다(성능 최적화).
                href={l.url}
                target="_blank"          // 새 탭에서 열기 — 문제 풀던 화면(코드/타이머)을 잃지 않도록
                rel="noopener noreferrer" // target="_blank"를 쓸 때 반드시 같이 넣는 보안 관행:
                // noopener는 새로 열린 탭이 window.opener로 원래 페이지를 조작하지 못하게 막고,
                // noreferrer는 어느 페이지에서 왔는지 정보(Referer 헤더)가 넘어가지 않게 한다.
                className="block rounded-md px-2 py-1.5 text-sm hover:bg-[var(--brand-tint)]"
              >
                {l.name} ↗
              </a>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
