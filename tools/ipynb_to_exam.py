import os
import json
import re
import glob
import nbformat
import traceback
import sys
import pandas as pd
import numpy as np

def parse_notebook(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        nb = nbformat.read(f, as_version=4)
        
    exam_id = os.path.basename(filepath).replace('.ipynb', '')
    title = exam_id
    
    setup_code = ""
    total_points = 100
    total_points_v1 = 0
    
    problems = []
    
    current_session = ""
    in_dl_section = False
    
    prob_re = re.compile(r'^\*\*문제\s+(\d+)\.\*\*\s*(.+)', re.S)
    ans_re = re.compile(r'```python\n(.*?)\n```', re.S)
    header_re = re.compile(r'^##\s+(\d+교시[^<]+)')
    scoring_re = re.compile(r'^##\s+채점 가이드')
    point_re = re.compile(r'\|\s*문제\s+(\d+)\s*\|\s*(\d+)점\s*\|')

    points_dict = {}

    # 문제 1(라이브러리 불러오기+데이터 로딩)부터가 채점 대상이므로, exe에 실제로
    # pre-load 시켜줄 코드는 없습니다. cells[2]는 Jupyter 전용 ExamTimer 기동
    # 셀(aice_grader 모듈은 exe에 없음 - exe는 자체 QTimer를 씀)이라 절대 setup_code로
    # 쓰면 안 됩니다. setup_code는 항상 빈 문자열로 둡니다.
    setup_code = ""

    for cell in nb.cells:
        if cell.cell_type == 'markdown':
            m_header = header_re.match(cell.source)
            if m_header:
                current_session = m_header.group(1).strip()
            if scoring_re.search(cell.source):
                for line in cell.source.split('\n'):
                    m_pt = point_re.search(line)
                    if m_pt:
                        points_dict[int(m_pt.group(1))] = int(m_pt.group(2))
                continue

    i = 0
    while i < len(nb.cells):
        cell = nb.cells[i]

        if cell.cell_type == 'markdown':
            m_header = header_re.match(cell.source)
            if m_header:
                current_session = m_header.group(1).strip()

            m_prob = prob_re.search(cell.source)
            if m_prob:
                prob_no = int(m_prob.group(1))
                prompt = m_prob.group(2).strip()

                answer_code = ""
                if i + 2 < len(nb.cells):
                    ans_cell = nb.cells[i+2]
                    if ans_cell.cell_type == 'markdown':
                        m_ans = ans_re.search(ans_cell.source)
                        if m_ans:
                            answer_code = m_ans.group(1).strip()

                # 5교시(딥러닝) 포함 전 문제를 채점 대상으로 삼습니다 (exe가 통합됐으므로).
                problems.append({
                    "no": prob_no,
                    "session": current_session,
                    "prompt_markdown": prompt,
                    "answer_code": answer_code,
                    "points": 0,
                    "checks": [],
                    "manual_review": False
                })
        i += 1
        
    for p in problems:
        p["points"] = points_dict.get(p["no"], 0)
        total_points_v1 += p["points"]
        
    namespace = {}
    original_cwd = os.getcwd()
    os.chdir(os.path.dirname(filepath))
    
    # Pre-inject matplotlib backends to prevent popups
    exec("import matplotlib; matplotlib.use('Agg')", namespace)
    
    try:
        exec(setup_code, namespace)
        for p in problems:
            try:
                exec(p["answer_code"], namespace)
            except Exception as code_e:
                print(f"Warning: Code execution failed in {exam_id}, prob {p['no']}: {code_e}")
                pass
            
            checks = []

            # 답안 코드에 등장하는 모든 식별자를 훑어서, 실행 후 namespace에 실제로
            # 존재하는 값의 '타입'으로 채점 가능 여부를 판단합니다. (특정 변수명을
            # 하드코딩해서 맞추던 예전 방식은 df/housing/wine처럼 데이터셋마다 변수명이
            # 다른 경우를 다 놓쳐서, checks가 비어 자동 정답 처리되는 사각지대를 만들었음)
            tokens = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', p['answer_code']))
            # loss/mse/rmse/mae는 낮을수록 좋은 지표라 gte(이상)가 아니라 lte(이하)로 체크해야 함.
            # acc/r2/precision/recall/auc/score/f1은 높을수록 좋은 지표라 gte(이상)로 체크.
            # 단순 substring 검색(.search())은 "answer2"(r2 포함), "layer2"(r2 포함),
            # "z_score"(score 포함) 같은 변수명을 오탐지하므로, snake_case 밑줄 단위로 쪼갠
            # 조각이 키워드와 "완전히" 일치할 때만 매칭되도록 합니다.
            lower_is_better_words = {'loss', 'mse', 'rmse', 'mae'}
            higher_is_better_words = {'acc', 'accuracy', 'r2', 'precision', 'recall', 'auc', 'score', 'f1'}

            def _matches_metric_word(name, keyword_set):
                return any(part in keyword_set for part in name.lower().split('_'))

            is_dl = '딥러닝' in p.get('session', '')

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
                    # 딥러닝 지표는 (seed 고정 없이) 재학습할 때마다 값이 흔들리므로,
                    # 이 자연스러운 변동폭까지 오답 처리하지 않도록 여유(margin)를 더 크게 둠.
                    if _matches_metric_word(name, lower_is_better_words):
                        margin_ratio = 0.20 if is_dl else 0.08
                        margin = max(abs(fval) * margin_ratio, 0.02)
                        checks.append({"var": name, "op": "lte", "expected": round(fval + margin, 4), "tolerance": 0.0})
                    elif _matches_metric_word(name, higher_is_better_words):
                        if 0 < fval <= 1.0:
                            margin = 0.08 if is_dl else 0.03
                            checks.append({"var": name, "op": "gte", "expected": round(max(fval - margin, 0.0), 4), "tolerance": 0.0})
                        else:
                            margin_ratio = 0.20 if is_dl else 0.05
                            margin = abs(fval) * margin_ratio
                            checks.append({"var": name, "op": "gte", "expected": round(fval - margin, 4), "tolerance": 0.0})

            if not checks:
                # 그래프만 그리는 문제든, 정말 채점 기준을 못 찾은 문제든, checks가
                # 비어있으면 무조건 manual_review로 넘겨서 "본인 확인" 문구가 뜨게 합니다.
                # (grader.py는 checks가 비어도 manual_review=False면 무조건 정답 처리하므로,
                #  자동 정답 처리되는 사각지대를 완전히 없애기 위한 안전장치입니다.)
                p['manual_review'] = True
                    
            unique_checks = []
            seen = set()
            for c in checks:
                key = f"{c.get('var')}_{c.get('attr', '')}"
                if key not in seen:
                    seen.add(key)
                    unique_checks.append(c)
                    
            p["checks"] = unique_checks
            
    except Exception as e:
        print(f"Error executing exam {exam_id}: {e}")
    finally:
        os.chdir(original_cwd)
        
    exam_data = {
        "exam_id": exam_id,
        "title": exam_id.replace('모의고사', '').replace('_', ' ').strip(),
        "time_limit_minutes": 90,
        "setup_code": setup_code,
        "total_points_v1": total_points_v1,
        "problems": problems
    }
    
    return exam_data

def main():
    target_dir = r"c:\project\Aice\09_모의고사"
    out_dir = r"c:\project\Aice\AICE_Simulator\data"
    os.makedirs(out_dir, exist_ok=True)
    
    nb_files = glob.glob(os.path.join(target_dir, "*.ipynb"))
    for f in nb_files:
        exam_data = parse_notebook(f)
        
        out_file = os.path.join(out_dir, f"{exam_data['exam_id']}.json")
        with open(out_file, 'w', encoding='utf-8') as out_f:
            json.dump(exam_data, out_f, ensure_ascii=False, indent=2)
            
        num_probs = len(exam_data['problems'])
        num_checks = sum(1 for p in exam_data['problems'] if len(p['checks']) > 0)
        num_manual = sum(1 for p in exam_data['problems'] if p['manual_review'])
        num_blind = sum(1 for p in exam_data['problems'] if not p['checks'] and not p['manual_review'])

        print(f"[{exam_data['exam_id']}] 총 문제 수: {num_probs} / checks 생성: {num_checks} / manual_review: {num_manual} / 채점 사각지대(비어있음): {num_blind}")

if __name__ == "__main__":
    main()
