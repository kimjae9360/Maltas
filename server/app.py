"""
AICE_Simulator 모의고사 실행/채점 API.

이 API는 임의의 파이썬 코드를 그대로 실행하는 엔드포인트를 인터넷에 노출한다. X-API-Key는
"진짜 보안"이 아니라 무차별 스캔 방지용 최소 방어선이다(프론트 번들에 값이 들어가므로 네트워크
탭을 보면 누구나 꺼낼 수 있다). URL을 공개적으로 퍼뜨리기 전에는 반드시 더 강한 인증으로
교체해야 한다.
"""
import os
import sys
import json
import glob
import subprocess

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SERVER_DIR, "data")
WORKER_PATH = os.path.join(SERVER_DIR, "worker.py")

API_KEY = os.environ.get("AICE_API_KEY", "")
ALLOWED_ORIGINS = [o for o in os.environ.get("AICE_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o]

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AICE Simulator API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _load_json_dir(pattern, key_field):
    items = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, pattern))):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items[data[key_field]] = data
    return items


EXAMS = _load_json_dir("모의고사*.json", "exam_id")
CHAPTERS = _load_json_dir("study_*.json", "chapter_id")


def _run_worker(setup_code, code_by_problem, current_code, problem_no, checks, manual_review, timeout):
    worker_input = {
        "setup_code": setup_code,
        "code_by_problem": code_by_problem,
        "current_code": current_code,
        "problem_no": problem_no,
        "checks": checks,
        "manual_review": manual_review,
    }
    try:
        proc = subprocess.run(
            [sys.executable, WORKER_PATH],
            input=json.dumps(worker_input),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SERVER_DIR,
        )
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "error": f"Execution timed out ({int(timeout)}s limit).",
            "is_correct": False,
            "detail": "⏱️ 서버 응답 시간이 초과되었습니다. 다시 시도해주세요. (서버 첫 실행 시 워밍업으로 인해 느릴 수 있습니다)",
            "plots": [],
        }

    if proc.returncode != 0:
        return {
            "stdout": proc.stdout,
            "error": proc.stderr or "worker process crashed",
            "is_correct": False,
            "detail": "❌ 코드 실행 중 서버 오류가 발생하여 오답 처리되었습니다.",
            "plots": [],
        }

    return json.loads(proc.stdout)


def require_api_key(x_api_key: str = Header(default="")):
    if not API_KEY:
        # 로컬 개발 중 AICE_API_KEY가 설정 안 되어 있으면 인증을 건너뛴다.
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")


def _get_exam(exam_id: str) -> dict:
    exam = EXAMS.get(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="exam not found")
    return exam


def _get_problem(exam: dict, no: int) -> dict:
    for p in exam["problems"]:
        if p["no"] == no:
            return p
    raise HTTPException(status_code=404, detail="problem not found")


def _public_exam(exam: dict) -> dict:
    return {
        "exam_id": exam["exam_id"],
        "title": exam["title"],
        "time_limit_minutes": exam["time_limit_minutes"],
        "total_points_v1": exam["total_points_v1"],
        "setup_code": exam.get("setup_code", ""),
        "problems": [
            {"no": p["no"], "session": p["session"], "prompt_markdown": p["prompt_markdown"], "points": p["points"]}
            for p in exam["problems"]
        ],
    }


@app.get("/api/exams")
def list_exams(_: None = Depends(require_api_key)):
    return [
        {
            "exam_id": e["exam_id"],
            "title": e["title"],
            "time_limit_minutes": e["time_limit_minutes"],
            "total_points_v1": e["total_points_v1"],
            "problem_count": len(e["problems"]),
        }
        for e in EXAMS.values()
    ]


@app.get("/api/exams/{exam_id}")
def get_exam(exam_id: str, _: None = Depends(require_api_key)):
    return _public_exam(_get_exam(exam_id))


class RunRequest(BaseModel):
    problem_no: int
    current_code: str
    code_by_problem: dict[str, str] = {}


@app.post("/api/exams/{exam_id}/run")
@limiter.limit("20/minute")
def run_problem(exam_id: str, body: RunRequest, request: Request, _: None = Depends(require_api_key)):
    exam = _get_exam(exam_id)
    problem = _get_problem(exam, body.problem_no)

    timeout = 180.0 if "딥러닝" in problem.get("session", "") else 90.0

    result = _run_worker(
        exam.get("setup_code", ""),
        body.code_by_problem,
        body.current_code,
        body.problem_no,
        problem.get("checks", []),
        problem.get("manual_review", False),
        timeout,
    )
    result["points_earned"] = problem["points"] if result["is_correct"] else 0
    return result


@app.get("/api/exams/{exam_id}/problems/{no}/answer")
def get_answer(exam_id: str, no: int, _: None = Depends(require_api_key)):
    exam = _get_exam(exam_id)
    problem = _get_problem(exam, no)
    return {"answer_code": problem["answer_code"]}


# ---- 학습 모드 (이론 공부 / 실무 연습) ----
# 데스크톱(ui/study_window.py)과 동일한 "unit index" 방식을 그대로 쓴다:
# section_no*100 + practice_no (practice_no=0은 그 섹션의 예제 코드).


def _get_chapter(chapter_id: str) -> dict:
    chapter = CHAPTERS.get(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    return chapter


def _public_chapter(chapter: dict) -> dict:
    return {
        "chapter_id": chapter["chapter_id"],
        "title": chapter["title"],
        "setup_code": chapter.get("setup_code", ""),
        "sections": [
            {
                "no": s["no"],
                "title": s["title"],
                "theory_markdown": s.get("theory_markdown", ""),
                "concept_table_markdown": s.get("concept_table_markdown", ""),
                "example_code": s.get("example_code", ""),
                "practices": [
                    {"no": p["no"], "prompt_markdown": p["prompt_markdown"], "starter_code": p.get("starter_code", "")}
                    for p in s["practices"]
                ],
            }
            for s in chapter["sections"]
        ],
    }


def _find_section_practice(chapter: dict, unit: int):
    section_no, practice_no = divmod(unit, 100)
    section = next((s for s in chapter["sections"] if s["no"] == section_no), None)
    if not section:
        raise HTTPException(status_code=404, detail="section not found")
    if practice_no == 0:
        return section, None
    practice = next((p for p in section["practices"] if p["no"] == practice_no), None)
    if not practice:
        raise HTTPException(status_code=404, detail="practice not found")
    return section, practice


@app.get("/api/study")
def list_chapters(_: None = Depends(require_api_key)):
    return [
        {
            "chapter_id": c["chapter_id"],
            "title": c["title"],
            "is_practice_only": c["chapter_id"].endswith("_실무전용"),
            "section_count": len(c["sections"]),
            "practice_count": sum(len(s["practices"]) for s in c["sections"]),
        }
        for c in CHAPTERS.values()
    ]


@app.get("/api/study/{chapter_id}")
def get_chapter(chapter_id: str, _: None = Depends(require_api_key)):
    return _public_chapter(_get_chapter(chapter_id))


class StudyRunRequest(BaseModel):
    unit: int
    current_code: str
    code_by_unit: dict[str, str] = {}


@app.post("/api/study/{chapter_id}/run")
@limiter.limit("20/minute")
def run_study_unit(chapter_id: str, body: StudyRunRequest, request: Request, _: None = Depends(require_api_key)):
    chapter = _get_chapter(chapter_id)
    section, practice = _find_section_practice(chapter, body.unit)

    is_deep_learning = "딥러닝" in chapter_id
    timeout = 180.0 if is_deep_learning else 90.0

    checks = practice.get("checks", []) if practice else []
    manual_review = practice.get("manual_review", False) if practice else True  # 예제 실행은 항상 통과 처리

    result = _run_worker(
        chapter.get("setup_code", ""),
        body.code_by_unit,
        body.current_code,
        body.unit,
        checks,
        manual_review,
        timeout,
    )
    if practice is None:
        # 예제 코드는 채점 대상이 아니라 실행 결과 확인용이다.
        result["is_correct"] = None
        result["detail"] = None
    return result


@app.get("/api/study/{chapter_id}/practice/{unit}/answer")
def get_practice_answer(chapter_id: str, unit: int, _: None = Depends(require_api_key)):
    chapter = _get_chapter(chapter_id)
    section, practice = _find_section_practice(chapter, unit)
    if not practice:
        raise HTTPException(status_code=400, detail="example code has no answer")
    return {"answer_code": practice["answer_code"]}
