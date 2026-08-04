"""
stdin으로 {"setup_code","code_by_problem","current_code","problem_no","checks","manual_review"}
JSON을 받아 문제 코드를 처음부터 재실행(엔진의 상태비저장 재실행 방식과 동일)하고,
채점 결과를 stdout에 JSON 한 줄로 출력한다.

데스크톱 버전(engine/code_executor.py)의 sys.settrace 기반 타임아웃은 Windows에 SIGALRM이
없고 matplotlib Figure를 프로세스 간에 넘기기 어려워서 택한 방식이었다. 여기서는 이 워커
자체가 이미 리눅스에서 별도 서브프로세스로 실행되므로, 부모(app.py)가 subprocess.run(timeout=...)
으로 감싸는 것만으로 진짜 SIGKILL 기반 하드 타임아웃이 되어 그 우회가 필요 없다. matplotlib
Figure도 base64 PNG로 바꿔 JSON에 실으면 되므로 피클링 문제 자체가 발생하지 않는다.
"""
import io
import os
import sys
import json
import base64
import contextlib
import traceback

import matplotlib
matplotlib.use("Agg")

# answer_code/checks 안의 경로는 전부 "data/train.csv"처럼 리포 루트 기준 상대경로다
# (데스크톱 버전이 AICE_Simulator 루트를 working_dir로 실행하는 것과 동일하게 맞춘다).
# 그래서 실제 csv/xlsx는 server/data/ 에 두고, cwd는 그 부모인 server/ 로 옮긴다.
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))


def build_full_code(setup_code, code_by_problem, current_code, problem_no):
    code_blocks = [setup_code or ""]
    for p_no in sorted(code_by_problem.keys(), key=int):
        if int(p_no) < problem_no:
            code_blocks.append(code_by_problem[p_no])
    code_blocks.append(current_code)
    return "\n".join(code_blocks)


def grade_problem(namespace, checks, manual_review):
    if manual_review and not checks:
        return True, "[본인이 직접 확인] 시각화 결과나 출력물을 직접 확인하세요."

    if not checks:
        return True, "✅ 정답입니다. (확인할 조건 없음)"

    for check in checks:
        var_name = check["var"]
        attr = check.get("attr", "")
        op = check.get("op", "eq")
        expected = check.get("expected")
        tolerance = check.get("tolerance", 1e-3)

        if var_name not in namespace:
            return False, f"❌ 변수 '{var_name}'를 찾을 수 없습니다."

        expr = f"{var_name}.{attr}" if attr else var_name
        try:
            actual = eval(expr, {}, namespace)

            if op == "eq":
                if isinstance(actual, tuple) and isinstance(expected, list):
                    actual = list(actual)
                if actual != expected:
                    return False, f"❌ '{expr}' 값이 일치하지 않습니다. (기대값: {expected}, 실제값: {actual})"
            elif op == "gte":
                if not (actual >= expected):
                    return False, f"❌ '{expr}' 값이 {expected} 이상이어야 합니다. (실제값: {actual})"
            elif op == "lte":
                if not (actual <= expected):
                    return False, f"❌ '{expr}' 값이 {expected} 이하여야 합니다. (실제값: {actual})"
            elif op == "close":
                if not _is_close(actual, expected, tolerance):
                    return False, f"❌ '{expr}' 값이 허용오차 내에 있지 않습니다. (기대값: {expected}, 실제값: {actual})"
        except Exception as e:
            return False, f"❌ '{expr}' 평가 중 에러 발생: {str(e)}"

    return True, "✅ 정답입니다."


def _is_close(actual, expected, tolerance):
    try:
        return abs(float(actual) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return actual == expected


def run(request):
    setup_code = request.get("setup_code", "")
    code_by_problem = request.get("code_by_problem", {})
    current_code = request["current_code"]
    problem_no = request["problem_no"]
    checks = request.get("checks", [])
    manual_review = request.get("manual_review", False)

    full_code = build_full_code(setup_code, code_by_problem, current_code, problem_no)

    namespace = {}
    stdout_capture = io.StringIO()
    plots = []

    # matplotlib.pyplot은 무겁기 때문에 실제로 필요할 때(= 이 subprocess 안)에만 import
    import matplotlib.pyplot as plt  # noqa: PLC0415

    def _mock_show(*args, **kwargs):
        fig = plt.gcf()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plots.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        plt.clf()

    plt.show = _mock_show

    error = None
    original_cwd = os.getcwd()
    try:
        os.chdir(WORKING_DIR)
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stdout_capture):
            exec(full_code, namespace)
    except Exception:
        error = traceback.format_exc()
        print(f"\n[Error]\n{error}", file=stdout_capture)
    finally:
        os.chdir(original_cwd)
        try:
            import matplotlib.pyplot as _plt
            _plt.close("all")
        except Exception:
            pass

    stdout_text = stdout_capture.getvalue()

    if error:
        is_correct = False
        detail = "❌ 코드 실행 중 에러가 발생하여 오답 처리되었습니다. (콘솔 확인)"
    else:
        is_correct, detail = grade_problem(namespace, checks, manual_review)

    return {
        "stdout": stdout_text,
        "error": error,
        "is_correct": is_correct,
        "detail": detail,
        "plots": plots,
    }


def main():
    request = json.load(sys.stdin)
    result = run(request)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
