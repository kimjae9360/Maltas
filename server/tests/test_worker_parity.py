"""
server/worker.py가 데스크톱 엔진(engine/code_executor.py + engine/grader.py)과 동일하게 채점하는지
확인한다. tests/test_phase3.py와 같은 방식으로, 모든 모의고사의 모든 문제에 대해 정답 코드를
넣었을 때 전부 정답 처리되는지를 서브프로세스 워커를 통해 직접 검증한다.
"""
import os
import sys
import json
import glob
import subprocess

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_PATH = os.path.join(SERVER_DIR, "worker.py")
DATA_DIR = os.path.join(SERVER_DIR, "data")

EXAM_FILES = sorted(glob.glob(os.path.join(DATA_DIR, "모의고사*.json")))


def _run_worker(setup_code, code_by_problem, current_code, problem_no, checks, manual_review, timeout):
    payload = {
        "setup_code": setup_code,
        "code_by_problem": code_by_problem,
        "current_code": current_code,
        "problem_no": problem_no,
        "checks": checks,
        "manual_review": manual_review,
    }
    proc = subprocess.run(
        [sys.executable, WORKER_PATH],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=SERVER_DIR,
    )
    assert proc.returncode == 0, f"worker crashed: {proc.stderr}"
    return json.loads(proc.stdout)


@pytest.mark.parametrize("exam_path", EXAM_FILES, ids=[os.path.basename(p) for p in EXAM_FILES])
def test_full_exam_correct_answers(exam_path):
    with open(exam_path, "r", encoding="utf-8") as f:
        exam_data = json.load(f)

    code_by_problem = {}
    for p in exam_data["problems"]:
        code_by_problem[str(p["no"])] = p["answer_code"]

    for p in exam_data["problems"]:
        timeout = 180.0 if "딥러닝" in p.get("session", "") else 60.0
        result = _run_worker(
            exam_data.get("setup_code", ""),
            code_by_problem,
            p["answer_code"],
            p["no"],
            p.get("checks", []),
            p.get("manual_review", False),
            timeout=timeout,
        )

        assert result["is_correct"] is True, (
            f"[{os.path.basename(exam_path)}] problem {p['no']} failed grading. "
            f"detail={result['detail']} error={result['error']}"
        )

        if p.get("manual_review"):
            assert "[본인이 직접 확인]" in result["detail"]
