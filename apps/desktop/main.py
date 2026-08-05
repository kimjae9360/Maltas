import sys
import os
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox

# PyInstaller가 정적 분석만으로는 못 찾는 의존성들.
# 실제 사용은 문제 답안 코드가 exec()로 동적 임포트하는 형태라 여기서
# 직접 import해둬야 PyInstaller가 tensorflow/딥러닝 관련 라이브러리를 통째로 묶는다.
import pandas as pd
import numpy as np
import sklearn
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
import xgboost
import lightgbm
import imblearn
import tensorflow as tf

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow
from ui.exam_select_dialog import ExamSelectDialog
from ui.study_select_dialog import StudySelectDialog
from ui.study_window import StudyWindow
from ui.mode_select_dialog import ModeSelectDialog
from engine.session_manager import SessionManager
from engine.study_progress_manager import StudyProgressManager
from resource_path import get_base_dir, get_writable_dir


def run_study_mode(app, data_dir, writable_dir):
    dialog = StudySelectDialog(data_dir)
    if dialog.exec() != StudySelectDialog.Accepted or not dialog.selected_chapter_id:
        return
    chapter_id = dialog.selected_chapter_id

    chapter_json = data_dir / f"study_{chapter_id}.json"
    if not chapter_json.exists():
        QMessageBox.critical(None, "오류", f"학습 데이터 파일이 없습니다: {chapter_json}")
        return

    with open(chapter_json, 'r', encoding='utf-8') as f:
        chapter_data = json.load(f)

    pm = StudyProgressManager(sessions_dir=str(writable_dir / "sessions"))
    unfinished = pm.find_unfinished_sessions(chapter_id)

    session_file = None
    if unfinished:
        reply = QMessageBox.question(None, "이어서 학습하기",
                                     f"'{chapter_data['title']}'의 진행 중이던 학습 기록이 있습니다. 이어서 진행하시겠습니까?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            session_file = unfinished[0]

    if session_file:
        pm.load_session(session_file)
    else:
        pm.create_new_session(chapter_id)

    window = StudyWindow(chapter_data, pm)
    window.showMaximized()
    sys.exit(app.exec())


def main():
    app = QApplication(sys.argv)
    base_dir = Path(get_base_dir())
    writable_dir = Path(get_writable_dir())
    data_dir = base_dir / "data"

    # 0. 모드 선택 (모의고사 / 학습)
    mode_dialog = ModeSelectDialog()
    mode_dialog.exec()

    if mode_dialog.selected_mode == "study":
        run_study_mode(app, data_dir, writable_dir)
        return
    elif mode_dialog.selected_mode != "exam":
        return

    # 1. 시험 선택
    dialog = ExamSelectDialog(data_dir)
    if dialog.exec() != ExamSelectDialog.Accepted or not dialog.selected_exam_id:
        return
    exam_id = dialog.selected_exam_id

    exam_json = data_dir / f"{exam_id}.json"
    if not exam_json.exists():
        QMessageBox.critical(None, "오류", f"시험 데이터 파일이 없습니다: {exam_json}")
        return

    with open(exam_json, 'r', encoding='utf-8') as f:
        exam_data = json.load(f)

    # 2. 선택한 시험에 대해서만 미완료 세션 확인 (다른 시험의 세션과 섞이지 않도록)
    sm = SessionManager(sessions_dir=str(writable_dir / "sessions"))
    unfinished = [p for p in sm.find_unfinished_sessions() if p.name.startswith(f"{exam_id}_")]

    session_file = None
    if unfinished:
        reply = QMessageBox.question(None, "이어서 풀기",
                                     f"'{exam_data['title']}'의 미완료 세션이 {len(unfinished)}개 있습니다. 가장 최근 세션을 이어서 푸시겠습니까?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            session_file = unfinished[0]

    # 3. Create or load session
    if session_file:
        sm.load_session(session_file)
    else:
        sm.create_new_session(exam_id, time_limit_minutes=exam_data["time_limit_minutes"])

    # 4. Show window
    window = MainWindow(exam_data, sm)
    window.showMaximized()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
