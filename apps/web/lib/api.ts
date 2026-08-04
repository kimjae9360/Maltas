// 이 파일 하나가 프론트엔드(apps/web)와 백엔드(apps/server) 사이의 "유일한 통로"다.
// 다른 컴포넌트/페이지들은 fetch()를 직접 호출하지 않고 항상 이 파일이 내보내는 `api` 객체를
// 통해서만 서버와 통신한다 — API 주소나 인증 방식이 바뀌어도 이 파일 하나만 고치면 되도록.

// 환경변수(.env.local, Vercel 프로젝트 설정 등)로 서버 주소/키를 주입받는다.
// NEXT_PUBLIC_ 접두사가 붙은 환경변수는 Next.js가 빌드할 때 브라우저에서도 보이는 코드에
// 그대로 박아넣는다(서버 전용 비밀값은 이 접두사 없이 따로 관리해야 한다). API_KEY도 결국
// 브라우저 번들 안에 그대로 노출되므로, app.py 주석에도 적어뒀듯 "진짜 보안"은 아니다.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8123";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

/**
 * 실제 fetch를 감싸는 공통 헬퍼. 이 프로젝트의 모든 API 호출은 결국 이 함수를 거친다.
 *
 * <T> 는 제네릭(generic) — "이 함수가 어떤 타입을 돌려줄지는 호출하는 쪽이 정한다"는 뜻.
 * 예를 들어 request<ExamSummary[]>(...) 라고 부르면, 반환값이 ExamSummary[] 타입이라고
 * TypeScript에게 알려주는 것. 실제 런타임 검증은 안 해주고 "타입상으로 이렇게 믿는다"는 선언일 뿐이라,
 * 서버 응답 형태가 바뀌면 이 타입 선언도 같이 고쳐줘야 한다.
 */
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };
  // 스프레드 문법(...)으로 여러 헤더 객체를 하나로 합친다. 뒤에 오는 값이 앞의 값을 덮어쓰므로,
  // 호출하는 쪽에서 options.headers로 개별 헤더를 넘기면 기본값을 오버라이드할 수 있는 구조.

  // --- 타임아웃 처리 ---
  // fetch()는 기본적으로 "서버가 응답을 아예 안 주면" 영원히 끝나지 않는다. 예전에 이 타임아웃이
  // 없어서, 서버가 느려지거나 요청이 중간에 끊기면 화면의 "채점 중..." 버튼이 영원히 그대로 멈춰
  // 있는 버그가 있었다(이후 요청을 새로 눌러도 반응 없음). AbortController가 그 문제를 해결하는
  // 브라우저 표준 방법이다: controller.signal을 fetch에 넘겨두면, controller.abort()를 부르는
  // 순간 그 fetch가 즉시 실패(AbortError)로 끝나도록 강제할 수 있다.
  const controller = new AbortController();
  const TIMEOUT_MS = 200000; // 200초 — 서버 최대 타임아웃(딥러닝 180초)보다 여유를 둬 응답 직전에 끊기는 경쟁 상태 방지
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,  // 이 fetch를 controller와 "연결"해서, abort() 호출에 반응하게 만든다
    });
    clearTimeout(timeoutId);  // 응답이 제때 왔으니, 예약해둔 타임아웃 타이머는 취소해서 불필요하게 남지 않게 한다
    if (!res.ok) {
      // res.ok = HTTP 상태 코드가 200번대인지 여부. fetch는 404/500이 와도 예외를 던지지 않고
      // 그냥 "응답"으로 취급하기 때문에, 우리가 직접 상태 코드를 확인해서 에러로 바꿔줘야 한다.
      throw new Error(`API 요청 실패 (${res.status}): ${path}`);
    }
    const data = await res.json();
    return data as T;
    // "as T"는 타입 단언(type assertion) — "이 값은 T 타입이 맞다"고 TypeScript에게 우겨서 알려주는 것.
    // 실제로 그런지 런타임에서 검사해주진 않는다(그게 필요하면 zod 같은 검증 라이브러리를 써야 한다).
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === 'AbortError') {
      // controller.abort()가 호출돼서 fetch가 실패하면, 에러의 name이 'AbortError'로 온다.
      // 이 경우를 따로 잡아서 "몇 초 안에 응답이 없었다"는 걸 사용자가 알아볼 수 있는 메시지로 바꿔준다.
      throw new Error(`요청 시간 초과 (${TIMEOUT_MS / 1000}초): ${path}`);
    }
    throw error;  // AbortError가 아닌 다른 에러(네트워크 끊김 등)는 그대로 호출한 쪽에 다시 던진다
  }
}

// --- 아래부터는 서버(app.py)가 주고받는 JSON의 "모양"을 TypeScript 타입으로 옮겨 적은 것들이다.
// FastAPI 쪽의 Pydantic 모델(RunRequest 등)이나 응답 딕셔너리와 필드 이름/타입을 반드시 맞춰야 한다
// — 서로 다른 언어(Python vs TypeScript)라서 자동으로 동기화되지 않고, 사람이 손으로 맞춰야 한다.

export interface ExamSummary {
  exam_id: string;
  title: string;
  time_limit_minutes: number;
  total_points_v1: number;
  problem_count: number;
}

export interface ExamProblem {
  no: number;
  session: string;
  prompt_markdown: string;
  points: number;
  answer_code_b64: string;
}

export interface ExamDetail {
  exam_id: string;
  title: string;
  time_limit_minutes: number;
  total_points_v1: number;
  setup_code: string;
  problems: ExamProblem[];
}

export interface RunResult {
  stdout: string;
  error: string | null;
  is_correct: boolean;
  detail: string;
  plots: string[];       // base64 PNG 문자열들의 배열 (worker.py의 _mock_show가 만든 것)
  points_earned: number;
}

export interface ChapterSummary {
  chapter_id: string;
  title: string;
  is_practice_only: boolean;
  section_count: number;
  practice_count: number;
}

export interface StudyPractice {
  no: number;
  prompt_markdown: string;
  starter_code: string;
  answer_code_b64: string;
}

export interface StudySection {
  no: number;
  title: string;
  theory_markdown: string;
  concept_table_markdown: string;
  example_code: string;
  practices: StudyPractice[];
}

export interface ChapterDetail {
  chapter_id: string;
  title: string;
  setup_code: string;
  sections: StudySection[];
}

export interface StudyRunResult {
  stdout: string;
  error: string | null;
  is_correct: boolean | null;  // 예제 코드 실행 결과는 채점 대상이 아니라서 null이 온다 (app.py 참고)
  detail: string | null;
  plots: string[];
}

// 이 프로젝트의 모든 컴포넌트/페이지가 실제로 import해서 쓰는 것은 바로 이 `api` 객체 하나다.
// 예: import { api } from "@/lib/api"; ... await api.getExam(examId)
export const api = {
  /** 서버를 미리 깨워두는 ping (Render free-tier cold start 방지용) */
  ping: () =>
    fetch(`${API_BASE}/api/ping`, {
      method: "GET",
      headers: API_KEY ? { "X-API-Key": API_KEY } : {},
      signal: AbortSignal.timeout(5000),
    }).catch(() => {}),

  listExams: () => request<ExamSummary[]>("/api/exams"),
  getExam: (examId: string) => request<ExamDetail>(`/api/exams/${encodeURIComponent(examId)}`),
  runProblem: (
    examId: string,
    body: { problem_no: number; current_code: string; code_by_problem: Record<string, string> }
  ) =>
    request<RunResult>(`/api/exams/${encodeURIComponent(examId)}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listChapters: () => request<ChapterSummary[]>("/api/study"),
  getChapter: (chapterId: string) => request<ChapterDetail>(`/api/study/${encodeURIComponent(chapterId)}`),
  runStudyUnit: (chapterId: string, body: { unit: number; current_code: string; code_by_unit: Record<string, string> }) =>
    request<StudyRunResult>(`/api/study/${encodeURIComponent(chapterId)}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
