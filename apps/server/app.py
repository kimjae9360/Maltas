"""
AICE_Simulator 모의고사 실행/채점 API.

이 API는 임의의 파이썬 코드를 그대로 실행하는 엔드포인트를 인터넷에 노출한다. X-API-Key는
"진짜 보안"이 아니라 무차별 스캔 방지용 최소 방어선이다(프론트 번들에 값이 들어가므로 네트워크
탭을 보면 누구나 꺼낼 수 있다). URL을 공개적으로 퍼뜨리기 전에는 반드시 더 강한 인증으로
교체해야 한다.

--- 공부용 요약 ---
FastAPI로 만든 웹 서버. 프론트(apps/web)가 이 서버에 fetch()로 요청을 보내면,
여기서 문제 데이터를 돌려주거나(GET) 사용자 코드를 실제로 실행해 채점(POST)한다.
실제 코드 실행은 이 파일이 직접 하지 않고 worker.py에 위임한다 — 이 파일은
"요청을 받아서 worker에 넘기고, 결과를 HTTP 응답으로 포장하는" 역할만 한다.
"""
import os
import sys
import json
import glob
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeout

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))   # 이 app.py가 있는 폴더(apps/server) 절대경로
DATA_DIR = os.path.join(SERVER_DIR, "data")                # 문제 JSON·CSV들이 들어있는 폴더
# (참고) 예전엔 여기 WORKER_PATH = .../worker.py 를 만들어서 subprocess.run([python, WORKER_PATH], ...)
# 로 워커를 매번 새 프로세스로 띄웠다. 지금은 ProcessPoolExecutor + `from worker import run`으로
# 같은 프로세스 안에서 함수만 호출하는 방식이라 그 경로 문자열 자체가 필요 없어져서 제거했다.

# 환경변수(env var)로 값을 받는 이유: 이 값들은 배포 환경(Render)마다 다르고, 특히 API_KEY는
# 코드에 그대로 적어서 git에 올리면 안 되는 비밀값이라 배포 플랫폼의 "환경변수" 설정으로 주입한다.
# os.environ.get("KEY", "기본값") = 환경변수가 없으면 기본값을 쓰는 파이썬 표준 패턴.
API_KEY = os.environ.get("AICE_API_KEY", "")
ALLOWED_ORIGINS = [o for o in os.environ.get("AICE_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o]
# "http://a.com,http://b.com" 처럼 콤마로 구분된 문자열을 받아 리스트로 쪼갠다.
# CORS(Cross-Origin Resource Sharing): 브라우저는 기본적으로 "프론트가 열려있는 주소와 다른 주소로의
# fetch 요청"을 막는다(보안 정책). 이 서버가 웹 프론트(예: maltas-six.vercel.app)의 요청을 받아주려면,
# "이 origin(출처)들의 요청은 허용한다"고 서버가 명시적으로 알려줘야 하는데 그게 ALLOWED_ORIGINS다.

limiter = Limiter(key_func=get_remote_address)  # IP 주소 기준으로 요청 횟수를 세는 레이트리미터
app = FastAPI(title="AICE Simulator API")       # FastAPI 앱 인스턴스 — 이 객체에 엔드포인트(@app.get 등)를 등록해나간다
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # 레이트리밋 초과 시 자동으로 429 응답
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
# 미들웨어(middleware) = 모든 요청/응답이 공통으로 거쳐가는 처리 단계. 여기서는 "요청이 허용된
# origin에서 왔는지" 매 요청마다 자동으로 검사해주는 역할.

# ─── 데이터 로딩 ─────────────────────────────────────────────────────────────
def _load_json_dir(pattern, key_field):
    """DATA_DIR 안에서 pattern에 맞는 JSON 파일들을 전부 읽어서,
    {그 파일의 key_field 값: 파일 내용} 형태의 딕셔너리로 모아준다.

    예: _load_json_dir("모의고사*.json", "exam_id") 를 호출하면
    "모의고사01_Titanic_생존자예측.json" 파일을 읽어서 그 안의 "exam_id" 필드 값을 key로 쓴다.
    이렇게 해두면 나중에 exam_id 문자열 하나로 O(1)에 그 시험 데이터를 바로 찾을 수 있다.
    """
    items = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, pattern))):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items[data[key_field]] = data
    return items

# 서버가 켜질 때(import 시점) 딱 한 번만 모든 문제 데이터를 메모리에 올려둔다.
# 매 요청마다 파일을 다시 읽지 않아도 되니 빠르고, 파일 시스템 I/O도 줄어든다.
# (대신 새 문제 JSON을 추가하려면 서버를 재시작해야 반영된다 — 이 앱 규모에선 문제 없는 트레이드오프)
EXAMS = _load_json_dir("모의고사*.json", "exam_id")
CHAPTERS = _load_json_dir("study_*.json", "chapter_id")

# ─── 지속형 워커 프로세스 풀 ──────────────────────────────────────────────────
# subprocess.run()은 매 채점마다 Python 인터프리터를 새로 시작해 30초 이상 걸릴 수 있다.
# ProcessPoolExecutor는 워커 프로세스를 계속 살려두므로 두 번째 요청부터 빠르다.
#
# (공부용 보충 설명)
# 예전 방식: 채점 요청이 올 때마다 `subprocess.run([python, "worker.py"], ...)`로 파이썬
#   인터프리터 자체를 처음부터 새로 켰다. pandas/sklearn 같은 무거운 라이브러리를 매번
#   import하느라 Render 무료 티어(CPU가 느림)에서는 코드 한 줄 실행에도 10~30초씩 걸렸다.
# 지금 방식: ProcessPoolExecutor(max_workers=1)로 "워커 프로세스 1개"를 미리 띄워두고 계속
#   재사용한다. 그 프로세스는 sklearn/tensorflow를 이미 import한 상태로 살아있기 때문에,
#   두 번째 요청부터는 무거운 import를 다시 안 해도 돼서 훨씬 빨라진다.
# 트레이드오프: 프로세스를 계속 재사용하다 보니, 어떤 사용자의 코드가 numpy 전역 난수 시드를
#   건드리는 등 "파이썬 프로세스 전역 상태"를 바꾸면 이론적으로 다음 채점 요청에 그 흔적이
#   남을 수 있다. 이 프로젝트의 정답 코드들은 보통 random_state를 코드 안에 직접 명시하므로
#   실제 채점 정오답에는 거의 영향이 없다고 판단해 이 트레이드오프를 받아들였다.
sys.path.insert(0, SERVER_DIR)  # worker 모듈을 찾을 수 있도록
# sys.path = 파이썬이 `import 모듈이름`을 할 때 뒤져보는 폴더 목록. ProcessPoolExecutor가 만드는
# 새 프로세스는 이 app.py를 실행한 방식에 따라 apps/server가 sys.path에 없을 수도 있어서,
# "worker.py를 반드시 찾을 수 있도록" 명시적으로 경로를 추가해준다.

_POOL: ProcessPoolExecutor | None = None
# 타입 힌트 `ProcessPoolExecutor | None` = 이 변수는 ProcessPoolExecutor 객체이거나 None일 수 있다는 뜻.
# 모듈 최상단에 선언된 전역(global) 변수라, 이 파일이 처음 import될 때 딱 한 번 None으로 초기화되고
# 이후 요청들이 같은 값을 공유해서 재사용한다.


def _get_pool() -> ProcessPoolExecutor:
    """풀이 아직 없으면(서버가 막 켜졌거나, 이전에 리셋됐으면) 새로 만들고, 있으면 그대로 재사용해서 돌려준다."""
    global _POOL
    # 함수 안에서 전역 변수 _POOL의 값 자체를 바꾸려면(재할당) global 선언이 꼭 필요하다.
    # (선언 없이 _POOL = ... 을 하면 파이썬은 그걸 "새로운 지역 변수"로 착각한다)
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=1)
        # max_workers=1: 워커 프로세스를 딱 1개만 둔다. 이 앱은 사용자가 1~2명 수준이라
        # 여러 채점을 동시에 처리할 필요가 없고, 1개로 제한하면 메모리도 아낄 수 있다.
    return _POOL


def _worker_task(worker_input: dict) -> dict:
    """워커 프로세스 안에서 실행되는 함수."""
    # 이 함수는 별도 프로세스에서 실행되므로 여기서 import 해야 한다.
    # (ProcessPoolExecutor로 새 프로세스를 만들면, 그 프로세스는 app.py를 처음부터 다시 import하며
    #  시작한다. 이때 이 함수 자체는 pickle로 "직렬화"되어 자식 프로세스로 전달되는데, 함수 안에서
    #  쓰는 import들은 그 자식 프로세스 쪽에서 다시 실행돼야 하므로 굳이 함수 내부에 넣어둔 것)
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from worker import run  # noqa: PLC0415
    return run(worker_input)


def _make_timeout_result(timeout: float) -> dict:
    """제한 시간을 넘겨서 강제 종료됐을 때 프론트에 돌려줄 표준 응답 형태."""
    return {
        "stdout": "",
        "error": f"Execution timed out ({int(timeout)}s limit).",
        "is_correct": False,
        "detail": "⏱️ 실행 시간이 초과됐습니다. 다시 시도해주세요. (첫 채점은 서버 워밍업으로 느릴 수 있습니다)",
        "plots": [],
    }


def _reset_pool():
    """지금 살아있는 워커 프로세스를 버리고, 다음 요청 때 완전히 새 프로세스로 다시 시작하게 만든다.

    타임아웃(무한루프 등)이나 예상 못한 에러가 나면 호출한다. 그 프로세스가 이상한 상태(예: 메모리를
    너무 많이 먹었거나, 응답이 없는 상태)로 남아있을 수 있어서, 아예 버리고 새로 시작하는 게 안전하다.
    """
    global _POOL
    if _POOL is not None:
        try:
            # wait=False: 지금 실행 중인 작업을 기다리지 않고 즉시 반환한다(요청이 오래 걸리지 않도록).
            # cancel_futures=True: 아직 시작 안 한 대기 중인 작업들은 취소한다.
            #   (단, 이미 실행 중인 작업 자체를 강제로 죽이는 기능은 아니라서, 정말 멈춰버린 프로세스는
            #    자연스럽게 백그라운드에 남았다가 종료될 수 있다 — 이 앱 규모에선 감수 가능한 수준)
            _POOL.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        _POOL = None  # 다음 _get_pool() 호출 때 새로 만들어지도록 초기화

def _run_worker(setup_code, code_by_problem, current_code, problem_no, checks, manual_review, timeout):
    """모든 채점 요청이 공통으로 거쳐가는 함수. 모의고사 채점과 학습모드 채점 둘 다 이 함수를 쓴다.

    실제 실행은 워커 프로세스(별도 프로세스)에서 일어나므로, 여기서는 "일 시키고 결과 기다리기"만 한다.
    """
    worker_input = {
        "setup_code": setup_code,
        "code_by_problem": code_by_problem,
        "current_code": current_code,
        "problem_no": problem_no,
        "checks": checks,
        "manual_review": manual_review,
    }
    pool = _get_pool()
    future = pool.submit(_worker_task, worker_input)
    # pool.submit(...) : "이 작업을 워커 프로세스에게 시켜라"라고 예약만 하고, 즉시 Future 객체를 돌려준다.
    # Future = "나중에 결과가 나올 상자". future.result()를 부르면 결과가 나올 때까지 기다린다.
    try:
        return future.result(timeout=timeout)
        # timeout초 안에 결과가 안 나오면 FuturesTimeout 예외를 던진다. 이게 바로 "진짜 하드 타임아웃"
        # 역할을 한다 — 사용자 코드가 무한루프에 빠져도 이 서버(그리고 클라이언트)는 timeout초 뒤엔
        # 반드시 응답을 받는다.
    except FuturesTimeout:
        future.cancel()
        _reset_pool()  # 멈춰버린 워커를 버리고 다음 요청을 위해 새로 준비
        return _make_timeout_result(timeout)
    except Exception as exc:
        # 워커 프로세스가 죽어버리는 경우(BrokenProcessPool 등) 포함, 예상 못한 모든 에러를 여기서 잡아
        # 서버 자체는 절대 죽지 않고 항상 JSON 응답을 돌려주게 만든다.
        _reset_pool()
        return {
            "stdout": "",
            "error": str(exc),
            "is_correct": False,
            "detail": "❌ 코드 실행 중 서버 오류가 발생했습니다.",
            "plots": [],
        }


def require_api_key(x_api_key: str = Header(default="")):
    """FastAPI의 Depends()로 엔드포인트에 끼워넣는 "인증 검사기".

    x_api_key: str = Header(default="") 는 FastAPI 특유의 문법으로, HTTP 요청 헤더의
    "X-API-Key" 값을 자동으로 읽어서 이 함수의 인자로 넣어준다(직접 파싱할 필요가 없다).
    이 함수를 쓰는 엔드포인트 앞에 @app.get(..., ) 대신 Depends(require_api_key)를 인자로
    넣어두면, 그 엔드포인트가 실행되기 "전에" 먼저 이 함수가 실행되어 인증을 검사한다.
    """
    if not API_KEY:
        # 로컬 개발 중 AICE_API_KEY가 설정 안 되어 있으면 인증을 건너뛴다.
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")
        # HTTPException을 던지면 FastAPI가 자동으로 그 status_code와 메시지를 담은 HTTP 응답을 만들어준다.


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
    """exam 데이터에서 "정답이 드러나는 필드(answer_code, checks)"를 뺀, 프론트에 내려줘도 안전한 버전.

    왜 굳이 이렇게 따로 만들까? EXAMS 딕셔너리에는 answer_code(정답 코드)와 checks(채점 조건)가
    그대로 들어있는데, 이걸 그대로 프론트에 보내버리면 사용자가 브라우저 개발자도구 네트워크 탭에서
    정답을 그냥 볼 수 있게 된다. 그래서 "문제를 푸는 화면"에 필요한 필드만 골라서 새 딕셔너리를
    만들어 돌려준다 — 서버 메모리 안의 원본(EXAMS)에는 정답이 그대로 남아있고, 응답에만 없는 것.
    """
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
    # 함수 인자 이름을 "_"로 쓴 이유: Depends(require_api_key)의 반환값 자체는 안 쓰고,
    # "이 엔드포인트를 타기 전에 인증 검사만 실행되게 하려는" 목적이라서 관례적으로 밑줄로 표시한다.
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
    # 이 목록 화면에서도 answer_code/checks는 안 실어보낸다 — 애초에 여기서 만드는 딕셔너리에
    # 그 필드들을 넣지도 않았으니 자연히 안전하다.


@app.get("/api/exams/{exam_id}")
def get_exam(exam_id: str, _: None = Depends(require_api_key)):
    # 경로 안의 {exam_id} 는 FastAPI의 경로 파라미터 문법. URL의 그 위치에 온 값이 자동으로
    # 함수의 exam_id 인자에 문자열로 들어온다. 예: /api/exams/모의고사01_Titanic_생존자예측
    return _public_exam(_get_exam(exam_id))


class RunRequest(BaseModel):
    """POST 요청의 JSON 바디(body) 형태를 정의하는 Pydantic 모델.

    FastAPI는 이 클래스를 엔드포인트 함수의 인자 타입으로 쓰면, 요청 바디 JSON을 자동으로
    파싱해서 이 타입의 객체로 만들어주고, 필드 타입이 안 맞으면(예: problem_no에 문자열이 오면)
    자동으로 422 에러를 응답해준다 — 우리가 직접 JSON 파싱/검증 코드를 짤 필요가 없다.
    """
    problem_no: int
    current_code: str
    code_by_problem: dict[str, str] = {}   # "= {}" 는 기본값 — 요청에 이 필드가 없으면 빈 딕셔너리로 처리


@app.post("/api/exams/{exam_id}/run")
@limiter.limit("20/minute")
# 이 데코레이터가 있으면 같은 IP에서 분당 20번 넘게 요청하면 자동으로 429(Too Many Requests) 응답.
# 채점 API는 무거운 코드를 실제로 실행하니, 악의적/실수로 인한 폭주 요청을 막기 위한 최소한의 안전장치.
def run_problem(exam_id: str, body: RunRequest, request: Request, _: None = Depends(require_api_key)):
    exam = _get_exam(exam_id)
    problem = _get_problem(exam, body.problem_no)

    # 딥러닝 문제는 모델 학습 때문에 훨씬 오래 걸리므로 제한시간을 넉넉하게 둔다.
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
    # FastAPI는 함수가 딕셔너리를 return하면 자동으로 JSON 응답으로 변환해준다.


@app.get("/api/exams/{exam_id}/problems/{no}/answer")
def get_answer(exam_id: str, no: int, _: None = Depends(require_api_key)):
    """"정답 보기" 버튼을 눌렀을 때만 호출되는 엔드포인트 — 이때만 answer_code를 내려준다.

    평소 문제 목록/상세 조회(get_exam)에서는 answer_code를 절대 안 보내다가, 사용자가
    명시적으로 정답 보기를 요청했을 때만 이 별도 엔드포인트로 노출하는 구조.
    """
    exam = _get_exam(exam_id)
    problem = _get_problem(exam, no)
    return {"answer_code": problem["answer_code"]}


# ---- 학습 모드 (이론 공부 / 실무 연습) ----
# 데스크톱(ui/study_window.py)과 동일한 "unit index" 방식을 그대로 쓴다:
# section_no*100 + practice_no (practice_no=0은 그 섹션의 예제 코드).
# 예: 3번 섹션의 2번 TODO 문제 = unit 302. 이렇게 숫자 하나로 "몇 섹션의 몇 번째 문제인지"를
# 한꺼번에 표현할 수 있어서, 프론트-서버 간에 주고받을 때 훨씬 간단하다.


def _get_chapter(chapter_id: str) -> dict:
    chapter = CHAPTERS.get(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    return chapter


def _public_chapter(chapter: dict) -> dict:
    """학습 챕터에서도 마찬가지로 answer_code/checks를 뺀 안전한 버전만 프론트에 돌려준다."""
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
    """unit 숫자 하나(예: 302)를 다시 "3번 섹션 + 2번 문제"로 쪼개서 실제 데이터를 찾아준다."""
    section_no, practice_no = divmod(unit, 100)
    # divmod(302, 100) -> (3, 2). 몫과 나머지를 한 번에 구하는 파이썬 내장 함수.
    section = next((s for s in chapter["sections"] if s["no"] == section_no), None)
    if not section:
        raise HTTPException(status_code=404, detail="section not found")
    if practice_no == 0:
        # practice_no가 0이면 "그 섹션의 예제 코드"를 가리키는 것이므로 실습 문제(practice)는 없다.
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
        # is_correct/detail을 None으로 만들어, 프론트가 "정답/오답 표시"를 아예 안 그리도록 신호를 준다.
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
