import os
import sys
import shutil

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.study_progress_manager import StudyProgressManager


@pytest.fixture
def temp_sessions_dir():
    dir_path = "temp_study_sessions_test"
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    yield dir_path
    shutil.rmtree(dir_path)


def test_save_load_roundtrip(temp_sessions_dir):
    pm = StudyProgressManager(sessions_dir=temp_sessions_dir)
    pm.create_new_session("02_numpy_pandas")

    pm.update_state(current_section_no=3, code_updates={"1-1": "arr = np.array([1,2,3])"})
    pm.mark_section_completed(1)
    pm.save_now()

    saved_file = pm.session_file

    pm2 = StudyProgressManager(sessions_dir=temp_sessions_dir)
    pm2.load_session(saved_file)

    data1, data2 = pm.get_data(), pm2.get_data()
    assert data1 == data2
    assert data2["current_section_no"] == 3
    assert data2["practice_code_by_id"]["1-1"] == "arr = np.array([1,2,3])"
    assert data2["completed_sections"] == [1]


def test_record_result_wrong_list(temp_sessions_dir):
    pm = StudyProgressManager(sessions_dir=temp_sessions_dir)
    pm.create_new_session("02_numpy_pandas")

    # 오답 -> 오답 리스트에 들어감
    pm.record_result("1-1", is_correct=False, revealed_answer=False)
    assert "1-1" in pm.get_data()["wrong_practice_ids"]

    # 스스로 다시 풀어서 정답 -> 리스트에서 빠짐
    pm.record_result("1-1", is_correct=True, revealed_answer=False)
    assert "1-1" not in pm.get_data()["wrong_practice_ids"]

    # 정답 보기를 사용한 뒤 채점 -> 오답 리스트에 남음(revealed_answer=True)
    pm.mark_revealed("1-2")
    pm.record_result("1-2", is_correct=False, revealed_answer=True)
    assert "1-2" in pm.get_data()["wrong_practice_ids"]
    assert pm.is_revealed("1-2") is True


def test_review_mode_helpers(temp_sessions_dir):
    pm = StudyProgressManager(sessions_dir=temp_sessions_dir)
    pm.create_new_session("02_numpy_pandas")

    pm.ensure_in_wrong_list("3-2")
    assert "3-2" in pm.get_data()["wrong_practice_ids"]

    pm.update_practice_result_only("3-2", True)
    assert pm.get_data()["practice_results_by_id"]["3-2"]["is_correct"] is True
    # update_practice_result_only 자체는 wrong_practice_ids를 건드리지 않음
    assert "3-2" in pm.get_data()["wrong_practice_ids"]

    pm.remove_from_wrong_list("3-2")
    assert "3-2" not in pm.get_data()["wrong_practice_ids"]


def test_reset_progress(temp_sessions_dir):
    pm = StudyProgressManager(sessions_dir=temp_sessions_dir)
    pm.create_new_session("02_numpy_pandas")

    pm.update_state(current_section_no=4, code_updates={"1-1": "x = 1"})
    pm.mark_section_completed(1)
    pm.mark_section_completed(2)
    pm.record_result("1-1", is_correct=False, revealed_answer=False)
    pm.mark_revealed("1-2")
    pm.mark_chapter_completed()

    session_file_before = pm.session_file
    chapter_id_before = pm.get_data()["chapter_id"]

    pm.reset_progress()
    data = pm.get_data()

    # 세션 파일/챕터 아이디는 그대로 재사용된다 (새 세션을 만드는 게 아니라 기존 걸 초기화)
    assert pm.session_file == session_file_before
    assert data["chapter_id"] == chapter_id_before

    assert data["current_section_no"] == 1
    assert data["practice_code_by_id"] == {}
    assert data["practice_results_by_id"] == {}
    assert data["wrong_practice_ids"] == []
    assert data["revealed_practice_ids"] == []
    assert data["completed_sections"] == []
    assert data["is_completed"] is False


def test_find_unfinished_filters_by_chapter_and_completion(temp_sessions_dir):
    # 서로 다른 챕터 id를 써서, 같은 초(second)에 두 세션이 생성되어 타임스탬프 파일명이
    # 충돌하는 상황(SessionManager와 동일한 기존 설계상 한계)을 피합니다.
    pm = StudyProgressManager(sessions_dir=temp_sessions_dir)

    pm.create_new_session("chapter_a")
    pm.save_now()

    pm.create_new_session("chapter_b")
    pm.mark_chapter_completed()
    pm.save_now()

    pm.create_new_session("chapter_c")
    pm.save_now()

    all_unfinished = pm.find_unfinished_sessions()
    assert len(all_unfinished) == 2  # chapter_b는 완료되어 제외

    chapter_a_only = pm.find_unfinished_sessions(chapter_id="chapter_a")
    assert len(chapter_a_only) == 1
    assert "chapter_a" in str(chapter_a_only[0])
