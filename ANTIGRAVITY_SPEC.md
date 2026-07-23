# AICE 실전 모의고사 시뮬레이터 (.exe) — 구현 스펙

> 이 문서는 Antigravity(Gemini)가 그대로 읽고 순서대로 구현하기 위한 확정 스펙입니다.
> **반드시 Phase 순서대로 진행하고, 각 Phase가 끝나면 "Definition of Done" 체크리스트를 실제로 실행해 결과를 보여준 뒤, 사용자 확인을 받고 나서 다음 Phase로 넘어가세요.** 여러 Phase를 한 번에 몰아서 구현하지 마세요 — 중간에 잘못된 가정이 있으면 뒤로 갈수록 되돌리기 비용이 커집니다.

## 0. 절대 규칙

1. `C:\project\Aice\09_모의고사\*.ipynb` 등 기존 학습 자료는 **읽기 전용**입니다. 절대 수정하지 마세요. 이 프로그램은 그 노트북들을 "파싱해서 재사용"하는 것이지, 노트북 자체를 건드리는 게 아닙니다.
2. `C:\project\Aice\00_시작하기\aice_grader.py`에 이미 있는 `check_nulls`, `check_encoding`, `check_shape`, `check_score`, `compare_value`, `ExamTimer` 로직을 최대한 재사용하세요. 새로 발명하지 마세요. 이 프로그램의 "채점 철학"은 이미 노트북들에서 검증된 것과 동일해야 합니다.
3. 각 Phase 완료 시 반드시 **실제로 실행한 터미널 출력**을 사용자에게 보여주세요. "구현했습니다"라는 말만 하고 실행 결과가 없으면 미완성으로 간주합니다.
4. 모든 파일 경로는 `pathlib.Path`를 사용하고, 상대경로는 스크립트 위치 기준으로 계산하세요 (하드코딩된 절대경로 금지).
5. 이 문서에 없는 결정(라이브러리 선택, 파일 스키마 등)이 필요하면 **임의로 정하지 말고 먼저 사용자에게 물어보세요.**

---

## 1. 확정된 아키텍처 결정 (여기서 더 고민하지 말 것)

### 1.1 GUI 프레임워크: **PySide6**
- PyQt5(GPL)가 아니라 PySide6(LGPL)를 사용합니다 — 유료 판매 제품이므로 라이선스가 중요합니다.
- 코드 에디터는 별도 무거운 위젯(QScintilla 등) 없이 `QPlainTextEdit` + 자체 `QSyntaxHighlighter` 서브클래스로 최소한의 Python 문법 강조만 구현합니다. (키워드/문자열/주석 3가지 색상이면 충분)
- matplotlib 그래프는 `matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`로 임베드합니다.

### 1.2 실행 범위(v1 스코프): **딥러닝(5교시) 문제는 이번 버전에서 제외**
- 이유: PyInstaller + TensorFlow 조합은 빌드가 매우 무겁고(500MB+) 잘 깨집니다.
- `tools/ipynb_to_exam.py`가 노트북을 파싱할 때 "5교시: 딥러닝 모델링" 섹션은 건너뛰고 `mock_exam.json`에 포함하지 않습니다.
- 이 결정에 이견이 있으면 사용자에게 먼저 확인받으세요. (기본값은 "제외"입니다)

### 1.3 실행 네임스페이스는 "문제별"이 아니라 "세션 전체에서 지속"
**이게 제일 중요한 결정입니다. 절대 놓치면 안 됩니다.**

실제 모의고사 노트북은 아래처럼 되어 있습니다 (예: 모의고사01 cell 구조):

```
cell[2] (code) : import pandas as pd ... ; df = pd.read_csv(...)   <- 최초 1회만 실행
cell[5] (markdown) : **문제 1.** df의 shape과 결측치를 출력하세요.
cell[6] (code, 사용자 작성) : print(df.shape); print(df.isnull().sum())
...
cell[25] (markdown) : **문제 7.** Name에서 Title을 추출해 컬럼을 만드세요.
cell[26] (code, 사용자 작성) : df['Title'] = df['Name'].apply(...)   <- df를 "변형"함
...
cell[31] (markdown) : **문제 9.** get_dummies로 인코딩하세요.
cell[32] (code, 사용자 작성) : df = pd.get_dummies(df, ...)         <- 문제 7의 결과(df['Title'])를 이어받아 사용
```

즉 문제 9는 문제 7에서 만든 `Title` 컬럼이 이미 존재한다고 가정하고 작성됩니다. **각 문제를 독립된 `exec()` 네임스페이스에서 실행하면 이런 문제들이 전부 깨집니다.**

**구현 방법**: `engine/code_executor.py`는 시험 세션 시작 시 단 하나의 `namespace: dict`를 만들고 (최초 데이터 로딩 코드로 초기화), 이후 모든 문제의 사용자 코드를 **같은 namespace에 누적 실행**합니다. Jupyter 커널이 동작하는 방식과 동일합니다.

- 문제를 다시 풀거나 이전 문제로 돌아가서 코드를 수정하는 경우: 그 문제부터 **현재 문제까지 순서대로 전부 재실행**해서 namespace를 재구성합니다 (Jupyter의 "Restart & Run All"과 동일한 개념). 문제별로 diff 재실행 최적화는 v1에서 하지 않아도 됩니다 — 정확성이 우선입니다.

### 1.4 채점 방식: "코드 비교"가 아니라 "실행 결과 스냅샷 비교"
사용자가 제출한 코드가 정답 코드와 **글자 그대로 같을 필요는 없습니다.** 대신, 정답 코드를 실행했을 때 특정 변수가 갖게 되는 상태(스냅샷)와, 사용자 코드를 실행했을 때 그 변수가 갖게 되는 상태를 비교합니다.

`mock_exam.json`의 각 문제는 아래와 같은 `checks` 배열을 가집니다:

```json
{
  "checks": [
    {"var": "df", "attr": "shape", "op": "eq", "expected": [891, 13]},
    {"var": "df", "attr": "isnull().sum().sum()", "op": "eq", "expected": 0},
    {"var": "acc", "op": "gte", "expected": 0.75, "tolerance": 0.0}
  ]
}
```

- `var`: namespace 안의 변수 이름
- `attr`: (선택) 그 변수에 대해 평가할 표현식 (예: `.shape`, `.isnull().sum().sum()`). 없으면 변수 자체를 비교.
- `op`: `eq`(정확히 일치) | `gte`(이상) | `lte`(이하) | `close`(허용오차 내 근사, `aice_grader.compare_value`와 동일 로직 재사용)
- `expected`: 정답 코드를 실제로 실행해서 **생성 시점에 자동 계산**한 값 (사람이 손으로 입력하지 않습니다 — `tools/ipynb_to_exam.py`가 정답 코드를 한 번 실행해서 이 값을 채워 넣습니다)

`engine/grader.py`는 문제별로 `checks`를 순회하며 `eval(f"{var}{attr}", {}, namespace)` 형태로 사용자 namespace에서 값을 뽑아 비교합니다. 하나의 문제에 checks가 여러 개면 **전부 통과해야 그 문제가 정답**입니다 (부분점수 없음, v1 기준).

> 주의: `eval`에 사용자 입력이 아니라 **우리가 JSON에 미리 정의한 표현식**만 들어가므로 안전합니다. 사용자가 직접 입력한 코드는 `code_executor.py`에서 별도로 `exec`됩니다.

---

## 2. Phase 0 — 문제 파싱 (`tools/ipynb_to_exam.py`)

### 목표
`C:\project\Aice\09_모의고사\모의고사01_Titanic_생존자예측.ipynb` ~ `모의고사10_마케팅전환예측.ipynb` (총 10개)를 파싱해서 `data/mock_exam_01.json` ~ `mock_exam_10.json`으로 변환합니다.

### 정확한 셀 구조 (실측 결과, 10개 파일 전부 동일 패턴)

```
cells[0]  : markdown, 제목 + 인트로
cells[1]  : markdown, "## 목차"
cells[2]  : code, import + 데이터 로딩 (예: df = pd.read_csv('../data/train.csv'))
cells[3]  : code, 타이머 시작 코드 (파싱 시 무시 — exe 프로그램은 자체 타이머가 있음)
cells[4]  : markdown, "## 1교시: ..." 같은 세션 헤더 (문제 여러 개 앞에 하나씩 등장)
cells[5]  : markdown, "**문제 1.** <지문 텍스트>"
cells[6]  : code, "# 여기에 코드를 작성하세요" (빈 TODO 셀 — 무시)
cells[7]  : markdown, "<details>\n<summary>✅ 정답 보기</summary>\n\n```python\n<정답코드>\n```\n\n</details>"
...  (문제 수만큼 [markdown 지문][code 빈칸][markdown 정답] 3개 셀이 반복, 교시 바뀔 때 "## N교시" 헤더 셀이 끼어듦)
cells[-2] : code, 타이머 종료 코드 (무시)
cells[-1] : markdown, "## 채점 가이드 (100점 만점 배점표)" + 마크다운 표
```

### 파싱 규칙
1. `re.match(r'^\*\*문제 (\d+)\.\*\*\s*(.+)', cell.source, re.S)` 로 문제 번호와 지문을 추출.
2. 그 다음 code 셀은 항상 빈 TODO — 무시.
3. 그 다음 markdown 셀에서 ` ```python\n(.*?)\n``` ` (re.S)로 정답 코드를 추출.
4. 직전에 등장한 "## N교시: 제목" 헤더 텍스트를 `session` 필드로 저장 (문제가 어느 교시에 속하는지).
5. 마지막 셀(`## 채점 가이드`)의 마크다운 표에서 `\| 문제 (\d+) \| (\d+)점 \|` 정규식으로 문항별 배점을 추출.
6. **5교시(딥러닝) 섹션은 건너뜁니다** (1.2 참고). "## 5교시" 헤더를 만나면 그 다음 "## 채점 가이드" 헤더가 나올 때까지의 문제들은 mock_exam.json에 포함하지 않습니다. 단, 배점표의 총점은 그대로 두되 `total_points_v1` 필드에 "딥러닝 제외 후 실제 이 프로그램이 채점하는 만점"을 별도로 기록하세요 (예: 100점 만점 중 딥러닝 문제 배점을 뺀 값).

### `checks` 자동 생성 (가장 중요한 부분)
정답 코드를 파싱만 하고 끝나면 안 됩니다. 아래 절차를 반드시 수행하세요:

1. 각 모의고사 파일마다, **처음부터 순서대로 정답 코드를 실제로 실행**하는 별도의 참조 실행기를 만드세요 (`code_executor.py`를 재사용하거나 간단한 별도 함수로). cell[2]의 데이터 로딩 코드부터 시작해서, 모든 문제의 **정답 코드를 순서대로 같은 namespace에 누적 실행**합니다 (1.3의 지속 네임스페이스와 동일한 원리).
2. 각 문제의 정답 코드를 실행한 직후, 그 namespace의 상태를 보고 해당 문제에 대한 `checks`를 자동으로 생성합니다:
   - 데이터프레임 관련 문제(`df`, `X_train` 등이 코드에 등장) → `{"var": "<이름>", "attr": "shape", "op": "eq", "expected": <실행 결과>}` 자동 추가. 새로 만들어진 컬럼이 있으면 `{"var": "df", "attr": "columns.tolist()", "op": "eq", "expected": [...]}` 도 추가.
   - 모델 학습/평가 문제(`accuracy_score`, `r2_score`, `f1_score` 등 호출) → 그 반환값을 담은 변수에 대해 `{"op": "gte", "expected": <실행값 - 0.03>, "tolerance": 0}` (사용자가 정확히 같은 값을 못 내도 근접하면 통과하도록 여유를 둠. 회귀 R2는 `-0.05` 여유)
   - 시각화 문제(`sns.`, `plt.` 호출만 있고 새 변수가 없는 경우) → `checks: []` (자동채점 불가 — `"manual_review": true` 플래그만 남기고, UI에서는 "그래프가 그려졌는지 스스로 확인하세요"로 표시)
3. 이 자동 생성 결과를 `data/mock_exam_01.json` 등에 저장한 뒤, **반드시 실행 로그(각 문제별로 checks가 몇 개 생성됐는지)를 출력**하세요.

### `mock_exam.json` 스키마 예시

```json
{
  "exam_id": "모의고사01_Titanic_생존자예측",
  "title": "Titanic 생존자 예측 (이진분류)",
  "time_limit_minutes": 90,
  "setup_code": "import pandas as pd\nimport numpy as np\n...\ndf = pd.read_csv('data/train.csv')\ndf.head()",
  "total_points_v1": 88,
  "problems": [
    {
      "no": 1,
      "session": "1교시: 데이터 로딩 & EDA",
      "prompt_markdown": "`df`의 shape과 컬럼별 결측치 개수를 출력하세요.",
      "answer_code": "print(df.shape)\nprint(df.isnull().sum())",
      "points": 6,
      "checks": [
        {"var": "df", "attr": "shape", "op": "eq", "expected": [891, 12]}
      ],
      "manual_review": false
    }
  ]
}
```

### Definition of Done (Phase 0)
- [ ] `python tools/ipynb_to_exam.py` 실행 시 10개 `mock_exam_XX.json`이 `data/` 폴더에 생성됨
- [ ] 각 파일에 대해 "총 문제 수 / checks 자동 생성된 문제 수 / manual_review 문제 수"를 콘솔에 출력
- [ ] `data/mock_exam_01.json`을 직접 열어서 문제 1~3개 정도의 `checks.expected` 값이 실제 Titanic 데이터와 맞는 상식적인 값인지 (예: shape이 (891, 12) 근처인지) 사람이 눈으로 확인 가능하도록 로그에 남길 것

---

## 3. Phase 1 — 세션 관리 (`engine/session_manager.py`)

### `session.json` 스키마

```json
{
  "exam_id": "모의고사01_Titanic_생존자예측",
  "started_at": "2026-07-21T14:03:00",
  "elapsed_seconds": 1830,
  "time_limit_minutes": 90,
  "current_problem_no": 5,
  "code_by_problem": {
    "1": "print(df.shape)\nprint(df.isnull().sum())",
    "2": "# 아직 작성 중...",
    "3": ""
  },
  "graded_results": {
    "1": {"is_correct": true, "points_earned": 6}
  }
}
```

- 저장 위치: `sessions/<exam_id>_<시작시각 타임스탬프>.json`
- 저장 트리거: (a) 60초마다 자동 저장, (b) 사용자가 코드 에디터에서 타이핑을 멈춘 지 5초 후 디바운스 저장, (c) 문제 제출(채점) 직후 즉시 저장. 세 가지 전부 구현하세요 — 60초 주기만 있으면 마지막 순간 작업이 날아갈 수 있습니다.
- 프로그램 시작 시 `sessions/` 폴더에 미완료 세션이 있으면 "이어서 풀기" 다이얼로그를 띄웁니다.

### Definition of Done (Phase 1)
- [ ] 세션 저장/로드 단위 테스트 (pytest): 저장 후 즉시 로드했을 때 원본과 완전히 동일한지
- [ ] 강제 종료 시나리오 수동 테스트: 프로그램 실행 → 문제 3번에서 코드 입력 → 15초 대기(디바운스 저장 확인) → 작업관리자로 강제 종료 → 재실행 → 복구 다이얼로그 확인 → 복구 후 코드/타이머 값이 종료 직전과 일치하는지 스크린샷으로 증빙

---

## 4. Phase 2 — 코드 실행기 (`engine/code_executor.py`)

### 요구사항
- 클래스 `CodeExecutor`는 생성 시 `setup_code`를 받아 최초 1회 실행하고 내부에 `self.namespace: dict`를 보관합니다.
- `run_problem(problem_no, code, all_problems_up_to_here)`: 1.3에서 설명한 대로, **problem_no 이전까지의 모든 문제의 (사용자가 마지막으로 저장한) 코드를 처음부터 순서대로 재실행**한 뒤 현재 코드를 실행합니다. (매 실행마다 setup_code부터 재실행 — 정확성 우선, 속도 최적화는 v2)
- `matplotlib.use('Agg')` 또는 Qt 백엔드로 설정하고, `plt.show()`를 몽키패치해서 실제 창을 띄우는 대신 `FigureCanvasQTAgg`로 렌더링된 이미지를 UI에 전달할 콜백을 호출하도록 구현.
- `print()` 출력과 예외(traceback)를 `io.StringIO`로 캡처해서 UI 콘솔 탭에 표시.
- 실행 타임아웃: 문제당 30초 초과 시 강제 중단 (무한루프 방지). `threading` 또는 `multiprocessing` 중 하나를 선택하되, **왜 그걸 선택했는지 주석으로 이유를 남기세요** (예: matplotlib 객체는 프로세스 간 공유가 까다로워서 threading + signal 기반 타임아웃을 선택함 등).

### Definition of Done (Phase 2)
- [ ] pytest: 문제 1 코드 실행 후 문제 2 코드가 문제 1에서 만든 변수를 참조할 수 있는지 확인하는 테스트
- [ ] pytest: 무한루프 코드(`while True: pass`)를 넣었을 때 30초 내에 강제 종료되는지 확인
- [ ] 수동 확인: `sns.heatmap(...)` 같은 시각화 코드를 실행했을 때 그래프 이미지가 실제로 캡처되는지 스크린샷

---

## 5. Phase 3 — 채점 엔진 (`engine/grader.py`)

- `grade_problem(namespace, problem_spec) -> (is_correct: bool, detail: str)`: problem_spec["checks"]를 순회하며 1.4의 `op`별 비교 수행. `close` op은 `aice_grader.compare_value`와 동일한 허용오차 로직을 그대로 가져다 쓰세요 (import해서 재사용, 코드 복붙 금지).
- `checks`가 비어있고 `manual_review: true`인 문제는 자동 채점하지 않고 UI에 "본인이 직접 확인" 배지를 표시하도록 `detail`에 명시.
- 전체 결과 집계는 기존 `MockExamGrader`의 리포트 포맷(획득점수/총점/합격여부 80점 기준)을 그대로 재사용하세요.

### Definition of Done (Phase 3)
- [ ] pytest: 정답 코드를 그대로 넣었을 때 모든 문제가 `is_correct=True`가 되는지 (mock_exam_01.json 전체로 회귀 테스트)
- [ ] pytest: 일부러 틀린 코드(예: `df.shape` 대신 `df.head()`만 출력)를 넣었을 때 정확히 오답 처리되는지

---

## 6. Phase 4 — UI (`ui/main_window.py`, `main.py`)

레이아웃: 상단(타이머+진행률+문제 네비게이션 버튼) / 좌측(문제 지문, Markdown 렌더링) / 우측(코드 에디터) / 하단(탭: 콘솔 출력 | 그래프 출력). "채점하기" 버튼과 "정답 보기" 버튼(정답 보기를 누르면 그 문제는 자동으로 감점 처리 — 실제 시험처럼).

이 Phase는 스펙을 너무 세세하게 규정하지 않습니다. 대신 **PySide6 시그널/슬롯 계약**만 지키세요:
- `CodeExecutor`, `SessionManager`, `Grader`는 UI와 완전히 분리된 순수 Python 클래스여야 합니다 (PySide6 import가 그 파일들 안에 있으면 안 됩니다). UI는 이 클래스들을 가져다 쓰기만 합니다. → 이렇게 해야 나중에 사람이 로직만 따로 pytest로 검증할 수 있습니다.

### Definition of Done (Phase 4)
- [ ] `python main.py`로 실행 시 모의고사01을 처음부터 끝까지 (딥러닝 제외 문제만) 실제로 풀어서 채점까지 완료하는 전체 시나리오 스크린샷 5장 이상

---

## 7. 지금은 하지 말 것 (다음 단계로 보류)

아래 두 가지는 **Antigravity가 지금 시도하지 마세요.** Phase 0~4가 전부 끝나고 사용자가 확인한 뒤, 별도로 진행합니다.

- **`tools/generate_problems.py` (동적 문제 생성)** — 품질 판단이 어렵고 잘못하면 이상한 문제가 생성됩니다. Phase 0~4가 안정되면 다시 논의합니다.
- **PyInstaller `.exe` 패키징** — sklearn/matplotlib 포함 빌드는 hidden-import 이슈가 많아 반복적인 디버깅이 필요합니다. Phase 0~4 코드가 완성되고 pytest가 전부 통과한 뒤에 진행합니다.

Phase 0~4까지 완료되면 거기서 멈추고 사용자에게 보고하세요.
