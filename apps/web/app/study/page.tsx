"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, ChapterSummary } from "@/lib/api";
import { studyStorage, StudySession } from "@/lib/storage";

// "이론 공부"와 "실무 연습" 두 메뉴가 실제로는 이 파일 하나를 공유한다(app/page.tsx 주석 참고).
// 서버가 미리 만들어둔 "본편"(이론 포함) 챕터와 "_실무전용"(이론 없이 문제만) 챕터를 각각
// mode 값에 따라 걸러서 보여줄 뿐, 화면 구조나 데이터를 불러오는 방식은 완전히 동일하다.
function StudyPageInner() {
  const params = useSearchParams();
  // useSearchParams(): 지금 URL의 "?mode=practice" 같은 쿼리스트링을 읽는 Next.js 훅.
  // params.get("mode")가 "practice"가 아니면(없거나 다른 값이면) 전부 "theory"로 취급해서
  // 기본값이 항상 안전하게 정해지도록 한다.
  const mode = params.get("mode") === "practice" ? "practice" : "theory";

  const [chapters, setChapters] = useState<ChapterSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<StudySession[]>([]);

  useEffect(() => {
    api.listChapters().then(setChapters).catch((e) => setError(String(e)));
    studyStorage.listAll().then(setSessions);
  }, []);

  // 서버가 내려준 28개 챕터 중, 지금 모드에 맞는 것만 골라낸다.
  // is_practice_only는 서버(app.py)가 chapter_id.endswith("_실무전용")로 미리 계산해둔 값.
  const filtered = chapters?.filter((c) => c.is_practice_only === (mode === "practice"));
  // (참고) 00_AI개념, 11_비지도학습, 12_빈출패턴요약 세 챕터는 "_실무전용" 버전이 아예 없어서,
  // mode=practice(실무 연습)에서는 이 셋이 목록에 안 보인다 — 개념 설명 위주 챕터라 일부러
  // 실무전용 버전을 따로 안 만든 것이지, 버그로 빠진 게 아니다.

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <div className="mb-8">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          ← 홈으로
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-3xl font-extrabold tracking-tight">
            {mode === "theory" ? "📖 이론 공부 — 챕터 선택" : "💻 실무 연습 — 챕터 선택"}
          </h1>
          <Link href="/history" className="text-xs font-semibold text-[var(--muted)] hover:text-[var(--brand)]">
            히스토리 →
          </Link>
        </div>
        <p className="mt-1.5 text-[15px] text-[var(--muted)]">
          {mode === "theory"
            ? "개념 설명 → 핵심 정리 → 예제 → TODO 문제 순서로 진행돼요. 막히면 언제든 힌트/정답을 볼 수 있어요."
            : "이론 설명 없이 TODO 문제만 밀도 있게 이어집니다. 손에 익히는 반복 연습용이에요."}
        </p>
      </div>

      {error && <p className="text-[var(--bad)]">{error} (서버가 실행 중인지 확인해주세요)</p>}

      {!error && chapters === null && (
        <div className="mt-8 flex justify-center">
          <p className="text-[var(--muted)]">데이터를 불러오는 중입니다...</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {filtered?.map((c) => {
          const session = sessions.find((s) => s.chapter_id === c.chapter_id);
          // 이 챕터로 공부한 적이 있으면(session이 있으면) "완료" 또는 "진행중 n/m" 배지를 붙인다.
          return (
            <Link
              key={c.chapter_id}
              href={`/study/${encodeURIComponent(c.chapter_id)}`}
              className="card flex flex-col gap-1 p-5 transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="text-[15px] font-bold">{c.title}</div>
              <div className="flex flex-wrap gap-2 text-xs text-[var(--muted)]">
                <span className="pill">{c.section_count}섹션</span>
                <span className="pill">TODO {c.practice_count}개</span>
                {session && (
                  <span className="pill">
                    {session.is_completed ? "완료" : `진행중 ${session.completed_sections.length}/${c.section_count}`}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default function StudyPage() {
  // <Suspense>로 감싸는 이유: 이 페이지 안에서 useSearchParams()를 쓰는데, Next.js는
  // 쿼리스트링을 읽는 컴포넌트를 "그 값을 알아내는 동안 잠시 대기(suspend)할 수 있는"
  // 컴포넌트로 취급한다. 그래서 부모를 Suspense로 감싸주지 않으면 빌드 시 경고/에러가 난다.
  // (여기선 별도 로딩 UI를 fallback으로 안 넣었으니, 그 짧은 대기 동안은 아무것도 안 보인다)
  return (
    <Suspense>
      <StudyPageInner />
    </Suspense>
  );
}
