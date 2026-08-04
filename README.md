# AICE Simulator

이 저장소는 두 가지 버전을 담고 있습니다.

| 폴더 | 설명 |
|---|---|
| `apps/web` + `apps/server` | **웹 버전** (Maltas). Next.js 프론트(Vercel) + FastAPI 채점 서버(Render). 로그인 없이 이론 공부·실무 연습·모의고사를 브라우저에서 바로 풀 수 있고, 딥러닝 문제까지 서버에서 실제로 실행/채점합니다. 지금 실제로 배포·사용 중인 버전입니다. |
| `apps/desktop` | **Windows 데스크톱 버전** (레거시/로컬 백업용). 아래 설명은 이 버전 기준입니다. |

---

## 🚀 그냥 실행만 하고 싶다면 (사용자용, 데스크톱 버전)

1. `dist/AICE_Simulator/` 폴더 전체를 복사해서 원하는 위치에 두세요. (`AICE_Simulator.exe`만 옮기면 안 됩니다 — `_internal` 폴더가 같이 있어야 실행됩니다.)
2. `AICE_Simulator.exe`를 더블클릭합니다. (TensorFlow가 같이 번들되어 있어서 처음 뜰 때 20~30초 정도 걸릴 수 있습니다.)
3. **📝 모의고사 풀기** 또는 **📖 학습 모드** 중 하나를 선택합니다.

### 📝 모의고사 모드

4. "모의고사 선택" 창에서 풀어볼 시험을 고르고 **"선택한 모의고사 시작"**을 누릅니다.
5. 왼쪽 문제 지문을 읽고, 오른쪽 코드 에디터에 코드를 작성한 뒤 **"▶ 현재 문제 실행"**을 누르면 콘솔/시각화 탭에 결과와 채점 결과가 표시됩니다.
6. 막히면 **"정답 보기"**를 누를 수 있지만, 그 문제는 0점 처리됩니다.
7. 다 풀었으면 **"최종 제출 (채점하기)"**를 눌러 최종 점수를 확인합니다.
8. 풀다가 중간에 꺼도 괜찮습니다 — 다음에 실행하면 "이어서 풀기"로 복구할 수 있습니다.

### 📖 학습 모드

4. "학습 챕터 선택" 창에서 공부할 챕터(01~08, EX01~03)를 고릅니다.
5. 섹션마다 **이론 설명 → 핵심 개념 정리 → 예제 코드(직접 실행 가능) → TODO 실전 문제**가 순서대로 나옵니다.
6. TODO 문제는 코드를 직접 작성하고 **"✅ 채점하기"**로 즉시 확인합니다. 막히면 **"정답 보기"**를 누를 수 있지만, 그 문제는 나중에 **"📝 복습 모드"**에 남아 다시 풀어볼 수 있습니다.
7. 챕터를 끝까지 진행하면 자동으로 복습 모드가 열려, 스스로 못 풀었던 문제만 모아서 재도전할 수 있습니다.
8. 타이머나 점수는 없고, 진행 상황은 자동 저장되어 다음에 이어서 볼 수 있습니다.

Python이나 다른 프로그램 설치가 전혀 필요 없습니다. Windows 전용입니다.

> 처음 실행 시 Windows Defender SmartScreen이 "알 수 없는 게시자" 경고를 띄울 수 있습니다. 정식 코드 서명 인증서가 없는 개인 배포 프로그램이라 흔한 현상이며, **"추가 정보" → "실행"**을 누르면 정상 실행됩니다.

---

## 🛠 소스에서 직접 실행/개발하고 싶다면 (데스크톱 버전)

### 환경 준비

TensorFlow가 필요해서 **Python 3.12**로 가상환경을 만들어야 합니다 (3.14는 TensorFlow 미지원). 아래 명령은 모두 `apps/desktop/`에서 실행합니다.

```powershell
cd apps/desktop
py -3.12 -m venv ../../.venv_dl
../../.venv_dl/Scripts/activate
pip install -r requirements.txt
```

### 실행

```powershell
python main.py
```

### 테스트

```powershell
pytest tests/ -v
```

### 다시 빌드(exe 생성)하고 싶다면

```powershell
python -m PyInstaller --name AICE_Simulator --onedir --windowed ^
  --add-data "data;data" ^
  --collect-all sklearn --collect-all scipy --collect-all xgboost --collect-all lightgbm --collect-all imblearn ^
  --collect-data matplotlib --hidden-import markdown ^
  --exclude-module pandas.tests --exclude-module numpy.tests --exclude-module matplotlib.tests ^
  --exclude-module sklearn.tests --exclude-module scipy.tests --exclude-module xgboost.testing ^
  main.py
```

빌드 결과물은 `dist/AICE_Simulator/`에 생성됩니다. (약 1.6GB — TensorFlow/scikit-learn/xgboost가 전부 포함되어 있어서 큽니다.)

---

## 📂 폴더 구조 (데스크톱 버전, `apps/desktop/` 기준)

| 경로 | 설명 |
|---|---|
| `apps/desktop/main.py` | 프로그램 진입점 — 모드 선택(모의고사/학습) → 시험/챕터 선택 → 세션 로드 → 메인 창 실행 |
| `apps/desktop/ui/exam_select_dialog.py` | 모의고사 선택 화면 |
| `apps/desktop/ui/main_window.py` | 모의고사 메인 화면 (타이머, 문제 지문, 코드 에디터, 콘솔/시각화 탭) |
| `apps/desktop/ui/study_select_dialog.py` | 학습 챕터 선택 화면 |
| `apps/desktop/ui/study_window.py` | 학습 모드 메인 화면 (이론/개념표, 예제 실행, TODO 채점/정답보기, 섹션 이동) |
| `apps/desktop/ui/study_review_dialog.py` | 학습 모드 복습 화면 — 스스로 못 푼 TODO 문제만 모아 그 자리에서 재도전 |
| `apps/desktop/ui/highlighter.py` | 코드 에디터용 Python 문법 하이라이터 (모의고사/학습 모드 공용) |
| `apps/desktop/engine/code_executor.py` | 사용자 코드를 안전하게 실행하는 엔진 (세션 전체에서 이어지는 실행 컨텍스트, matplotlib 캡처, 타임아웃 처리) |
| `apps/desktop/engine/grader.py` | 실행 결과를 정답과 비교해 자동 채점 |
| `apps/desktop/engine/session_manager.py` | 모의고사: 풀던 문제/코드/경과시간을 자동저장하고 "이어서 풀기"로 복구 |
| `apps/desktop/engine/study_progress_manager.py` | 학습 모드: 섹션 진행도/오답 리스트를 자동저장하고 "이어서 학습하기"로 복구 |
| `apps/desktop/data/` | 파싱된 시험/학습 데이터(JSON) + 실습용 CSV·Excel·JSON (exe에 그대로 번들됨) — `apps/server/data/`와 내용은 동일하며 웹 서버용 사본이 따로 있음 |
| `apps/desktop/dist/` | 빌드된 최종 실행 파일 (git에는 안 올라감 — 별도로 zip 압축해서 배포) |
| `apps/desktop/sessions/` | 사용자가 풀던 진행 상황 자동저장 파일 (개인 진행기록이라 git에는 안 올라감) |
| `apps/desktop/tests/` | pytest 테스트 (세션 저장/복구, 코드 실행기, 채점 로직, 딥러닝 문제 실행까지 검증) |
| `tools/ipynb_to_exam.py` | `09_모의고사`의 노트북들을 파싱해서 `모의고사*.json`으로 변환하는 빌드 스크립트 (데스크톱/웹 데이터 공용, 저장소 루트에 위치) |
| `tools/ipynb_to_study.py` | 학습 노트북을 파싱해서 `study_*.json`으로 변환하는 빌드 스크립트 (노트북이 수정되면 다시 실행) |
| `.venv_dl/` | TensorFlow용 Python 3.12 가상환경, 저장소 루트에 위치 — 데스크톱 앱과 `apps/server` 로컬 테스트가 공유 (git에는 안 올라감) |

## ⚠️ 참고

- `AICE_Simulator.exe`를 배포할 땐 `apps/desktop/dist/AICE_Simulator/` 폴더를 zip으로 압축해서 옮기세요.
- 딥러닝(5교시) 문제까지 전부 포함되어 있어서, exe 하나로 모든 시험을 완전히 풀 수 있습니다.
- 웹 버전 개발/배포 관련 내용은 `apps/web/`, `apps/server/` 안의 코드와 저장소 루트의 `render.yaml`을 참고하세요.
