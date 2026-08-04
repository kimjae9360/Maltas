import { openDB, DBSchema, IDBPDatabase } from "idb";

export interface GradedResult {
  is_correct: boolean;
  points_earned: number;
  detail: string;
  note?: string;
}

export interface ExamSession {
  sessionId: string;
  exam_id: string;
  title: string;
  started_at: string;
  elapsed_seconds: number;
  time_limit_minutes: number;
  total_points_v1: number;
  current_problem_no: number;
  code_by_problem: Record<string, string>;
  graded_results: Record<string, GradedResult>;
  flagged_problem_nos: number[];
  revealed_problem_nos: number[];
  is_submitted: boolean;
}

export interface PracticeResult {
  is_correct: boolean;
  attempts: number;
  revealed_answer: boolean;
}

export interface StudySession {
  sessionId: string;
  chapter_id: string;
  title: string;
  started_at: string;
  current_section_no: number;
  practice_code_by_unit: Record<string, string>;
  practice_results_by_unit: Record<string, PracticeResult>;
  wrong_units: number[];
  completed_sections: number[];
  is_completed: boolean;
}

interface AiceDB extends DBSchema {
  examSessions: {
    key: string;
    value: ExamSession;
    indexes: { "by-exam": string };
  };
  studySessions: {
    key: string;
    value: StudySession;
    indexes: { "by-chapter": string };
  };
}

let dbPromise: Promise<IDBPDatabase<AiceDB>> | null = null;

function getDb() {
  if (!dbPromise) {
    dbPromise = openDB<AiceDB>("aice-simulator", 2, {
      upgrade(db, oldVersion) {
        if (oldVersion < 1) {
          const store = db.createObjectStore("examSessions", { keyPath: "sessionId" });
          store.createIndex("by-exam", "exam_id");
        }
        if (oldVersion < 2) {
          const store = db.createObjectStore("studySessions", { keyPath: "sessionId" });
          store.createIndex("by-chapter", "chapter_id");
        }
      },
    });
  }
  return dbPromise;
}

function newSessionId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export const examStorage = {
  async createSession(examId: string, title: string, timeLimitMinutes: number, totalPoints: number): Promise<ExamSession> {
    const session: ExamSession = {
      sessionId: newSessionId("exam"),
      exam_id: examId,
      title,
      started_at: new Date().toISOString(),
      elapsed_seconds: 0,
      time_limit_minutes: timeLimitMinutes,
      total_points_v1: totalPoints,
      current_problem_no: 1,
      code_by_problem: {},
      graded_results: {},
      flagged_problem_nos: [],
      revealed_problem_nos: [],
      is_submitted: false,
    };
    const db = await getDb();
    await db.put("examSessions", session);
    return session;
  },

  async findUnfinishedSession(examId: string): Promise<ExamSession | null> {
    const db = await getDb();
    const all = await db.getAllFromIndex("examSessions", "by-exam", examId);
    const unfinished = all
      .filter((s) => !s.is_submitted && s.elapsed_seconds < s.time_limit_minutes * 60)
      .sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
    return unfinished[0] ?? null;
  },

  async save(session: ExamSession) {
    const db = await getDb();
    await db.put("examSessions", session);
  },

  async get(sessionId: string): Promise<ExamSession | undefined> {
    const db = await getDb();
    return db.get("examSessions", sessionId);
  },

  async listAll(): Promise<ExamSession[]> {
    const db = await getDb();
    return db.getAll("examSessions");
  },
};

export const studyStorage = {
  async createSession(chapterId: string, title: string): Promise<StudySession> {
    const session: StudySession = {
      sessionId: newSessionId("study"),
      chapter_id: chapterId,
      title,
      started_at: new Date().toISOString(),
      current_section_no: 1,
      practice_code_by_unit: {},
      practice_results_by_unit: {},
      wrong_units: [],
      completed_sections: [],
      is_completed: false,
    };
    const db = await getDb();
    await db.put("studySessions", session);
    return session;
  },

  async findLatestSession(chapterId: string): Promise<StudySession | null> {
    const db = await getDb();
    const all = await db.getAllFromIndex("studySessions", "by-chapter", chapterId);
    const sorted = all.sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
    return sorted[0] ?? null;
  },

  async save(session: StudySession) {
    const db = await getDb();
    await db.put("studySessions", session);
  },

  async listAll(): Promise<StudySession[]> {
    const db = await getDb();
    return db.getAll("studySessions");
  },
};
