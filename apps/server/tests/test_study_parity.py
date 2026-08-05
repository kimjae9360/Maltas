"""
server/worker.py가 학습 모드(study_*.json)의 모든 챕터·섹션·TODO에 대해서도 answer_code를
넣었을 때 전부 정답 처리되는지 확인한다. test_worker_parity.py(모의고사용)의 학습모드 버전.

각 섹션의 example_code(unit = section_no*100)와 각 practice의 answer_code
(unit = section_no*100 + practice_no)를 전부 모아 code_by_unit으로 넘기고, app.py의
run_study_unit과 동일한 방식(_run_worker(..., problem_no=unit, ...))으로 채점을 재현한다.
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

STUDY_FILES = sorted(glob.glob(os.path.join(DATA_DIR, "study_*.json")))


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


def _unit(section_no, practice_no=0):
    return section_no * 100 + practice_no


@pytest.mark.parametrize("chapter_path", STUDY_FILES, ids=[os.path.basename(p) for p in STUDY_FILES])
def test_full_chapter_correct_answers(chapter_path):
    with open(chapter_path, "r", encoding="utf-8") as f:
        chapter = json.load(f)

    code_by_unit = {}
    for s in chapter["sections"]:
        code_by_unit[str(_unit(s["no"]))] = s.get("example_code", "")
        for p in s["practices"]:
            code_by_unit[str(_unit(s["no"], p["no"]))] = p["answer_code"]

    is_deep_learning = "딥러닝" in chapter["chapter_id"]
    timeout = 180.0 if is_deep_learning else 90.0

    for s in chapter["sections"]:
        for p in s["practices"]:
            unit = _unit(s["no"], p["no"])
            result = _run_worker(
                chapter.get("setup_code", ""),
                code_by_unit,
                p["answer_code"],
                unit,
                p.get("checks", []),
                p.get("manual_review", False),
                timeout=timeout,
            )
            assert result["is_correct"] is True, (
                f"[{os.path.basename(chapter_path)}] section {s['no']} practice {p['no']} "
                f"(unit={unit}) failed grading. detail={result['detail']} error={result['error']}"
            )
            if p.get("manual_review"):
                assert "[본인이 직접 확인]" in result["detail"]
