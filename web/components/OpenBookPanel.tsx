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

// 실제 AICE 시험은 이 7개 라이브러리의 공식문서만 오픈북으로 허용된다. 답을 외우는 시험이
// 아니라 "필요한 걸 빠르게 찾아 쓰는" 시험이라, 연습할 때도 같은 방식으로 문서를 찾아보게 한다.
export function OpenBookPanel() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--foreground)]"
      >
        📚 오픈북
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="card absolute right-0 top-full z-30 mt-2 w-56 p-2">
            <p className="mb-1 px-2 text-xs font-bold text-[var(--muted)]">공식 문서 (실제 시험 오픈북과 동일)</p>
            {LINKS.map((l) => (
              <a
                key={l.name}
                href={l.url}
                target="_blank"
                rel="noopener noreferrer"
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
