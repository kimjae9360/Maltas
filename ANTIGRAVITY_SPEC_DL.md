# AICE 실전 모의고사 시뮬레이터 — 딥러닝(5교시) 지원 추가 스펙

> 이 문서는 이미 완성되어 검증까지 끝난 "1~4교시 exe"(`dist/AICE_Simulator/AICE_Simulator.exe`)에 딥러닝(5교시)을 추가하는 작업입니다.
> **기존에 검증 완료된 파일/빌드를 절대 덮어쓰지 마세요.** 아래처럼 전부 "DL 전용 별도 산출물"로 만듭니다. 기존 것과 새 것을 나란히 비교할 수 있어야 실패해도 되돌릴 수 있습니다.
> Phase 순서대로 진행하고, 각 Phase 끝나면 실행 결과를 보여준 뒤 사용자 확인을 받고 다음으로 넘어가세요.

## 0. 절대 규칙 (기존 스펙과 동일)

1. `C:\project\Aice\09_모의고사\*.ipynb`는 읽기 전용. 수정 금지.
2. `data/모의고사*.json` (현재 1~4교시용, 이미 검증됨) 은 **절대 덮어쓰지 마세요**. 새 파일은 `data_dl/모의고사*.json`처럼 별도 폴더/이름으로 저장.
3. 각 Phase 끝나면 실제 실행 결과(터미널 출력)를 보여줄 것.
4. 문서에 없는 결정은 임의로 정하지 말고 먼저 물어볼 것.

## 1. 확정된 결정

### 1.1 파서 확장: `tools/ipynb_to_exam.py`를 건드리지 말고 새 스크립트로
기존 `parse_notebook()` 함수는 `in_dl_section` 플래그로 5교시를 건너뛰도록 되어 있습니다. 이 로직을 지우거나 바꾸지 말고, **`tools/ipynb_to_exam_dl.py`라는 새 파일을 만들어서** 기존 함수를 복사한 뒤 `in_dl_section` 필터링만 제거한 버전을 만드세요. (기존 파일이 계속 1~4교시용 안정 버전을 만들어내야 하므로 그대로 둡니다.)

- 출력 경로: `data_dl/모의고사01_Titanic_생존자예측.json` 등 (기존 `data/` 폴더와 별도)
- 5교시 문제의 `checks` 자동 생성 시, DL 답안 코드에 나오는 변수명(`acc`, `accuracy`, `loss`, `history` 등)을 인식하도록 `score_vars` 목록에 필요한 이름이 이미 있는지 실행 결과 로그로 확인하세요. 없으면 `manual_review: true`로 남는 게 정상입니다(무리하게 다 자동채점 만들려 하지 마세요).
- 기존 경로 보정 스크립트(`'../data/' -> 'data/'`)도 이 새 JSON들에 동일하게 다시 적용해야 합니다.

### 1.2 실행 타임아웃
`engine/code_executor.py`의 30초 타임아웃은 딥러닝 학습(`epochs=100`, `EarlyStopping`)에는 너무 짧을 수 있습니다. `CodeExecutor.run_problem()`의 `timeout` 파라미터를 UI에서 문제 유형에 따라 다르게 넘기도록 하세요 (예: `main_window.py`에서 문제의 `session`에 "딥러닝"이 포함되면 `timeout=180`, 아니면 기존 30초). **`code_executor.py` 자체의 기본값은 건드리지 마세요** — 이미 검증된 1~4교시 동작에 영향 줄 수 있습니다.

### 1.3 새 진입점과 새 빌드 — 기존 것과 분리
- `main_dl.py`: `main.py`를 복사해서 만들되, `exam_json = base_dir / "data_dl" / f"{exam_id}.json"`처럼 새 데이터 폴더를 보게 하세요.
- requirements: `tensorflow`를 새로 추가 (기존 `requirements.txt`에 추가해도 되지만, 최소한 별도로 `pip install tensorflow` 먼저 하고 import 되는지 확인).
- PyInstaller 빌드는 **완전히 새 이름으로**: `--name AICE_Simulator_DL`. 결과물은 `dist/AICE_Simulator_DL/`에 생기므로 기존 `dist/AICE_Simulator/`(1~4교시, 이미 검증 완료)는 그대로 남아있어야 합니다.
- 빌드 시 tensorflow 관련 흔한 함정: `--collect-all tensorflow`를 쓰면 xgboost 때처럼 tensorflow의 내부 테스트/디버그 서브모듈 임포트에서 죽을 수 있습니다. 에러가 나면 에러 메시지에 나온 모듈을 `--exclude-module`로 제외하고 재시도하세요 (xgboost.testing 때 했던 것과 같은 방식). `hypothesis`처럼 없어서 죽는 의존성이 있으면 설치해서 해결할지, exclude로 건너뛸지 먼저 저에게 물어보세요.
- Windows에서 tensorflow는 보통 매우 무겁습니다(수백MB~1GB 추가 가능). 빌드가 20분을 넘기거나 실패를 3번 이상 반복하면 진행을 멈추고 상황을 보고하세요.

## 2. Phase 순서

1. **Phase DL-0**: `tools/ipynb_to_exam_dl.py` 작성 + 실행 → `data_dl/`에 10개 JSON 생성 (5교시 포함). 각 파일의 5교시 문제 수와 checks 생성 여부를 로그로 확인.
2. **Phase DL-1**: `main_dl.py` + `code_executor.py` 타임아웃 분기 처리. `python main_dl.py`로 실제 실행해서 5교시 문제(Sequential 모델 학습)가 앱 안에서 정말로 끝까지 도는지 확인 (에러 없이, 시간 내에).
3. **Phase DL-2**: PyInstaller로 `AICE_Simulator_DL.exe` 빌드. 완료 후 실제로 실행해서 5교시 문제까지 풀어보는 스모크 테스트.

각 Phase 끝나면 멈추고 결과를 보고하세요. Phase DL-2까지 끝나면 전체 작업 종료, 추가로 진행하지 마세요.
