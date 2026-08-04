"""
학습 노트북(이론→개념정리→예제→TODO 실전문제 반복 구조)을 파싱해서
data/study_<chapter_id>.json으로 변환합니다.

09_모의고사(ipynb_to_exam.py)와 다른 점: 노트북이 "문제"만 반복되는 게 아니라
"## N. 소제목" 아래에 [이론 → 개념표 → 예제코드 → TODO 문제들]이 세트로 반복됩니다.
그래서 고정 오프셋이 아니라 헤더를 보고 상태를 바꿔가며 순회하는 상태머신으로 파싱합니다.

원본 노트북(C:\\myfolder\\certification\\following-along-aice-associate\\)은 읽기 전용입니다.
이 스크립트는 절대 원본 노트북을 수정하지 않습니다 — data/*.json만 새로 만듭니다.
"""
import os
import json
import re
import glob
import nbformat
import pandas as pd
import numpy as np

SECTION_RE = re.compile(r'^##\s+(?!목차)(\d+)\.\s*(.+)')
THEORY_RE = re.compile(r'^###\s*📖\s*이론 설명')
CONCEPT_RE = re.compile(r'^###\s*🧩\s*핵심 개념 정리')
EXAMPLE_RE = re.compile(r'^###\s*💻\s*예제 코드')
TODO_RE = re.compile(r'^###\s*✍️\s*TODO')
PROB_RE = re.compile(r'^\*\*문제\s+(\d+)\.\*\*\s*(.+)', re.S)
ANS_RE = re.compile(r'```python\n(.*?)\n```', re.S)

LOWER_IS_BETTER_WORDS = {'loss', 'mse', 'rmse', 'mae'}
HIGHER_IS_BETTER_WORDS = {'acc', 'accuracy', 'r2', 'precision', 'recall', 'auc', 'score', 'f1'}


def _matches_metric_word(name, keyword_set):
    return any(part in keyword_set for part in name.lower().split('_'))


def _fix_data_path(code):
    return code.replace("../data/", "data/")


PLACEHOLDER_LINE_RE = re.compile(r'^#\s*여기에\s*(코드|답안)를?\s*작성하세요\s*$')


def _extract_starter_code(code_source):
    """빈 TODO 코드 셀에서 '# 여기에 코드를 작성하세요' 플레이스홀더 줄만 제거하고,
    실제로 남는 코드(toy 데이터 정의, 답안 변수 초기화 등)가 있으면 반환합니다."""
    lines = [l for l in code_source.split('\n') if not PLACEHOLDER_LINE_RE.match(l.strip())]
    remaining = '\n'.join(lines).strip()
    return remaining


def _append(existing, addition, sep="\n\n"):
    """한 섹션 안에 이론/개념표/예제코드 블록이 여러 번 나오는 챕터도 있어서, 덮어쓰지 않고
    이어붙입니다 (내용 유실 방지)."""
    if not existing:
        return addition
    return existing + sep + addition


def parse_notebook(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        nb = nbformat.read(f, as_version=4)

    chapter_id = os.path.basename(filepath).replace('.ipynb', '')
    title = nb.cells[0].source.split('\n')[0].lstrip('#').strip() if nb.cells else chapter_id

    setup_code = ""
    sections = []
    cur = None

    cells = nb.cells
    i = 0
    while i < len(cells):
        cell = cells[i]
        src = cell.source.strip()

        if cell.cell_type == 'code' and cur is None and not sections:
            # 제목/목차 뒤, 첫 "## N." 섹션이 나오기 전까지의 code cell은 전부 setup_code로 취급합니다.
            # (일부 챕터는 데이터 로딩 뒤에 train/test 분할·스케일링 같은 준비 코드를 별도 code cell로
            #  하나 더 두는데, 첫 cell만 setup_code로 삼으면 이 준비 코드가 통째로 유실됩니다.)
            setup_code = _append(setup_code, _fix_data_path(cell.source.strip()))
            i += 1
            continue

        if cell.cell_type == 'markdown':
            m_sec = SECTION_RE.match(src)
            if m_sec:
                if cur is not None:
                    sections.append(cur)
                cur = {
                    "no": int(m_sec.group(1)),
                    "title": m_sec.group(2).strip(),
                    "theory_markdown": "",
                    "concept_table_markdown": "",
                    "example_code": "",
                    "practices": [],
                }
                i += 1
                continue

            if cur is not None and THEORY_RE.match(src):
                cur["theory_markdown"] = _append(cur["theory_markdown"], cell.source.strip())
                i += 1
                continue

            if cur is not None and CONCEPT_RE.match(src):
                cur["concept_table_markdown"] = _append(cur["concept_table_markdown"], cell.source.strip())
                i += 1
                continue

            if cur is not None and EXAMPLE_RE.match(src):
                i += 1
                if i < len(cells) and cells[i].cell_type == 'code':
                    cur["example_code"] = _append(cur["example_code"], _fix_data_path(cells[i].source.strip()))
                    i += 1
                continue

            if TODO_RE.match(src):
                # "### ✍️ TODO" 헤더는 상태 전환용 마커가 아니라 그냥 지나갑니다.
                # 문제 인식은 아래 PROB_RE가 섹션 안 어디서든(TODO 헤더 유무와 무관하게) 전담합니다.
                # (일부 챕터는 이 헤더 없이 "## 소제목" 바로 아래에 문제를 두거나, 반대로 이 헤더가
                #  있어도 문제가 여러 하위 블록에 흩어져 있어, 헤더 의존 파싱은 문제를 누락시켰습니다.)
                i += 1
                continue

            if cur is not None:
                m_prob = PROB_RE.match(src)
                if m_prob:
                    prob_no = int(m_prob.group(1))
                    prompt = m_prob.group(2).strip()
                    answer_code = ""
                    if i + 2 < len(cells) and cells[i + 2].cell_type == 'markdown':
                        m_ans = ANS_RE.search(cells[i + 2].source)
                        if m_ans:
                            answer_code = _fix_data_path(m_ans.group(1).strip())

                    # 빈 TODO 코드 셀("여기에 코드를 작성하세요")이 항상 진짜로 비어있는 건 아닙니다.
                    # 일부 문제는 그 자리에 학생이 이어서 쓸 toy 데이터(예: `toy = pd.DataFrame(...)`)나
                    # 그래프 해석형 문제의 시각화 코드+답안 변수 초기화(`답안1 = None`)를 미리 넣어둡니다.
                    # 이 내용은 정답 코드 실행에도 필요하고, 학습 화면의 코드 에디터 초기값으로도 써야 합니다.
                    starter_code = ""
                    if i + 1 < len(cells) and cells[i + 1].cell_type == 'code':
                        starter_code = _extract_starter_code(cells[i + 1].source)

                    practice = {
                        "no": prob_no,
                        "prompt_markdown": prompt,
                        "answer_code": answer_code,
                        "checks": [],
                        "manual_review": False,
                    }
                    if starter_code:
                        practice["starter_code"] = _fix_data_path(starter_code)
                    cur["practices"].append(practice)
                    i += 3
                    continue

        if cell.cell_type == 'code' and cur is not None:
            # "### 💻 예제 코드" 헤더 없이 섹션 중간에 그냥 놓인 code cell(추가 준비/설명 코드).
            # 헤더가 없다고 건너뛰면 뒤따르는 문제가 필요로 하는 변수가 조용히 사라지므로,
            # 섹션의 example_code에 이어붙여서 항상 실행되게 합니다.
            cur["example_code"] = _append(cur["example_code"], _fix_data_path(cell.source.strip()))
            i += 1
            continue

        i += 1

    if cur is not None:
        sections.append(cur)

    return {
        "chapter_id": chapter_id,
        "title": title,
        "setup_code": setup_code,
        "sections": sections,
    }


def _generate_checks(namespace, code, is_dl=False):
    """tools/ipynb_to_exam.py의 checks 자동 생성 로직과 동일 (그대로 재사용).
    딥러닝 챕터는 (seed 고정 없이) 재학습마다 정확도/손실이 흔들리므로 여유(margin)를 더 크게 둡니다."""
    checks = []
    tokens = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', code))

    for name in sorted(tokens):
        if name not in namespace:
            continue
        val = namespace[name]

        if isinstance(val, (pd.DataFrame, pd.Series, np.ndarray)):
            try:
                checks.append({"var": name, "attr": "shape", "op": "eq", "expected": list(val.shape)})
            except Exception:
                pass
        elif isinstance(val, (float, int)) and not isinstance(val, bool):
            fval = float(val)
            if _matches_metric_word(name, LOWER_IS_BETTER_WORDS):
                margin_ratio = 0.20 if is_dl else 0.08
                margin = max(abs(fval) * margin_ratio, 0.02)
                checks.append({"var": name, "op": "lte", "expected": round(fval + margin, 4), "tolerance": 0.0})
            elif _matches_metric_word(name, HIGHER_IS_BETTER_WORDS):
                if 0 < fval <= 1.0:
                    margin = 0.08 if is_dl else 0.03
                    checks.append({"var": name, "op": "gte", "expected": round(max(fval - margin, 0.0), 4), "tolerance": 0.0})
                else:
                    margin_ratio = 0.20 if is_dl else 0.05
                    margin = abs(fval) * margin_ratio
                    checks.append({"var": name, "op": "gte", "expected": round(fval - margin, 4), "tolerance": 0.0})

    unique_checks = []
    seen = set()
    for c in checks:
        key = f"{c.get('var')}_{c.get('attr', '')}"
        if key not in seen:
            seen.add(key)
            unique_checks.append(c)
    return unique_checks


def annotate_checks(chapter_data, exec_cwd):
    """setup_code -> (섹션별: example_code -> 각 practice의 answer_code)를 문서 순서대로
    하나의 지속 namespace에 누적 실행하면서, 각 practice 실행 직후 상태로 checks를 생성합니다.
    (예제 코드가 만든 변수를 뒤따르는 TODO 문제가 그대로 참조하는 노트북 관례를 그대로 반영)
    """
    is_dl = '딥러닝' in chapter_data.get('title', '') or '딥러닝' in chapter_data.get('chapter_id', '')

    namespace = {}
    original_cwd = os.getcwd()
    os.chdir(exec_cwd)
    try:
        exec("import matplotlib; matplotlib.use('Agg')", namespace)
        try:
            exec(chapter_data["setup_code"], namespace)
        except Exception as e:
            print(f"  Warning: setup_code 실행 실패: {e}")

        for sec in chapter_data["sections"]:
            try:
                exec(sec["example_code"], namespace)
            except Exception as e:
                print(f"  Warning: [{sec['no']}. {sec['title']}] 예제 코드 실행 실패: {e}")

            for p in sec["practices"]:
                try:
                    if p.get("starter_code"):
                        exec(p["starter_code"], namespace)
                    exec(p["answer_code"], namespace)
                except Exception as e:
                    print(f"  Warning: [{sec['no']}. {sec['title']}] 문제 {p['no']} 정답 코드 실행 실패: {e}")

                checks = _generate_checks(namespace, p["answer_code"], is_dl=is_dl)
                if not checks:
                    p["manual_review"] = True
                p["checks"] = checks
    finally:
        os.chdir(original_cwd)


EXCLUDED_DIRS = {
    "09_모의고사",     # 모의고사 모드가 이미 사용 중
    "99_전체통합본",   # 다른 챕터를 그대로 합친 중복 파일
    "00_시작하기",     # 이론/예제/TODO 구조가 아니라 진단 퀴즈+치트시트+에러가이드 모음이라 학습 모드 패턴과 다름
}


def main():
    source_root = r"C:\myfolder\certification\following-along-aice-associate"
    out_dir = r"C:\myfolder\project\AICE_Simulator\data"
    os.makedirs(out_dir, exist_ok=True)
    sim_root = os.path.dirname(out_dir)

    nb_files = []
    for entry in sorted(os.listdir(source_root)):
        if entry in EXCLUDED_DIRS or not os.path.isdir(os.path.join(source_root, entry)):
            continue
        for f in sorted(glob.glob(os.path.join(source_root, entry, "*.ipynb"))):
            # 기본판 + 심화(_실무전용)판 둘 다 별도 챕터로 만듭니다 (chapter_id에 이미
            # "_실무전용" 접미사가 붙어 있어 파일명이 겹치지 않음).
            nb_files.append(f)

    for f in nb_files:
        chapter_data = parse_notebook(f)
        annotate_checks(chapter_data, exec_cwd=sim_root)

        out_name = f"study_{chapter_data['chapter_id']}.json"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, 'w', encoding='utf-8') as out_f:
            json.dump(chapter_data, out_f, ensure_ascii=False, indent=2)

        num_sections = len(chapter_data["sections"])
        num_practices = sum(len(s["practices"]) for s in chapter_data["sections"])
        num_checks = sum(1 for s in chapter_data["sections"] for p in s["practices"] if p["checks"])
        num_manual = sum(1 for s in chapter_data["sections"] for p in s["practices"] if p["manual_review"])

        print(f"[{chapter_data['chapter_id']}] -> {out_name}")
        print(f"  섹션 수: {num_sections} / TODO 문제 수: {num_practices} / checks 생성: {num_checks} / manual_review: {num_manual}")


if __name__ == "__main__":
    main()
