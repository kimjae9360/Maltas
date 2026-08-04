"""
stdin으로 {"setup_code","code_by_problem","current_code","problem_no","checks","manual_review"}
JSON을 받아 문제 코드를 처음부터 재실행(엔진의 상태비저장 재실행 방식과 동일)하고,
채점 결과를 stdout에 JSON 한 줄로 출력한다.

데스크톱 버전(engine/code_executor.py)의 sys.settrace 기반 타임아웃은 Windows에 SIGALRM이
없고 matplotlib Figure를 프로세스 간에 넘기기 어려워서 택한 방식이었다. 여기서는 이 워커
자체가 이미 리눅스에서 별도 서브프로세스로 실행되므로, 부모(app.py)가 subprocess.run(timeout=...)
으로 감싸는 것만으로 진짜 SIGKILL 기반 하드 타임아웃이 되어 그 우회가 필요 없다. matplotlib
Figure도 base64 PNG로 바꿔 JSON에 실으면 되므로 피클링 문제 자체가 발생하지 않는다.

--- 공부용 요약 ---
이 파일은 "사용자가 코드 에디터에 입력한 파이썬 코드"를 실제로 돌려보고 채점하는,
이 서비스에서 가장 핵심적인 부분입니다. 크게 3단계로 이루어져 있어요.
  1) build_full_code : 지금까지 푼 문제들의 코드를 전부 이어붙여서 "완전한 하나의 스크립트"를 만든다
  2) run             : 그 스크립트를 exec()로 실제 실행하고, 출력/그래프/에러를 수집한다
  3) grade_problem   : 실행이 끝난 뒤 남은 변수 값들을 정답 조건(checks)과 비교해 채점한다
"""
import io
import os
import sys
import json
import base64
import contextlib
import traceback

import matplotlib
matplotlib.use("Agg")  # 화면(GUI) 없는 서버 환경에서도 그래프를 그릴 수 있게 하는 matplotlib 백엔드.
# "Agg"는 화면에 띄우는 대신 이미지 파일(메모리 버퍼)로만 그려주는 렌더러라, 서버처럼
# 모니터가 없는 환경에서 필수로 설정해야 한다. 이 줄이 없으면 서버에서 matplotlib import 시 에러가 난다.

# answer_code/checks 안의 경로는 전부 "data/train.csv"처럼 리포 루트 기준 상대경로다
# (데스크톱 버전이 AICE_Simulator 루트를 working_dir로 실행하는 것과 동일하게 맞춘다).
# 그래서 실제 csv/xlsx는 server/data/ 에 두고, cwd는 그 부모인 server/ 로 옮긴다.
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))
# __file__ = 이 worker.py 파일 자신의 경로. os.path.abspath로 절대경로로 바꾸고,
# os.path.dirname으로 "이 파일이 들어있는 폴더"만 뽑아낸다.
# 이렇게 "내 위치를 기준으로" 경로를 계산해두면, 나중에 이 폴더(apps/server) 전체를
# 다른 곳으로 옮기거나 이름을 바꿔도 코드를 고칠 필요가 없다 (실제로 최근에 server/ -> apps/server/로
# 옮겼을 때도 이 코드는 한 글자도 안 고쳤다).


def build_full_code(setup_code, code_by_problem, current_code, problem_no):
    """"지금까지 푼 모든 문제의 코드를 하나로 이어붙여서" 완전한 스크립트를 만든다.

    왜 이렇게 할까?
    이 앱은 문제 1번의 df = pd.read_csv(...) 같은 코드에서 만든 변수 df를,
    2번·3번 문제에서도 이어서 쓸 수 있어야 한다(실제 시험도 그렇다). 그런데 서버는
    "요청 하나 = 파이썬 프로세스 하나 실행"이라 문제마다 완전히 새로운 상태에서 시작한다.
    그래서 매번 "setup_code(공통 준비 코드) + 이전 문제들의 코드 + 지금 채점할 코드"를
    처음부터 순서대로 다시 실행해서, "마치 쭉 이어서 푼 것처럼" 상태를 복원하는 것이다.
    (조금 비효율적으로 보이지만, 세션을 서버 메모리에 들고 있지 않아도 되므로 훨씬 단순하고 안전하다.)

    problem_no보다 번호가 작은 문제의 코드만 붙이는 이유: 지금 채점하려는 문제 자신의 코드는
    맨 마지막의 current_code로 따로 넣기 때문에, 여기서 또 넣으면 중복 실행된다.
    """
    code_blocks = [setup_code or ""]
    for p_no in sorted(code_by_problem.keys(), key=int):
        # code_by_problem의 key는 JSON이라 전부 문자열("1", "2", ...)이다.
        # 문자열끼리 비교하면 "10" < "2"가 되어버리므로(사전순 비교), key=int로 숫자 기준 정렬해야 한다.
        if int(p_no) < problem_no:
            code_blocks.append(code_by_problem[p_no])
    code_blocks.append(current_code)
    return "\n".join(code_blocks)


def grade_problem(namespace, checks, manual_review):
    """코드를 실행하고 난 뒤 남은 변수들(namespace)을 정답 조건(checks)과 하나씩 비교해 채점한다.

    namespace: exec()가 코드를 실행하면서 만든 변수들이 전부 담기는 딕�너리.
               예를 들어 코드에 `df = pd.read_csv(...)`가 있었다면 namespace['df']로 접근 가능.
    checks:    [{"var": "df", "attr": "shape", "op": "eq", "expected": [891, 12]}, ...] 형태의 리스트.
               "채점 정답지" 역할 — 문제 JSON을 만들 때 미리 생성해둔 것.
    manual_review: 자동으로 값을 비교하기 애매한 문제(예: 그래프를 잘 그렸는지)는 checks 없이
               "사람이 직접 보고 판단"하도록 True로 표시해둔다.
    """
    if manual_review and not checks:
        return True, "[본인이 직접 확인] 시각화 결과나 출력물을 직접 확인하세요."

    if not checks:
        # 채점 조건이 아예 없는 문제(예제 코드 실행 등)는 "에러만 안 나면 통과"로 처리.
        return True, "✅ 정답입니다. (확인할 조건 없음)"

    for check in checks:
        var_name = check["var"]
        attr = check.get("attr", "")             # 예: "shape", "score" 처럼 변수의 속성/메서드 결과를 볼 때
        op = check.get("op", "eq")                # 비교 방식: eq(같다) / gte(이상) / lte(이하) / close(오차범위 내)
        expected = check.get("expected")          # 정답 값
        tolerance = check.get("tolerance", 1e-3)  # close 비교일 때 허용 오차

        if var_name not in namespace:
            # 채점하려는 변수 자체가 없다 = 사용자가 그 변수를 안 만들었다(문제를 안 풀었거나 변수명이 다름)
            return False, f"❌ 변수 '{var_name}'를 찾을 수 없습니다."

        expr = f"{var_name}.{attr}" if attr else var_name
        try:
            # eval(expr, {}, namespace): 문자열로 된 expr("df.shape" 등)을 실제 파이썬 코드처럼 평가한다.
            # 두 번째 인자(globals)를 빈 딕셔너리로 주는 이유: eval이 참조할 수 있는 전역 이름을 최소화해서
            # 채점 코드가 사용자 코드의 예상치 못한 전역 변수에 휘둘리지 않게 하기 위함. 실제 변수는 세 번째
            # 인자(locals)로 넘긴 namespace 안에서만 찾는다.
            actual = eval(expr, {}, namespace)

            if op == "eq":
                # (1, 2) 같은 튜플과 [1, 2] 같은 리스트는 파이썬에서 값이 같아도 "!="로 나온다.
                # JSON에는 튜플이 없어서 expected는 항상 리스트로 저장되므로, actual이 튜플이면
                # 비교 전에 리스트로 바꿔서 공평하게 비교한다. (예: df.shape는 튜플 (891, 12)를 반환)
                if isinstance(actual, tuple) and isinstance(expected, list):
                    actual = list(actual)
                if actual != expected:
                    return False, f"❌ '{expr}' 값이 일치하지 않습니다. (기대값: {expected}, 실제값: {actual})"
            elif op == "gte":
                # 정확히 값을 맞히기보단 "이 정도 성능 이상이면 정답" 식의 채점(정확도 등)에 사용
                if not (actual >= expected):
                    return False, f"❌ '{expr}' 값이 {expected} 이상이어야 합니다. (실제값: {actual})"
            elif op == "lte":
                if not (actual <= expected):
                    return False, f"❌ '{expr}' 값이 {expected} 이하여야 합니다. (실제값: {actual})"
            elif op == "close":
                # 부동소수점 계산은 라이브러리 버전/실행 환경에 따라 아주 미세하게 값이 달라질 수 있어서,
                # 완전히 똑같은 값이 아니라 "허용 오차(tolerance) 안에 들어오면 정답"으로 처리한다.
                if not _is_close(actual, expected, tolerance):
                    return False, f"❌ '{expr}' 값이 허용오차 내에 있지 않습니다. (기대값: {expected}, 실제값: {actual})"
        except Exception as e:
            # eval 자체가 실패하는 경우(예: attr 이름이 잘못됐거나 타입이 안 맞음)도 오답 처리하되,
            # 서버가 죽지 않도록 여기서 예외를 잡아 에러 메시지로 바꿔서 돌려준다.
            return False, f"❌ '{expr}' 평가 중 에러 발생: {str(e)}"

    # 모든 check를 통과해야 여기까지 도달한다.
    return True, "✅ 정답입니다."


def _is_close(actual, expected, tolerance):
    """실수(float) 두 값이 tolerance 오차 범위 안에서 "거의 같은지" 비교한다."""
    try:
        return abs(float(actual) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        # float으로 변환이 안 되는 값(문자열 등)이면 오차 비교가 의미 없으니 그냥 완전 일치로 대체.
        return actual == expected


def run(request):
    """이 워커의 진짜 메인 로직. app.py가 이 함수 하나만 호출한다.

    처리 순서: ① 코드 합치기 → ② 실제로 exec() 실행(출력/그래프 캡처) → ③ 채점 → ④ 결과 딕셔너리 반환.
    """
    setup_code = request.get("setup_code", "")
    code_by_problem = request.get("code_by_problem", {})
    current_code = request["current_code"]
    problem_no = request["problem_no"]
    checks = request.get("checks", [])
    manual_review = request.get("manual_review", False)

    full_code = build_full_code(setup_code, code_by_problem, current_code, problem_no)

    namespace = {}                    # exec()가 실행되면서 만드는 변수들이 여기 쌓인다 (= 코드의 "실행 결과 상태")
    stdout_capture = io.StringIO()    # print() 출력을 화면 대신 메모리로 가로채기 위한 가짜 파일 객체
    plots = []                        # plt.show()를 부를 때마다 캡처된 그래프 이미지(base64 PNG)들이 쌓인다

    # matplotlib.pyplot은 무겁기 때문에 실제로 필요할 때(= 이 subprocess 안)에만 import
    import matplotlib.pyplot as plt  # noqa: PLC0415

    def _mock_show(*args, **kwargs):
        """사용자 코드가 plt.show()를 호출하면, 실제로 창을 띄우는 대신 이 함수가 대신 실행된다.

        서버에는 화면이 없어서 plt.show()가 원래 하는 일(창 띄우기)을 할 수 없다. 대신 지금 그려진
        그래프(plt.gcf() = get current figure)를 PNG 이미지로 저장한 뒤, base64 문자열로 바꿔서
        plots 리스트에 담아둔다. base64로 바꾸는 이유는 이미지(바이너리)를 JSON 응답 안에 텍스트로
        실어 보내기 위함 — HTTP 응답은 JSON이라 순수 바이너리를 그대로 넣을 수 없다.
        프론트엔드는 이 문자열을 <img src="data:image/png;base64,..."> 형태로 그대로 렌더링한다.
        """
        fig = plt.gcf()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plots.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        plt.clf()  # 다음 문제/다음 그래프를 위해 현재 그림(figure)을 깨끗이 비운다(안 하면 그래프가 겹쳐 그려짐)

    plt.show = _mock_show  # matplotlib의 원래 show 함수를 위 가짜 함수로 "몽키패치"(런타임에 갈아끼움)

    error = None
    original_cwd = os.getcwd()
    try:
        # 사용자 코드 안의 pd.read_csv("data/train.csv") 같은 상대경로가 제대로 찾아지도록,
        # 실행 직전에 현재 작업 폴더(cwd)를 이 워커 파일이 있는 apps/server/ 로 바꾼다.
        os.chdir(WORKING_DIR)
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stdout_capture):
            # exec(코드문자열, namespace): 문자열로 된 파이썬 코드를 실제로 실행한다.
            # namespace를 globals 자리에 넘기면, 코드 안에서 만들어지는 모든 변수가 이 딕셔너리에 쌓인다
            # (그래서 실행이 끝난 뒤 grade_problem이 namespace를 보고 채점할 수 있는 것).
            exec(full_code, namespace)
    except Exception:
        # 사용자 코드에 문법 오류나 런타임 에러(예: 없는 컬럼 접근)가 있으면 여기서 잡힌다.
        # 서버 프로세스 자체는 죽지 않고, 에러 내용을 문자열로 저장해서 "오답 + 에러 메시지"로 응답한다.
        error = traceback.format_exc()
        print(f"\n[Error]\n{error}", file=stdout_capture)
    finally:
        # 성공하든 실패하든 반드시 실행되어야 하는 뒷정리 구간.
        os.chdir(original_cwd)  # cwd를 원래대로 되돌려놓는다 (다음 요청에 영향 안 주도록)
        try:
            import matplotlib.pyplot as _plt
            _plt.close("all")  # 열려있는 모든 figure를 닫아 메모리 누수 방지
        except Exception:
            pass

        # 딥러닝(Keras) 메모리 누수 방지: tf가 로드되어 있다면 세션을 초기화해 OOM 방지
        # (tensorflow는 GPU/CPU 메모리에 계산 그래프를 계속 쌓아두는 경향이 있어서,
        #  요청마다 정리해주지 않으면 서버가 오래 켜져 있을수록 메모리를 점점 더 먹는다)
        import sys as _sys
        if "tensorflow.keras.backend" in _sys.modules:
            try:
                _sys.modules["tensorflow.keras.backend"].clear_session()
            except Exception:
                pass

        # 강제 가비지 컬렉션 (Render 512MB 한계 대응)
        # 파이썬은 보통 알아서 안 쓰는 메모리를 회수하지만, 타이밍을 우리가 직접 강제해서
        # 다음 요청이 시작되기 전에 최대한 메모리를 비워두려는 것 (무료 티어라 메모리가 빠듯함).
        import gc
        gc.collect()

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
    """이 파일이 독립 스크립트로 직접 실행됐을 때의 진입점.

    (참고) 예전 버전에서는 app.py가 이 워커를 `subprocess.run([python, worker.py], ...)`로
    매번 새 프로세스로 띄워서 stdin/stdout으로 통신했다. 지금은 성능 때문에
    ProcessPoolExecutor로 워커 프로세스를 재사용하는 방식(app.py의 _worker_task 참고)을 쓰지만,
    그래도 이 main()은 "터미널에서 echo '{...}' | python worker.py 로 단독 테스트"할 때 여전히 쓸모 있다.
    """
    request = json.load(sys.stdin)   # 표준입력(stdin)으로 들어온 JSON 텍스트를 파이썬 객체로 변환
    result = run(request)
    json.dump(result, sys.stdout)    # 결과를 다시 JSON 텍스트로 표준출력(stdout)에 내보냄


if __name__ == "__main__":
    # 이 파일을 직접 실행했을 때만 main()을 호출하고, 다른 파일이 import worker 할 때는
    # 호출하지 않기 위한 파이썬의 표준 관용구.
    main()
