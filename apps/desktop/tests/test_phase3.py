import pytest
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.code_executor import CodeExecutor
from engine.grader import Grader
from resource_path import get_base_dir

# setup_code의 'data/train.csv' 등은 AICE_Simulator 루트(=data/의 부모) 기준 상대경로
working_dir_path = get_base_dir()

@pytest.fixture
def mock_exam_data():
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                             'data', '모의고사01_Titanic_생존자예측.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_full_exam_correct_answers(mock_exam_data):
    executor = CodeExecutor(mock_exam_data['setup_code'], working_dir=working_dir_path)
    grader = Grader()
    
    all_problems = {}
    for p in mock_exam_data['problems']:
        all_problems[p['no']] = p['answer_code']
        
    for p in mock_exam_data['problems']:
        timeout = 180.0 if "딥러닝" in p.get("session", "") else 30.0
        namespace, out, err = executor.run_problem(p['no'], p['answer_code'], all_problems, timeout=timeout)

        if err:
            print(f"Error in problem {p['no']}: {err}")
            
        is_correct, detail = grader.grade_problem(namespace, p)
        
        assert is_correct is True, f"Problem {p['no']} failed grading with correct code. Detail: {detail}"
        
        if p.get("manual_review"):
            assert "[본인이 직접 확인]" in detail

def test_incorrect_code_fails_grading(mock_exam_data):
    executor = CodeExecutor(mock_exam_data['setup_code'], working_dir=working_dir_path)
    grader = Grader()
    
    p1 = mock_exam_data['problems'][0]
    assert p1['no'] == 1
    
    wrong_code = "df = df.drop(0)"
    
    namespace, out, err = executor.run_problem(1, wrong_code, {})
    is_correct, detail = grader.grade_problem(namespace, p1)
    
    assert is_correct is False
    assert "일치하지 않습니다" in detail or "찾을 수 없습니다" in detail

if __name__ == "__main__":
    print("=== 채점 엔진(Grader) 수동 테스트 ===")
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                             'data', '모의고사01_Titanic_생존자예측.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        exam_data = json.load(f)
        
    executor = CodeExecutor(exam_data['setup_code'], working_dir=working_dir_path)
    grader = Grader()
    
    p1 = exam_data['problems'][0]
    ns, out, err = executor.run_problem(1, p1['answer_code'], {})
    is_correct, detail = grader.grade_problem(ns, p1)
    print("1. 정답 코드 입력 시:")
    print(f"결과: {is_correct} / 코멘트: {detail}")
    
    wrong_code = "df = df.drop(0)"
    ns, out, err = executor.run_problem(1, wrong_code, {})
    is_correct, detail = grader.grade_problem(ns, p1)
    print("\n2. 오답 코드 (df 행 하나 삭제) 입력 시:")
    print(f"결과: {is_correct} / 코멘트: {detail}")
    
    p_manual = next(p for p in exam_data['problems'] if p.get("manual_review"))
    ns, out, err = executor.run_problem(p_manual['no'], p_manual['answer_code'], {})
    is_correct, detail = grader.grade_problem(ns, p_manual)
    print(f"\n3. 시각화 등 수동 확인 문제 (문제 {p_manual['no']}) 채점 시:")
    print(f"결과: {is_correct} / 코멘트: {detail}")
