// 이 파일은 "브라우저 안에" 사용자의 응시/학습 기록을 저장하는 역할을 한다.
// 서버(apps/server)는 세션을 전혀 기억하지 않는 무상태(stateless) 서버라서 — 문제를 채점만
// 해줄 뿐 "누가 몇 번 문제까지 풀었는지"는 서버 메모리 어디에도 남지 않는다 — 그 진행 상황은
// 전부 이 사용자의 브라우저 안, IndexedDB라는 저장소에 저장된다. 그래서 로그인이 없어도
// "이어서 풀기"가 가능하고, 다른 사람의 서버 접속과 내 기록이 서로 섞이지 않는다.
// (대신 다른 기기/브라우저로 접속하면 기록이 안 보인다 — 이건 의도된 트레이드오프)
//
// IndexedDB는 브라우저에 내장된 저장소로, localStorage보다 훨씬 많은 용량을 다룰 수 있고
// 비동기(async)로 동작한다. 다만 원래 API가 콜백 기반이라 쓰기 번거로워서, `idb`라는 라이브러리로
// Promise 기반의 더 쓰기 편한 인터페이스를 씌워서 쓰고 있다.
import { openDB, DBSchema, IDBPDatabase } from "idb";

// --- 모의고사(exam) 세션에서 쓰는 타입들 ---

export interface GradedResult {
  is_correct: boolean;
  points_earned: number;
  detail: string;
  note?: string;   // 필드명 뒤의 "?"는 선택적(optional) 필드라는 뜻 — 없어도 되는 값
}

/** 모의고사 한 번 응시하는 것 = ExamSession 하나. 여기 담긴 값들이 통째로 IndexedDB에 저장된다. */
export interface ExamSession {
  sessionId: string;                       // 이 세션을 구분하는 고유 ID (아래 newSessionId로 생성)
  exam_id: string;                         // 어떤 시험인지 (서버의 exam_id와 대응)
  title: string;
  started_at: string;                      // 응시 시작 시각 (ISO 문자열, new Date().toISOString())
  elapsed_seconds: number;                 // 지금까지 흐른 시간 — 타이머 복원에 사용
  time_limit_minutes: number;
  total_points_v1: number;
  current_problem_no: number;
  code_by_problem: Record<string, string>; // { "1": "내가 짠 1번 문제 코드", "2": "...", ... }
  graded_results: Record<string, GradedResult>; // 문제 번호별 채점 결과 (오답노트/최종 리포트에 사용)
  flagged_problem_nos: number[];           // 사용자가 "나중에 다시 볼래요" 표시(깃발)해둔 문제 번호들
  revealed_problem_nos: number[];          // "정답 보기"를 눌러버린 문제 번호들 (이 문제는 0점 처리)
  is_submitted: boolean;                   // 최종 제출을 눌렀는지 — true가 되면 더 이상 수정 안 함
}

// --- 학습(study) 세션에서 쓰는 타입들 ---

export interface PracticeResult {
  is_correct: boolean;
  attempts: number;         // 몇 번 시도했는지 (학습 모드는 시험이 아니라 여러 번 시도 가능)
  revealed_answer: boolean; // 정답을 봤는지 — 복습 모드에서 "직접 못 푼 문제만 모아보기"에 쓰인다
}

/** 학습 챕터 하나를 공부하는 것 = StudySession 하나. */
export interface StudySession {
  sessionId: string;
  chapter_id: string;
  title: string;
  started_at: string;
  current_section_no: number;
  practice_code_by_unit: Record<string, string>;      // unit(섹션*100+문제번호) -> 작성한 코드
  practice_results_by_unit: Record<string, PracticeResult>;
  wrong_units: number[];        // 틀렸거나 정답을 본 unit들 — 복습 모드 대상
  completed_sections: number[];
  is_completed: boolean;        // 챕터를 끝까지 다 진행했는지
}

/**
 * IndexedDB에 만들 "데이터베이스"의 설계도(스키마)를 TypeScript 타입으로 미리 정의한 것.
 * DBSchema를 상속해서 이렇게 적어두면, idb 라이브러리가 db.get("examSessions", ...) 같은
 * 호출에서 자동으로 타입 체크/자동완성을 해준다 — "examSessions"라는 이름의 오브젝트 스토어에는
 * ExamSession 타입의 값만 들어갈 수 있고, key는 문자열이라는 걸 컴파일 시점에 강제하는 것.
 *
 * 참고로 "오브젝트 스토어(object store)"는 관계형 DB의 "테이블"과 비슷한 개념이라고 생각하면 된다.
 */
interface AiceDB extends DBSchema {
  examSessions: {
    key: string;
    value: ExamSession;
    indexes: { "by-exam": string };   // exam_id로 빠르게 검색하기 위한 보조 인덱스(색인)
  };
  studySessions: {
    key: string;
    value: StudySession;
    indexes: { "by-chapter": string };
  };
}

// DB 연결(openDB)은 시간이 걸리는 비동기 작업이라, 매번 새로 열지 않고 한 번 연 Promise를
// 이 모듈 전역 변수에 캐싱해서 재사용한다. (모듈은 브라우저에서 한 번만 로드되므로, 이 값은
// 페이지가 새로고침되기 전까지는 계속 같은 연결을 공유한다)
let dbPromise: Promise<IDBPDatabase<AiceDB>> | null = null;

function getDb() {
  if (!dbPromise) {
    dbPromise = openDB<AiceDB>("aice-simulator", 2, {
      // 두 번째 인자 2 = DB의 "버전 번호". 스키마(오브젝트 스토어 구조)를 바꿀 때마다 이 숫자를
      // 올려야 하고, 그러면 아래 upgrade 콜백이 자동으로 실행되어 마이그레이션을 할 수 있다.
      upgrade(db, oldVersion) {
        // oldVersion = 사용자의 브라우저에 이미 저장되어 있던 이전 DB 버전 (처음 방문이면 0).
        // 이렇게 "if (oldVersion < N)" 형태로 단계별로 나눠 적어두면, 버전을 하나씩 건너뛴
        // 사용자(예: 0 -> 2로 바로 업그레이드)도 누락 없이 모든 단계를 순서대로 거치게 된다.
        if (oldVersion < 1) {
          // v1: 모의고사 세션 저장 기능을 처음 추가했을 때 생긴 스토어
          const store = db.createObjectStore("examSessions", { keyPath: "sessionId" });
          // keyPath: "sessionId" = ExamSession 객체 안의 sessionId 필드를 그 레코드의 기본키로 쓴다
          store.createIndex("by-exam", "exam_id");
        }
        if (oldVersion < 2) {
          // v2: 나중에 학습 모드 진행기록 저장 기능을 추가하면서 생긴 스토어
          const store = db.createObjectStore("studySessions", { keyPath: "sessionId" });
          store.createIndex("by-chapter", "chapter_id");
        }
      },
    });
  }
  return dbPromise;
}

/** "exam_1735999999999_a1b2c3" 같은 형태의, 겹칠 일이 거의 없는 세션 ID를 만든다. */
function newSessionId(prefix: string) {
  // Date.now() = 현재 시각(밀리초) — 시간순 정렬에도 쓸 수 있고, 웬만해선 안 겹친다.
  // Math.random().toString(36) = 0~1 사이 난수를 36진수(0-9, a-z) 문자열로 바꿔서, 혹시라도
  // 같은 밀리초에 두 세션이 생성돼도 구분되도록 하는 보험.
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 모의고사 세션을 다루는 함수 모음. 페이지 컴포넌트들은 `examStorage.save(...)` 식으로 사용한다. */
export const examStorage = {
  /** 새 모의고사 응시를 시작할 때, 빈 상태의 세션 하나를 만들어 DB에 저장하고 돌려준다. */
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
    // db.put = 키가 이미 있으면 덮어쓰고, 없으면 새로 만드는 저장 방식(upsert). session.sessionId가
    // 방금 새로 만든 값이라 항상 "새로 만드는" 경우다.
    return session;
  },

  /** "이어서 풀기" 배너에 쓸, 아직 제출 안 하고 시간도 안 끝난 이 시험의 세션을 찾는다. */
  async findUnfinishedSession(examId: string): Promise<ExamSession | null> {
    const db = await getDb();
    const all = await db.getAllFromIndex("examSessions", "by-exam", examId);
    // by-exam 인덱스 덕분에, examSessions 전체를 다 뒤지지 않고 이 exam_id에 해당하는
    // 세션들만 바로 가져올 수 있다 (색인이 없었다면 매번 전체를 훑어야 했을 것).
    const unfinished = all
      .filter((s) => !s.is_submitted && s.elapsed_seconds < s.time_limit_minutes * 60)
      .sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
      // 시작 시각 내림차순 정렬 — 가장 "최근에 시작한" 미완료 세션을 맨 앞으로 오게 한다
    return unfinished[0] ?? null;
    // 배열이 비어있으면 unfinished[0]은 undefined인데, "?? null"로 undefined를 null로 바꿔서
    // 반환 타입(ExamSession | null)과 정확히 맞춘다.
  },

  async save(session: ExamSession) {
    const db = await getDb();
    await db.put("examSessions", session);
  },

  async get(sessionId: string): Promise<ExamSession | undefined> {
    const db = await getDb();
    return db.get("examSessions", sessionId);
  },

  /** 히스토리 페이지에서 "지금까지 응시한 모든 시험 기록"을 보여줄 때 쓴다. */
  async listAll(): Promise<ExamSession[]> {
    const db = await getDb();
    return db.getAll("examSessions");
  },
};

/** 학습 세션을 다루는 함수 모음. 구조는 examStorage와 거의 동일한 패턴이다. */
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

  /** 학습 모드는 "완료 여부"와 상관없이 그냥 가장 최근 세션을 이어서 보여준다(시험처럼 마감이 없어서). */
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
