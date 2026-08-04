import os
import sys
import shutil

import nbformat
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.ipynb_to_study import parse_notebook, annotate_checks


def _make_synthetic_notebook(path):
    """실제 학습 노트북(02_NumPy_Pandas_기초 등)과 동일한 셀 패턴을 갖는 최소 노트북을
    합성해서, 원본 노트북 파일 없이도(다른 PC에서도) 파서를 테스트할 수 있게 합니다."""
    nb = nbformat.v4.new_notebook()
    md = nbformat.v4.new_markdown_cell
    code = nbformat.v4.new_code_cell
    nb.cells = [
        md("# 테스트 챕터 - 합성 노트북"),
        md("## 목차"),
        code("import numpy as np"),
        code("extra_setup = 42"),  # 섹션 시작 전 두 번째 code cell -> setup_code에 이어붙여져야 함
        md("## 1. 섹션 하나"),
        md("### 📖 이론 설명\n이론 내용입니다."),
        md("### 🧩 핵심 개념 정리\n| 함수 | 설명 |\n|---|---|\n| np.array | 배열 생성 |"),
        md("### 💻 예제 코드"),
        code("y = np.array([1, 2, 3])"),
        md("### ✍️ TODO: 실전 문제"),
        md("**문제 1.** 정수 3개짜리 배열 `z`를 만드세요."),
        code("# 여기에 코드를 작성하세요"),
        md("<details>\n<summary>정답 보기</summary>\n\n```python\nz = np.array([4, 5, 6])\n```\n\n</details>"),
        md("**문제 2.** `w`를 만드세요."),
        code("# 여기에 코드를 작성하세요"),
        md("<details>\n<summary>정답 보기</summary>\n\n```python\nw = np.zeros(3)\n```\n\n</details>"),
        md("## 2. 섹션 둘"),
        md("### 📖 이론 설명\n둘째 섹션 이론."),
        md("### 🧩 핵심 개념 정리\n둘째 섹션 표."),
        md("### 💻 예제 코드"),
        code("q = 1"),
        md("### ✍️ TODO: 실전 문제"),
        md("**문제 1.** `q`를 출력하세요 (변수 할당 없음 -> manual_review 대상)."),
        code("# 여기에 코드를 작성하세요"),
        md("<details>\n<summary>정답 보기</summary>\n\n```python\nprint(q)\n```\n\n</details>"),
        # 실무전용 챕터처럼 이론/예제 없이 "## 소제목" 바로 아래 문제만 있는 섹션 + 빈 TODO 셀에
        # toy 데이터가 숨어있는 케이스(04_데이터전처리_실무전용에서 실제로 발견된 패턴)
        md("## 3. 섹션 셋 (실무전용 스타일)"),
        md("**문제 1.** 아래 `toy`에서 결측치를 제거하세요."),
        code("toy = np.array([1, np.nan, 3])\n# 여기에 코드를 작성하세요"),
        md("<details>\n\n```python\ntoy_clean = toy[~np.isnan(toy)]\n```\n\n</details>"),
    ]
    with open(path, 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)


@pytest.fixture
def synthetic_chapter(tmp_path):
    nb_path = tmp_path / "테스트챕터.ipynb"
    _make_synthetic_notebook(nb_path)
    return nb_path


def test_parse_notebook_structure(synthetic_chapter):
    data = parse_notebook(str(synthetic_chapter))

    assert data["chapter_id"] == "테스트챕터"
    # 첫 "## N." 섹션이 나오기 전의 code cell 2개가 모두 setup_code로 이어붙여져야 함
    assert data["setup_code"] == "import numpy as np\n\nextra_setup = 42"
    assert len(data["sections"]) == 3

    sec1 = data["sections"][0]
    assert sec1["no"] == 1
    assert sec1["title"] == "섹션 하나"
    assert "이론 내용입니다" in sec1["theory_markdown"]
    assert "np.array" in sec1["concept_table_markdown"]
    assert sec1["example_code"] == "y = np.array([1, 2, 3])"
    assert len(sec1["practices"]) == 2
    assert sec1["practices"][0]["no"] == 1
    assert sec1["practices"][0]["answer_code"] == "z = np.array([4, 5, 6])"
    assert sec1["practices"][1]["answer_code"] == "w = np.zeros(3)"

    sec2 = data["sections"][1]
    assert sec2["no"] == 2
    assert sec2["example_code"] == "q = 1"
    assert len(sec2["practices"]) == 1
    assert sec2["practices"][0]["answer_code"] == "print(q)"

    # 이론/개념표/예제 헤더 없이 "## 소제목" 바로 아래 문제만 있는 실무전용 스타일 섹션
    sec3 = data["sections"][2]
    assert sec3["no"] == 3
    assert sec3["theory_markdown"] == ""
    assert sec3["example_code"] == ""
    assert len(sec3["practices"]) == 1
    # 빈 TODO 셀에 숨어있던 "toy = ..." 정의가 플레이스홀더 주석만 빼고 starter_code로 추출돼야 함
    assert sec3["practices"][0]["starter_code"] == "toy = np.array([1, np.nan, 3])"
    assert sec3["practices"][0]["answer_code"] == "toy_clean = toy[~np.isnan(toy)]"


def test_annotate_checks_generates_and_flags_manual_review(synthetic_chapter, tmp_path):
    data = parse_notebook(str(synthetic_chapter))
    exec_cwd = tmp_path / "exec_cwd"
    exec_cwd.mkdir()

    annotate_checks(data, exec_cwd=str(exec_cwd))

    sec1_p1 = data["sections"][0]["practices"][0]
    assert sec1_p1["manual_review"] is False
    assert any(c["var"] == "z" and c["attr"] == "shape" and c["expected"] == [3] for c in sec1_p1["checks"])

    # 문제 2("w = np.zeros(3)")도 shape 체크가 생성되어야 함
    sec1_p2 = data["sections"][0]["practices"][1]
    assert sec1_p2["manual_review"] is False
    assert any(c["var"] == "w" for c in sec1_p2["checks"])

    # print(q)는 새 변수를 할당하지 않으므로 checks가 비어 manual_review로 빠져야 함
    sec2_p1 = data["sections"][1]["practices"][0]
    assert sec2_p1["checks"] == []
    assert sec2_p1["manual_review"] is True

    # starter_code(toy 정의)가 answer_code 실행 전에 먼저 exec되지 않으면 NameError로 실패해서
    # checks가 비고 manual_review=True가 됐을 것 -> starter_code가 제대로 반영됐는지 검증
    sec3_p1 = data["sections"][2]["practices"][0]
    assert sec3_p1["manual_review"] is False
    assert any(c["var"] == "toy_clean" for c in sec3_p1["checks"])
