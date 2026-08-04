import threading

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QSplitter, QPlainTextEdit,
                               QTabWidget, QTextBrowser, QMessageBox)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QShortcut, QKeySequence

import markdown

from engine.code_executor import CodeExecutor
from engine.grader import Grader
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from resource_path import get_base_dir
from ui.highlighter import PythonHighlighter
from ui.study_review_dialog import StudyReviewDialog


def _unit_idx(section_no, practice_no=0):
    """섹션의 예제 코드/각 TODO 문제를 하나의 정수 인덱스로 매핑합니다.
    (CodeExecutor.run_problem이 기대하는 '누적 실행 순서' 정수 키를 그대로 재사용하기 위함 —
    섹션당 문제 99개 미만이라는 전제로 section_no*100 + practice_no)"""
    return section_no * 100 + practice_no


class StudyWindow(QMainWindow):
    plot_signal = Signal(object)
    console_signal = Signal(str)
    run_finished_signal = Signal()

    def __init__(self, chapter_data, progress_manager):
        super().__init__()
        self.chapter_data = chapter_data
        self.progress_manager = progress_manager
        self.sections = chapter_data["sections"]

        self.editor_font_size = 18

        self._is_running = False
        self._active_run_key = None  # ("example"|"practice", unit_idx)

        self.working_dir = get_base_dir()
        self.executor = CodeExecutor(chapter_data["setup_code"], working_dir=self.working_dir)
        self.executor.on_plot_callback = self._on_plot_callback
        self.executor.on_console_callback = self._on_console_callback

        self.grader = Grader()

        session_data = progress_manager.get_data()
        self.current_section_idx = 0
        for i, s in enumerate(self.sections):
            if s["no"] == session_data.get("current_section_no", 1):
                self.current_section_idx = i
                break
        self.current_practice_idx = 0

        self.setup_ui()
        self.apply_theme()
        self.update_font_sizes()
        self.load_section(self.current_section_idx)
        self._setup_shortcuts()

        self.progress_manager.start_auto_save(60.0)

        self.plot_signal.connect(self.render_plot)
        self.console_signal.connect(self.append_console)
        self.run_finished_signal.connect(self._on_run_finished)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.run_current_practice)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.run_current_practice)
        QShortcut(QKeySequence(QKeySequence.ZoomIn), self, activated=lambda: self.change_font_size(2))
        QShortcut(QKeySequence(QKeySequence.ZoomOut), self, activated=lambda: self.change_font_size(-2))
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self.change_font_size(2))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.reset_font_size)

    # ---------------------------------------------------------- UI 구성 ----

    def setup_ui(self):
        self.setWindowTitle(f"AICE Simulator - 학습 모드 - {self.chapter_data['title']}")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        header_layout = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setFont(QFont("Malgun Gothic", 14, QFont.Bold))

        self.btn_font_minus = QPushButton("A-")
        self.btn_font_minus.setFixedWidth(40)
        self.btn_font_minus.clicked.connect(lambda: self.change_font_size(-2))
        self.btn_font_plus = QPushButton("A+")
        self.btn_font_plus.setFixedWidth(40)
        self.btn_font_plus.clicked.connect(lambda: self.change_font_size(2))

        self.btn_prev_section = QPushButton("◀ 이전 섹션")
        self.btn_prev_section.clicked.connect(self.prev_section)
        self.btn_next_section = QPushButton("다음 섹션 ▶")
        self.btn_next_section.clicked.connect(lambda: self.next_section(user_triggered=True))

        self.btn_review = QPushButton("📝 복습 모드")
        self.btn_review.clicked.connect(self.open_review_mode)

        header_layout.addWidget(self.progress_label)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_font_minus)
        header_layout.addWidget(self.btn_font_plus)
        header_layout.addSpacing(20)
        header_layout.addWidget(self.btn_prev_section)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.btn_next_section)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_review)
        main_layout.addLayout(header_layout)

        self.section_nav_layout = QHBoxLayout()
        self.section_nav_buttons = {}
        for s in self.sections:
            btn = QPushButton(str(s["no"]))
            btn.setFixedSize(30, 26)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, no=s["no"]: self._jump_to_section(no))
            self.section_nav_layout.addWidget(btn)
            self.section_nav_buttons[s["no"]] = btn
        self.section_nav_layout.addStretch()
        main_layout.addLayout(self.section_nav_layout)

        h_splitter = QSplitter(Qt.Horizontal)

        # 좌측: 이론 + 개념 정리 (섹션 전체에서 공통)
        self.theory_viewer = QTextBrowser()
        h_splitter.addWidget(self.theory_viewer)

        v_splitter = QSplitter(Qt.Vertical)

        # 우측 상단: 예제 코드
        example_widget = QWidget()
        example_layout = QVBoxLayout(example_widget)
        example_layout.setContentsMargins(0, 0, 0, 0)

        example_header = QHBoxLayout()
        example_label = QLabel("💻 예제 코드 (직접 실행해서 결과를 확인해보세요)")
        example_label.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        self.btn_run_example = QPushButton("▶ 예제 실행해보기")
        self.btn_run_example.clicked.connect(self.run_current_example)
        example_header.addWidget(example_label)
        example_header.addStretch()
        example_header.addWidget(self.btn_run_example)

        self.example_editor = QPlainTextEdit()
        self.example_editor.setReadOnly(True)
        self.example_highlighter = PythonHighlighter(self.example_editor.document())
        self.example_editor.setMaximumHeight(160)

        example_layout.addLayout(example_header)
        example_layout.addWidget(self.example_editor)
        v_splitter.addWidget(example_widget)

        # 우측 중단: TODO 문제
        practice_widget = QWidget()
        practice_layout = QVBoxLayout(practice_widget)
        practice_layout.setContentsMargins(0, 0, 0, 0)

        self.practice_nav_layout = QHBoxLayout()
        self.practice_label = QLabel()
        self.practice_label.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        self.practice_nav_layout.addWidget(self.practice_label)
        self.practice_nav_layout.addStretch()
        self.btn_prev_practice = QPushButton("◀")
        self.btn_prev_practice.setFixedWidth(36)
        self.btn_prev_practice.clicked.connect(self.prev_practice)
        self.btn_next_practice = QPushButton("▶")
        self.btn_next_practice.setFixedWidth(36)
        self.btn_next_practice.clicked.connect(lambda: self.next_practice(user_triggered=True))
        self.practice_nav_layout.addWidget(self.btn_prev_practice)
        self.practice_nav_layout.addWidget(self.btn_next_practice)

        self.practice_prompt_viewer = QTextBrowser()
        self.practice_prompt_viewer.setMaximumHeight(110)

        btn_layout = QHBoxLayout()
        self.btn_grade = QPushButton("✅ 채점하기")
        self.btn_grade.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px; border: none; }
            QPushButton:hover { background-color: #5CBF60; }
            QPushButton:disabled { background-color: #3A3D42; color: #8A8D92; }
        """)
        self.btn_grade.clicked.connect(self.run_current_practice)

        self.btn_answer = QPushButton("정답 보기")
        self.btn_answer.setStyleSheet("""
            QPushButton { background-color: #B22222; color: white; padding: 7px 14px; border-radius: 5px; border: none; }
            QPushButton:hover { background-color: #C93838; }
        """)
        self.btn_answer.clicked.connect(self.show_answer)

        btn_layout.addWidget(self.btn_grade)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_answer)

        self.reveal_banner = QLabel()
        self.reveal_banner.setWordWrap(True)
        self.reveal_banner.setVisible(False)

        self.code_editor = QPlainTextEdit()
        self.highlighter = PythonHighlighter(self.code_editor.document())
        self.code_editor.textChanged.connect(self.on_code_typed)

        practice_layout.addLayout(self.practice_nav_layout)
        practice_layout.addWidget(self.practice_prompt_viewer)
        practice_layout.addLayout(btn_layout)
        practice_layout.addWidget(self.reveal_banner)
        practice_layout.addWidget(self.code_editor)
        v_splitter.addWidget(practice_widget)

        # 우측 하단: 콘솔/시각화/정답 탭 (예제 실행과 TODO 채점이 공유)
        self.tabs = QTabWidget()
        self.console_output = QTextBrowser()
        self.console_output.setFont(QFont("Consolas", 14))

        self.plot_container = QVBoxLayout()
        plot_widget = QWidget()
        plot_widget.setLayout(self.plot_container)

        self.answer_output = QTextBrowser()
        self.answer_output.setFont(QFont("Consolas", 14))

        self.tabs.addTab(self.console_output, "콘솔 출력")
        self.tabs.addTab(plot_widget, "시각화 출력")
        self.tabs.addTab(self.answer_output, "정답 보기")
        self.tabs.setFont(QFont("Malgun Gothic", 12))
        v_splitter.addWidget(self.tabs)

        v_splitter.setSizes([160, 260, 260])

        h_splitter.addWidget(v_splitter)
        h_splitter.setSizes([480, 720])
        main_layout.addWidget(h_splitter)

    def apply_theme(self):
        self.code_editor.setStyleSheet("""
        QPlainTextEdit {
            background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #333333;
            border-left: 4px solid #007ACC; border-radius: 4px; padding: 8px;
            selection-background-color: #264F78;
        }
        """)
        self.code_editor.setPlaceholderText("# 여기에 코드를 작성하세요")

        self.example_editor.setStyleSheet("""
        QPlainTextEdit {
            background-color: #1B1A17; color: #D4D4D4; border: 1px solid #3A362F;
            border-left: 4px solid #C9A227; border-radius: 4px; padding: 8px;
        }
        """)

        self.reveal_banner.setStyleSheet("""
            QLabel { background-color: #3D1F1F; color: #FF8A80; font-weight: bold;
                     padding: 6px 10px; border: 1px solid #B22222; border-radius: 4px; margin-top: 6px; }
        """)

        self.console_output.setStyleSheet("""
        QTextBrowser {
            background-color: #1B1A17; color: #D4D4D4; border: 1px solid #3A362F;
            border-left: 4px solid #6A9955; border-radius: 4px; padding: 8px;
            selection-background-color: #264F78;
        }
        """)
        self._reset_console_placeholder()

        self.answer_output.setStyleSheet("""
        QTextBrowser {
            background-color: #1E1B12; color: #D4D4D4; border: 1px solid #4A3F1F;
            border-left: 4px solid #C9A227; border-radius: 4px; padding: 8px;
            selection-background-color: #264F78;
        }
        """)
        self._reset_answer_placeholder()

        self.theory_viewer.setStyleSheet("""
        QTextBrowser {
            background-color: #17212B; color: #E6E6E6; border: 1px solid #2D3E4E;
            border-left: 4px solid #4FC1FF; border-radius: 4px; padding: 15px;
        }
        """)

        self.practice_prompt_viewer.setStyleSheet("""
        QTextBrowser {
            background-color: #17212B; color: #E6E6E6; border: 1px solid #2D3E4E;
            border-left: 4px solid #4FC1FF; border-radius: 4px; padding: 10px;
        }
        """)

        toolbar_btn_style = """
        QPushButton {
            background-color: #333844; color: #E6E6E6; border: 1px solid #454C5C;
            border-radius: 5px; padding: 6px 12px;
        }
        QPushButton:hover { background-color: #414957; }
        QPushButton:pressed { background-color: #2B303A; }
        """
        for btn in (self.btn_font_minus, self.btn_font_plus, self.btn_prev_section, self.btn_next_section,
                    self.btn_review, self.btn_prev_practice, self.btn_next_practice, self.btn_run_example):
            btn.setStyleSheet(toolbar_btn_style)

    def _reset_console_placeholder(self):
        self.console_output.setHtml(
            "<i style='color:#6B6B6B;'>▶ 예제를 실행하거나 '채점하기'를 누르면 결과가 여기에 표시됩니다.</i>"
        )

    def _reset_answer_placeholder(self):
        self.answer_output.setHtml(
            "<i style='color:#6B6B6B;'>'정답 보기'를 누르면 이 탭에 정답 코드가 표시됩니다.</i>"
        )

    # ------------------------------------------------------ 렌더링 헬퍼 ----

    def change_font_size(self, delta):
        new_size = self.editor_font_size + delta
        if 10 <= new_size <= 36:
            self.editor_font_size = new_size
            self.update_font_sizes()
            self._refresh_theory_html()
            self._refresh_practice_html()

    def reset_font_size(self):
        self.editor_font_size = 18
        self.update_font_sizes()
        self._refresh_theory_html()
        self._refresh_practice_html()

    def update_font_sizes(self):
        font = QFont("Consolas", self.editor_font_size)
        self.code_editor.setFont(font)
        self.example_editor.setFont(font)

    def _theory_css(self):
        base = self.editor_font_size + 4
        h2_size = base + 8
        return f"""
        <style>
            p, li, b, strong, td, th {{ font-family: 'Malgun Gothic', sans-serif; font-size: {base}px; line-height: 1.6; color: #E0E0E0; }}
            h2, h3 {{ color: #4FC1FF; margin-top: 4px; font-size: {h2_size}px; }}
            code {{ background-color: #1E1E1E; padding: 2px 6px; border-radius: 4px; font-family: Consolas; color: #CE9178; font-size: {base}px; }}
            table {{ border-collapse: collapse; margin: 10px 0; }}
            td, th {{ border: 1px solid #2D3E4E; padding: 6px 10px; }}
        </style>
        """

    def _refresh_theory_html(self):
        s = self.sections[self.current_section_idx]
        md_text = f"## {s['no']}. {s['title']}\n\n{s['theory_markdown']}\n\n{s['concept_table_markdown']}"
        html = self._theory_css() + f"<div>{markdown.markdown(md_text, extensions=['tables'])}</div>"
        self.theory_viewer.setHtml(html)

    def _refresh_practice_html(self):
        s = self.sections[self.current_section_idx]
        p = s["practices"][self.current_practice_idx]
        md_text = f"**문제 {p['no']}.** {p['prompt_markdown']}"
        html = self._theory_css() + f"<div>{markdown.markdown(md_text)}</div>"
        self.practice_prompt_viewer.setHtml(html)

    def _render_answer_tab(self, answer_code):
        import html as html_mod
        escaped = html_mod.escape(answer_code)
        self.answer_output.setHtml(
            "<div style='font-family:Consolas; font-size:14px; color:#D4D4D4;'>"
            "<p style='color:#C9A227; font-weight:bold; margin-bottom:10px;'>✅ 정답 코드 (참고용 — 내 코드와 비교해보세요)</p>"
            f"<pre style='white-space:pre-wrap; margin:0;'>{escaped}</pre></div>"
        )

    # -------------------------------------------------------- 이동/로딩 ----

    def load_section(self, idx, practice_idx=0):
        if idx < 0 or idx >= len(self.sections):
            return
        self.current_section_idx = idx
        self.current_practice_idx = 0
        s = self.sections[idx]

        self.progress_manager.update_state(current_section_no=s["no"])
        self.progress_label.setText(f"섹션 {s['no']} / {len(self.sections)} · {s['title']}")

        self._refresh_theory_html()

        has_example = bool(s["example_code"].strip())
        self.example_editor.setPlainText(s["example_code"] if has_example else "(이 섹션에는 별도 예제 코드가 없습니다 — 왼쪽 이론을 참고하세요)")
        self.btn_run_example.setEnabled(has_example)

        self.clear_plot()
        self._reset_console_placeholder()
        self._reset_answer_placeholder()
        self.tabs.setCurrentIndex(0)

        self.btn_prev_section.setEnabled(idx > 0)
        self.btn_next_section.setEnabled(idx < len(self.sections) - 1)
        self._refresh_section_nav()

        if not s["practices"]:
            self._load_empty_practice_state()
            return
        self.load_practice(min(practice_idx, len(s["practices"]) - 1))

    def _load_empty_practice_state(self):
        self.practice_label.setText("이 섹션에는 TODO 실습문제가 없습니다 (이론 위주 섹션)")
        self.practice_prompt_viewer.setHtml(
            "<i style='color:#6B6B6B;'>이 섹션은 개념 설명 위주라 별도 실습문제가 없습니다. "
            "왼쪽 이론을 확인한 뒤 '다음 섹션'으로 넘어가세요.</i>"
        )
        self.code_editor.blockSignals(True)
        self.code_editor.clear()
        self.code_editor.blockSignals(False)
        self.code_editor.setEnabled(False)
        self.btn_grade.setEnabled(False)
        self.btn_answer.setEnabled(False)
        self.reveal_banner.setVisible(False)
        self.btn_prev_practice.setEnabled(False)
        self.btn_next_practice.setEnabled(True)

    def load_practice(self, idx):
        s = self.sections[self.current_section_idx]
        if idx < 0 or idx >= len(s["practices"]):
            return
        self.code_editor.setEnabled(True)
        self.btn_grade.setEnabled(True)
        self.btn_answer.setEnabled(True)
        self.current_practice_idx = idx
        p = s["practices"][idx]
        pid = self._practice_id(s, p)

        self.progress_label.setText(f"섹션 {s['no']} / {len(self.sections)} · {s['title']}")
        self.practice_label.setText(f"✍️ TODO 문제 {idx + 1} / {len(s['practices'])}")

        self._refresh_practice_html()

        session_data = self.progress_manager.get_data()
        # 노트북의 "빈 TODO 셀"에 toy 데이터/답안 변수 초기화 등 실제 시작 코드가 들어있던 문제는
        # 처음 열었을 때 그 내용을 코드 에디터 초기값으로 보여줍니다 (저장된 코드가 있으면 그게 우선).
        saved_code = session_data["practice_code_by_id"].get(pid, p.get("starter_code", ""))
        self.code_editor.blockSignals(True)
        self.code_editor.setPlainText(saved_code)
        self.code_editor.blockSignals(False)

        self.clear_plot()
        self._reset_console_placeholder()
        self._reset_answer_placeholder()

        revealed = self.progress_manager.is_revealed(pid)
        self.reveal_banner.setVisible(revealed)
        border_color = "#B22222" if revealed else "#007ACC"
        self.code_editor.setStyleSheet(f"""
        QPlainTextEdit {{
            background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #333333;
            border-left: 4px solid {border_color}; border-radius: 4px; padding: 8px;
            selection-background-color: #264F78;
        }}
        """)
        if revealed:
            self.reveal_banner.setText("🔒 정답을 확인한 문제입니다 — 이 문제는 복습 리스트에 남습니다. 자유롭게 연습해보세요.")
            self._render_answer_tab(p["answer_code"])

        self.btn_prev_practice.setEnabled(idx > 0)
        self.btn_next_practice.setEnabled(True)  # 마지막 문제에서는 다음 섹션으로 이동
        self._refresh_practice_nav_label()

    def _practice_id(self, section, practice):
        return f"{section['no']}-{practice['no']}"

    def _refresh_practice_nav_label(self):
        s = self.sections[self.current_section_idx]
        results = self.progress_manager.get_data()["practice_results_by_id"]
        done = sum(1 for p in s["practices"] if results.get(self._practice_id(s, p), {}).get("is_correct"))
        self.practice_label.setText(f"✍️ TODO 문제 {self.current_practice_idx + 1} / {len(s['practices'])}  (섹션 내 정답 {done}개)")

    def _refresh_section_nav(self):
        session_data = self.progress_manager.get_data()
        completed = set(session_data.get("completed_sections", []))
        for s in self.sections:
            btn = self.section_nav_buttons[s["no"]]
            is_current = (s["no"] == self.sections[self.current_section_idx]["no"])
            if s["no"] in completed:
                color = "#4CAF50"
            else:
                color = "#454C5C"
            border = "2px solid #FFFFFF" if is_current else "1px solid #2D3E4E"
            btn.setChecked(is_current)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {color}; color: white; font-weight: bold;
                                border: {border}; border-radius: 4px; }}
            """)

    def _jump_to_section(self, section_no):
        for i, s in enumerate(self.sections):
            if s["no"] == section_no:
                self.load_section(i)
                return

    def prev_section(self):
        self.load_section(self.current_section_idx - 1)

    def next_section(self, user_triggered=False):
        self.progress_manager.mark_section_completed(self.sections[self.current_section_idx]["no"])
        if self.current_section_idx + 1 < len(self.sections):
            self.load_section(self.current_section_idx + 1)
        elif user_triggered:
            self._finish_chapter()

    def prev_practice(self):
        self.load_practice(self.current_practice_idx - 1)

    def next_practice(self, user_triggered=False):
        s = self.sections[self.current_section_idx]
        if self.current_practice_idx + 1 < len(s["practices"]):
            self.load_practice(self.current_practice_idx + 1)
        else:
            self.next_section(user_triggered=user_triggered)

    def _finish_chapter(self):
        self.progress_manager.mark_chapter_completed()
        self.progress_manager.save_now()
        wrong = self.progress_manager.get_data().get("wrong_practice_ids", [])
        if wrong:
            QMessageBox.information(self, "챕터 완료",
                                     f"🎉 챕터를 끝까지 진행했습니다!\n스스로 풀지 못했던 문제 {len(wrong)}개를 복습 모드에서 다시 풀어보세요.")
            self.open_review_mode()
        else:
            QMessageBox.information(self, "챕터 완료", "🎉 모든 TODO 문제를 스스로 풀었습니다! 챕터를 완료했습니다.")

    def open_review_mode(self):
        session_data = self.progress_manager.get_data()
        wrong_ids = session_data.get("wrong_practice_ids", [])
        dialog = StudyReviewDialog(self.chapter_data, wrong_ids, self.grader,
                                    self.executor, self._build_units_dict(), self.progress_manager, parent=self)
        dialog.exec()
        self._refresh_section_nav()

    # -------------------------------------------------------------- 실행 ----

    def _build_units_dict(self):
        """CodeExecutor가 기대하는 '누적 실행 코드 블록' 딕셔너리.
        섹션별 예제 코드(항상 존재) + 지금까지 저장된 TODO 코드(있는 것만)를 정수 인덱스로 묶습니다."""
        session_data = self.progress_manager.get_data()
        saved = session_data["practice_code_by_id"]
        units = {}
        for s in self.sections:
            units[str(_unit_idx(s["no"], 0))] = s["example_code"]
            for p in s["practices"]:
                pid = self._practice_id(s, p)
                if pid in saved:
                    units[str(_unit_idx(s["no"], p["no"]))] = saved[pid]
        return units

    def on_code_typed(self):
        s = self.sections[self.current_section_idx]
        p = s["practices"][self.current_practice_idx]
        pid = self._practice_id(s, p)
        self.progress_manager.on_code_changed(pid, self.code_editor.toPlainText())

    def _on_plot_callback(self, fig):
        self.plot_signal.emit(fig)

    def _on_console_callback(self, text):
        self.console_signal.emit(text)

    def _is_stale_run_update(self, key):
        return self._active_run_key is not None and self._active_run_key != key

    @Slot(object)
    def render_plot(self, fig):
        self.clear_plot()
        canvas = FigureCanvasQTAgg(fig)
        self.plot_container.addWidget(canvas)
        self.tabs.setCurrentIndex(1)

    @Slot(str)
    def append_console(self, text):
        self.console_output.append(text)

    @Slot()
    def _on_run_finished(self):
        self._is_running = False
        self._active_run_key = None
        self.btn_run_example.setEnabled(True)
        self.btn_grade.setEnabled(True)
        self._refresh_practice_nav_label()
        self._refresh_section_nav()

    def clear_plot(self):
        for i in reversed(range(self.plot_container.count())):
            widget_to_remove = self.plot_container.itemAt(i).widget()
            self.plot_container.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

    def run_current_example(self):
        if self._is_running:
            return
        s = self.sections[self.current_section_idx]
        idx = _unit_idx(s["no"], 0)

        self.console_output.clear()
        self.clear_plot()
        self.console_output.append("실행 중...")
        self.tabs.setCurrentIndex(0)

        self._is_running = True
        self._active_run_key = ("example", idx)
        self.btn_run_example.setEnabled(False)
        self.btn_grade.setEnabled(False)

        units = self._build_units_dict()

        def _run():
            try:
                ns, out, err = self.executor.run_problem(idx, s["example_code"], units, timeout=30.0)
                if err:
                    self.console_signal.emit("\n[예제 실행 중 에러가 발생했습니다. 위 내용을 확인하세요]")
            finally:
                self.run_finished_signal.emit()

        threading.Thread(target=_run, daemon=True).start()

    def run_current_practice(self):
        if self._is_running:
            return
        s = self.sections[self.current_section_idx]
        p = s["practices"][self.current_practice_idx]
        pid = self._practice_id(s, p)
        idx = _unit_idx(s["no"], p["no"])
        code = self.code_editor.toPlainText()

        self.console_output.clear()
        self.clear_plot()
        self.console_output.append("실행 중...")
        self.tabs.setCurrentIndex(0)

        self._is_running = True
        self._active_run_key = ("practice", idx)
        self.btn_run_example.setEnabled(False)
        self.btn_grade.setEnabled(False)

        units = self._build_units_dict()
        revealed = self.progress_manager.is_revealed(pid)

        def _run():
            try:
                ns, out, err = self.executor.run_problem(idx, code, units, timeout=30.0)
                if err:
                    is_correct = False
                    detail = "❌ 코드 실행 중 에러가 발생했습니다. (콘솔 확인)"
                else:
                    is_correct, detail = self.grader.grade_problem(ns, p)

                self.console_signal.emit(f"\n[채점 결과] {detail}")
                self.progress_manager.record_result(pid, is_correct, revealed_answer=revealed)
                self.progress_manager.save_now()
            finally:
                self.run_finished_signal.emit()

        threading.Thread(target=_run, daemon=True).start()

    def show_answer(self):
        s = self.sections[self.current_section_idx]
        p = s["practices"][self.current_practice_idx]
        pid = self._practice_id(s, p)
        reply = QMessageBox.question(self, "정답 보기",
                                      "정답을 보면 이 문제는 '스스로 풀지 못한 문제'로 복습 리스트에 남습니다. 계속하시겠습니까?",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.progress_manager.mark_revealed(pid)
            self.progress_manager.record_result(pid, is_correct=False, revealed_answer=True)
            self.progress_manager.save_now()
            self.reveal_banner.setVisible(True)
            self.reveal_banner.setText("🔒 정답을 확인한 문제입니다 — 이 문제는 복습 리스트에 남습니다. 자유롭게 연습해보세요.")
            self._render_answer_tab(p["answer_code"])
            self.tabs.setCurrentIndex(2)
            border_color = "#B22222"
            self.code_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #333333;
                border-left: 4px solid {border_color}; border-radius: 4px; padding: 8px;
                selection-background-color: #264F78;
            }}
            """)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "종료 확인",
            "학습 진행 상황은 저장되어 있어 다음에 실행하면 이어서 볼 수 있습니다.\n종료하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.progress_manager.stop_all()
            self.progress_manager.save_now()
            event.accept()
        else:
            event.ignore()
