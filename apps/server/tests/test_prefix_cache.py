"""
worker.py의 prefix 캐싱(직전 문제까지의 실행 상태를 재사용하는 최적화)이 실제로 동작하고,
캐시를 쓰든 안 쓰든 채점 결과가 완전히 똑같은지 확인한다.

test_worker_parity.py/test_study_parity.py는 문제마다 새 서브프로세스를 띄워서 확인하는데,
그러면 _PREFIX_CACHE가 매번 빈 상태로 시작해서 캐시 "적중(hit)" 경로 자체가 한 번도 실행되지
않는다(항상 처음부터 다시 실행하는 "미스" 경로만 테스트됨). 이 파일은 worker 모듈을 직접
import해서 같은 프로세스 안에서 run()을 여러 번 호출해, 실제로 캐시가 적중하는 상황을
재현하고 검증한다.
"""
import os
import sys
import json
import glob
import time

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)
os.chdir(SERVER_DIR)

import worker  # noqa: E402


def _load_exam(name):
    path = os.path.join(SERVER_DIR, "data", name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_cache_hit_matches_cache_miss_result():
    exam = _load_exam("모의고사01_Titanic_생존자예측.json")
    problems = {p["no"]: p for p in exam["problems"]}
    setup_code = exam.get("setup_code", "")

    # 문제 1~3의 정답 코드를 code_by_problem으로 준비 (4번을 채점할 때의 prefix로 쓰인다)
    code_by_problem = {str(no): problems[no]["answer_code"] for no in (1, 2, 3)}
    target = problems[4]

    worker._PREFIX_CACHE.update({"key": None, "namespace": None, "stdout": "", "plots": []})

    request = {
        "setup_code": setup_code,
        "code_by_problem": code_by_problem,
        "current_code": target["answer_code"],
        "problem_no": 4,
        "checks": target.get("checks", []),
        "manual_review": target.get("manual_review", False),
    }

    t0 = time.time()
    first = worker.run(request)  # 캐시 미스: 1~3번을 처음부터 실행
    miss_elapsed = time.time() - t0
    assert worker._PREFIX_CACHE["key"] is not None, "캐시가 저장되지 않았다"

    t0 = time.time()
    second = worker.run(request)  # 캐시 히트: 같은 prefix라 1~3번 재실행을 건너뛰어야 함
    hit_elapsed = time.time() - t0

    assert first["is_correct"] is True, first["detail"]
    assert second["is_correct"] is True, second["detail"]
    assert first["is_correct"] == second["is_correct"]
    assert first["detail"] == second["detail"]
    assert first["stdout"] == second["stdout"], "콘솔 출력이 캐시 사용 전후로 달라지면 안 된다"
    assert first["plots"] == second["plots"]

    print(f"\n[cache miss] {miss_elapsed:.2f}s -> [cache hit] {hit_elapsed:.2f}s")
    assert hit_elapsed < miss_elapsed, "캐시를 썼는데 오히려 느리거나 같으면 최적화 의미가 없다"


def test_cache_miss_when_prefix_changes():
    """앞 문제 코드가 한 글자라도 바뀌면 캐시를 못 쓰고 처음부터 다시 실행돼야 한다(정확성 우선)."""
    exam = _load_exam("모의고사01_Titanic_생존자예측.json")
    problems = {p["no"]: p for p in exam["problems"]}
    setup_code = exam.get("setup_code", "")
    target = problems[4]

    worker._PREFIX_CACHE.update({"key": None, "namespace": None, "stdout": "", "plots": []})

    base_code_by_problem = {str(no): problems[no]["answer_code"] for no in (1, 2, 3)}
    worker.run({
        "setup_code": setup_code,
        "code_by_problem": base_code_by_problem,
        "current_code": target["answer_code"],
        "problem_no": 4,
        "checks": target.get("checks", []),
        "manual_review": target.get("manual_review", False),
    })
    cached_key_before = worker._PREFIX_CACHE["key"]

    # 3번 문제 코드 뒤에 주석 한 줄만 추가 — prefix 텍스트가 달라지므로 해시도 달라져야 한다
    changed_code_by_problem = dict(base_code_by_problem)
    changed_code_by_problem["3"] = changed_code_by_problem["3"] + "\n# changed"

    prefix = worker.build_prefix_code(setup_code, changed_code_by_problem, 4)
    import hashlib
    new_key = hashlib.sha256(prefix.encode("utf-8")).hexdigest()
    assert new_key != cached_key_before, "prefix 코드가 달라졌는데 해시가 같으면 캐시 키 로직이 잘못된 것"

    result = worker.run({
        "setup_code": setup_code,
        "code_by_problem": changed_code_by_problem,
        "current_code": target["answer_code"],
        "problem_no": 4,
        "checks": target.get("checks", []),
        "manual_review": target.get("manual_review", False),
    })
    assert result["is_correct"] is True, result["detail"]
