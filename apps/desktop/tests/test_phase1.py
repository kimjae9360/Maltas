import pytest
import time
import os
import shutil
from pathlib import Path
import sys

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.session_manager import SessionManager

@pytest.fixture
def temp_sessions_dir():
    dir_path = "temp_sessions_test"
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    yield dir_path
    shutil.rmtree(dir_path)

def test_session_save_load(temp_sessions_dir):
    manager = SessionManager(sessions_dir=temp_sessions_dir)
    manager.create_new_session("test_exam_01")
    
    # Update some states
    manager.update_state(elapsed_seconds=120, current_problem_no=3, 
                         code_updates={1: "print('hello')", 3: "df.head()"},
                         graded_updates={1: {"is_correct": True, "points_earned": 6}})
    manager.save_now()
    
    saved_file = manager.session_file
    
    # Create new manager and load
    manager2 = SessionManager(sessions_dir=temp_sessions_dir)
    manager2.load_session(saved_file)
    
    data1 = manager.get_data()
    data2 = manager2.get_data()
    
    assert data1 == data2
    assert data2["elapsed_seconds"] == 120
    assert data2["current_problem_no"] == 3
    assert data2["code_by_problem"]["1"] == "print('hello')"
    assert data2["graded_results"]["1"]["is_correct"] is True

def test_find_unfinished(temp_sessions_dir):
    manager = SessionManager(sessions_dir=temp_sessions_dir)
    
    # finished session
    manager.create_new_session("finished_exam")
    manager.update_state(elapsed_seconds=5500, current_problem_no=14) # 5500 > 90*60 (5400)
    manager.save_now()
    
    # unfinished session
    manager.create_new_session("unfinished_exam")
    manager.update_state(elapsed_seconds=1000, current_problem_no=5)
    manager.save_now()
    
    unfinished = manager.find_unfinished_sessions()
    assert len(unfinished) == 1
    assert "unfinished_exam" in str(unfinished[0])

if __name__ == "__main__":
    print("=== 강제 종료 시나리오 수동 테스트 ===")
    test_dir = "temp_sessions_manual"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
        
    print("1. 프로그램 실행 및 세션 시작")
    manager = SessionManager(sessions_dir=test_dir)
    manager.create_new_session("모의고사01_Titanic", time_limit_minutes=90)
    
    print("2. 문제 3번에서 코드 입력 (on_code_changed 트리거)")
    manager.update_state(current_problem_no=3, elapsed_seconds=300)
    manager.on_code_changed(3, "import pandas as pd\ndf = pd.read_csv('train.csv')")
    
    print("3. 6초 대기 (5초 디바운스 자동 저장 확인)")
    for i in range(6):
        time.sleep(1)
        print(f"  대기 중... {i+1}초")
        
    print("4. 작업관리자로 강제 종료(sys.exit) 시뮬레이션!")
    
    # Check what was saved on disk before exiting
    saved_file = manager.session_file
    
    print("\n--- [강제 종료됨] ---\n")
    
    print("5. 프로그램 재실행 및 복구 다이얼로그 확인")
    new_manager = SessionManager(sessions_dir=test_dir)
    unfinished_sessions = new_manager.find_unfinished_sessions()
    
    if unfinished_sessions:
        print(f"-> 미완료 세션을 {len(unfinished_sessions)}개 발견했습니다!")
        target_session = unfinished_sessions[0]
        print(f"-> 복구 파일: {target_session.name}")
        new_manager.load_session(target_session)
        
        data = new_manager.get_data()
        print("\n[복구된 데이터 확인]")
        print(f"- 현재 문제 번호: {data['current_problem_no']}")
        print(f"- 경과 시간: {data['elapsed_seconds']}초")
        print(f"- 작성 중이던 문제 3번 코드:\n{data['code_by_problem'].get('3', '')}")
        
        if data['code_by_problem'].get('3') == "import pandas as pd\ndf = pd.read_csv('train.csv')":
            print("\n✅ 강제 종료 시나리오 검증 완료: 디바운스 저장을 통해 코드가 완벽히 복구되었습니다.")
        else:
            print("\n❌ 실패: 코드가 저장되지 않았습니다.")
    else:
        print("❌ 실패: 미완료 세션을 찾지 못했습니다.")
        
    shutil.rmtree(test_dir)
