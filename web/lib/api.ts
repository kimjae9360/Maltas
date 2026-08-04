const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8123";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 seconds timeout
  
  try {
    const res = await fetch(`${API_BASE}${path}`, { 
      ...options, 
      headers,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    if (!res.ok) {
      throw new Error(`API 요청 실패 (${res.status}): ${path}`);
    }
    return res.json() as Promise<T>;
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`요청 시간 초과 (30초): ${path}`);
    }
    throw error;
  }
}

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
  plots: string[];
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
  is_correct: boolean | null;
  detail: string | null;
  plots: string[];
}

export const api = {
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
  getAnswer: (examId: string, no: number) =>
    request<{ answer_code: string }>(`/api/exams/${encodeURIComponent(examId)}/problems/${no}/answer`),

  listChapters: () => request<ChapterSummary[]>("/api/study"),
  getChapter: (chapterId: string) => request<ChapterDetail>(`/api/study/${encodeURIComponent(chapterId)}`),
  runStudyUnit: (chapterId: string, body: { unit: number; current_code: string; code_by_unit: Record<string, string> }) =>
    request<StudyRunResult>(`/api/study/${encodeURIComponent(chapterId)}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getPracticeAnswer: (chapterId: string, unit: number) =>
    request<{ answer_code: string }>(`/api/study/${encodeURIComponent(chapterId)}/practice/${unit}/answer`),
};
