import threading
import html as html_mod

import markdown
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                               QTextBrowser, QLabel, QScrollArea, QWidget,
                               QPlainTextEdit, QFrame, QToolTip, QApplication)
from PySide6.QtGui import QFont, QCursor
from PySide6.QtCore import Qt, Signal, Slot

from engine.code_executor import CodeExecutor
from resource_path import get_base_dir
from ui.highlighter import PythonHighlighter
from ui.markdown_utils import make_code_copyable, extract_copy_text


def _unit_idx(section_no, practice_no=0):
    return section_no * 100 + practice_no


class StudyReviewDialog(QDialog):
    """챕터를 진행하며 스스로 풀지 못했던(오답/정답보기) TODO 문제만 모아,
    그 자리에서 다시 풀어볼 수 있게 하는 복습 모드. review_note_dialog.py의 HTML 카드
    레이아웃을 재사용하되, 정적 조회가 아니라 코드에디터+재채점이 가능하도록 확장한 버전."""

    grade_result_signal = Signal(str, bool, str)

    def __init__(self, chapter_data, wrong_ids, grader, base_executor, units, progress_manager, parent=None):
        super().__init__(parent)
        self.chapter_data = chapter_data
        self.grader = grader
        self.progress_manager = progress_manager
        self.units = units
        # 부모 창의 executor 콜백을 가로채지 않도록 독립된 실행기를 새로 만듭니다.
        self.executor = CodeExecutor(chapter_data["setup_code"], working_dir=get_base_dir())

        self.items = self._collect_items(chapter_data, wrong_ids)
        self._cards = {}  # pid -> {status_label, code_editor}

        self.setWindowTitle(f"복습 모드 - {chapter_data.get('title', '')}")
        self.resize(1000, 800)
        self._setup_ui()

        self.grade_result_signal.connect(self._on_grade_result)

    def _collect_items(self, chapter_data, wrong_ids):
        items = []
        for pid in wrong_ids:
            try:
                sec_no_str, prac_no_str = pid.split("-")
                sec_no, prac_no = int(sec_no_str), int(prac_no_str)
            except ValueError:
                continue
            section = next((s for s in chapter_data["sections"] if s["no"] == sec_no), None)
            if not section:
                continue
            practice = next((p for p in section["practices"] if p["no"] == prac_no), None)
            if not practice:
                continue
            items.append({"pid": pid, "section": section, "practice": practice})
        return items

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.header_label = QLabel()
        self.header_label.setFont(QFont("Malgun Gothic", 13, QFont.Bold))
        self._refresh_header()
        layout.addWidget(self.header_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.card_layout = QVBoxLayout(container)

        for item in self.items:
            self.card_layout.addWidget(self._build_card(item))
        self.card_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; }
            QLabel { color: #E6E6E6; }
            QScrollArea { border: none; }
        """)

    def _on_inline_code_clicked(self, url):
        text = extract_copy_text(url)
        if text is None:
            return
        QApplication.clipboard().setText(text)
        QToolTip.showText(QCursor.pos(), f"📋 복사됨: {text}")

    def _refresh_header(self):
        if self.items:
            self.header_label.setText(
                f"스스로 풀지 못했던 문제 {len(self.items)}개 — 코드를 다시 작성해서 채점해보세요. "
                "정답 처리되거나 직접 삭제하면 목록에서 사라집니다."
            )
        else:
            self.header_label.setText("🎉 복습할 문제가 없습니다! 모든 TODO 문제를 스스로 풀었어요.")

    def _build_card(self, item):
        pid = item["pid"]
        section, practice = item["section"], item["practice"]

        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame { background-color: #17212B; border: 1px solid #2D3E4E; border-left: 4px solid #4FC1FF;
                     border-radius: 4px; }
        """)
        v = QVBoxLayout(card)

        title = QLabel(f"[{section['no']}. {section['title']}] 문제 {practice['no']}")
        title.setFont(QFont("Malgun Gothic", 12, QFont.Bold))
        title.setStyleSheet("color: #4FC1FF;")
        v.addWidget(title)

        prompt = QTextBrowser()
        prompt.setMaximumHeight(90)
        prompt.setOpenLinks(False)
        prompt.anchorClicked.connect(self._on_inline_code_clicked)
        prompt_body = markdown.markdown(f"**문제 {practice['no']}.** {practice['prompt_markdown']}", extensions=['fenced_code'])
        prompt.setHtml(make_code_copyable(prompt_body))
        prompt.setStyleSheet("QTextBrowser { background-color: #17212B; color: #E0E0E0; border: none; }")
        v.addWidget(prompt)

        code_editor = QPlainTextEdit()
        code_editor.setPlainText(
            self.progress_manager.get_data()["practice_code_by_id"].get(pid, practice.get("starter_code", ""))
        )
        code_editor.setMaximumHeight(120)
        code_editor.setFont(QFont("Consolas", 14))
        code_editor.setStyleSheet("""
            QPlainTextEdit { background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #333333;
                              border-radius: 4px; padding: 6px; }
        """)
        PythonHighlighter(code_editor.document())
        v.addWidget(code_editor)

        btn_row = QHBoxLayout()
        btn_grade = QPushButton("✅ 다시 채점하기")
        btn_grade.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; }
            QPushButton:disabled { background-color: #3A3D42; color: #8A8D92; }
        """)
        btn_answer = QPushButton("정답 보기")
        btn_answer.setStyleSheet("""
            QPushButton { background-color: #B22222; color: white; padding: 6px 12px; border-radius: 4px; border: none; }
        """)
        btn_delete = QPushButton("✕ 삭제")
        btn_delete.setToolTip("이 문제를 복습 목록에서 그냥 지웁니다 (정답 처리와 무관)")
        btn_delete.setStyleSheet("""
            QPushButton { background-color: transparent; color: #8A8D92; padding: 6px 12px; border: 1px solid #3A3D42; border-radius: 4px; }
            QPushButton:hover { color: #FF8A80; border-color: #FF8A80; }
        """)
        status_label = QLabel("")
        status_label.setWordWrap(True)

        btn_row.addWidget(btn_grade)
        btn_row.addWidget(btn_answer)
        btn_row.addStretch()
        btn_row.addWidget(btn_delete)
        v.addLayout(btn_row)
        v.addWidget(status_label)

        answer_view = QTextBrowser()
        answer_view.setMaximumHeight(90)
        answer_view.setVisible(False)
        answer_view.setStyleSheet("""
            QTextBrowser { background-color: #1E1B12; color: #D4D4D4; border-left: 4px solid #C9A227; }
        """)
        escaped = html_mod.escape(practice["answer_code"])
        answer_view.setHtml(f"<pre style='font-family:Consolas; white-space:pre-wrap;'>{escaped}</pre>")
        v.addWidget(answer_view)

        btn_answer.clicked.connect(lambda: answer_view.setVisible(not answer_view.isVisible()))
        btn_grade.clicked.connect(lambda: self._grade_card(item, code_editor, status_label, btn_grade))
        btn_delete.clicked.connect(lambda: self._delete_card(item, card))

        self._cards[pid] = {"status_label": status_label, "code_editor": code_editor,
                             "card": card, "btn_grade": btn_grade}
        return card

    def _delete_card(self, item, card):
        pid = item["pid"]
        self.progress_manager.remove_from_wrong_list(pid)
        self.progress_manager.save_now()
        self.items = [i for i in self.items if i["pid"] != pid]
        self._cards.pop(pid, None)
        self.card_layout.removeWidget(card)
        card.deleteLater()
        self._refresh_header()

    def _grade_card(self, item, code_editor, status_label, btn_grade):
        pid = item["pid"]
        section, practice = item["section"], item["practice"]
        idx = _unit_idx(section["no"], practice["no"])
        code = code_editor.toPlainText()

        status_label.setText("⏳ 채점 중...")
        btn_grade.setEnabled(False)

        def _run():
            try:
                ns, out, err = self.executor.run_problem(idx, code, self.units, timeout=30.0)
                if err:
                    is_correct, detail = False, "❌ 코드 실행 중 에러가 발생했습니다."
                else:
                    is_correct, detail = self.grader.grade_problem(ns, practice)
            except Exception as e:
                is_correct, detail = False, f"❌ 실행 오류: {e}"
            self.grade_result_signal.emit(pid, is_correct, detail)

        threading.Thread(target=_run, daemon=True).start()

    @Slot(str, bool, str)
    def _on_grade_result(self, pid, is_correct, detail):
        card_info = self._cards.get(pid)
        if not card_info:
            return
        card_info["btn_grade"].setEnabled(True)
        color = "#4CAF50" if is_correct else "#FF8A80"
        card_info["status_label"].setStyleSheet(f"color: {color}; font-weight: bold;")
        card_info["status_label"].setText(detail)

        self.progress_manager.update_practice_result_only(pid, is_correct)
        if is_correct:
            self.progress_manager.remove_from_wrong_list(pid)
            card_info["card"].setStyleSheet("""
                QFrame { background-color: #17212B; border: 1px solid #2D3E4E; border-left: 4px solid #4CAF50;
                         border-radius: 4px; }
            """)
        else:
            self.progress_manager.ensure_in_wrong_list(pid)
        self.progress_manager.save_now()
