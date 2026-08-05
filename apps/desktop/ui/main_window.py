import sys
import os
import threading
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QSplitter, QPlainTextEdit,
                               QTabWidget, QTextBrowser, QMessageBox, QApplication)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QShortcut, QKeySequence

import markdown

from engine.code_executor import CodeExecutor
from engine.grader import Grader
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from resource_path import get_base_dir
from ui import theme
from ui.review_note_dialog import ReviewNoteDialog
from ui.highlighter import PythonHighlighter
from ui.markdown_utils import make_code_copyable, extract_copy_text


class MainWindow(QMainWindow):
    plot_signal = Signal(object)
    console_signal = Signal(str)
    run_finished_signal = Signal()

    def __init__(self, exam_data, session_manager):
        super().__init__()
        self.exam_data = exam_data
        self.session_manager = session_manager

        self.editor_font_size = 18 # Code editor dynamic font size

        # 동시에 하나의 실행만 허용하기 위한 상태. matplotlib은 process-global 상태(plt.show
        # 몽키패치, 현재 figure 등)를 쓰기 때문에, 두 실행이 겹치면 서로의 그래프 캡처를 깨뜨릴
        # 수 있습니다. _active_run_no는 "지금 백그라운드에서 실행 중인 코드가 어느 문제 것인지"를
        # 기억해뒀다가, 콘솔/그래프 갱신 시점에 사용자가 이미 다른 문제로 넘어갔다면(그 사이 화면이
        # 바뀌었다면) 엉뚱한 문제 화면에 이전 실행 결과가 표시되지 않도록 걸러내는 데 씁니다.
        self._is_running = False
        self._active_run_no = None
        
        self.working_dir = get_base_dir()
        self.executor = CodeExecutor(exam_data['setup_code'], working_dir=self.working_dir)
        
        self.executor.on_plot_callback = self._on_plot_callback
        self.executor.on_console_callback = self._on_console_callback
        
        self.grader = Grader()
        
        self.current_idx = 0
        self.problems = exam_data["problems"]
        
        session_data = session_manager.get_data()
        self.time_limit = session_data["time_limit_minutes"] * 60
        self.elapsed = session_data["elapsed_seconds"]
        
        curr_no = session_data["current_problem_no"]
        for i, p in enumerate(self.problems):
            if p["no"] == curr_no:
                self.current_idx = i
                break
                
        self.setup_ui()
        self.apply_theme()
        self.update_font_sizes()
        self.load_problem(self.current_idx)
        self._setup_shortcuts()
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.tick_timer)
        self.clock_timer.start(1000)
        
        self.session_manager.start_auto_save(60.0)
        
        self.plot_signal.connect(self.render_plot)
        self.console_signal.connect(self.append_console)
        self.run_finished_signal.connect(self._on_run_finished)

    def _setup_shortcuts(self):
        # Jupyter에 익숙한 응시자를 위한 Ctrl+Enter 실행 단축키 (일반 Enter/Numpad Enter 둘 다 지원)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.run_current_code)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.run_current_code)
        # Alt+Left/Right: 코드 에디터의 표준 '단어 단위 이동'(Ctrl+Left/Right)과 겹치지 않도록
        # 브라우저 뒤로/앞으로 가기와 같은 조합을 사용
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.prev_problem)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self.next_problem)
        # VSCode 스타일 글꼴 확대/축소
        QShortcut(QKeySequence(QKeySequence.ZoomIn), self, activated=lambda: self.change_font_size(2))
        QShortcut(QKeySequence(QKeySequence.ZoomOut), self, activated=lambda: self.change_font_size(-2))
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self.change_font_size(2))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.reset_font_size)

    def setup_ui(self):
        self.setWindowTitle(f"AICE Simulator - {self.exam_data['title']}")
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        header_layout = QHBoxLayout()
        self.progress_label = QLabel()
        prog_font = QFont("Malgun Gothic", 14, QFont.Bold)
        self.progress_label.setFont(prog_font)
        
        self.timer_label = QLabel()
        self.timer_label.setFont(QFont("Consolas", 16, QFont.Bold))

        # Font size buttons
        self.btn_font_minus = QPushButton("A-")
        self.btn_font_minus.setToolTip("글꼴 크기 줄이기")
        self.btn_font_minus.clicked.connect(lambda: self.change_font_size(-2))
        self.btn_font_minus.setFixedWidth(40)

        self.btn_font_plus = QPushButton("A+")
        self.btn_font_plus.setToolTip("글꼴 크기 키우기")
        self.btn_font_plus.clicked.connect(lambda: self.change_font_size(2))
        self.btn_font_plus.setFixedWidth(40)

        self.btn_prev = QPushButton("◀ 이전 문제")
        self.btn_prev.clicked.connect(self.prev_problem)
        self.btn_next = QPushButton("다음 문제 ▶")
        self.btn_next.clicked.connect(self.next_problem)

        self.btn_reset = QPushButton("↺ 처음부터 다시 풀기")
        self.btn_reset.clicked.connect(self.reset_exam)

        self.btn_theme_toggle = QPushButton()
        self.btn_theme_toggle.setFixedWidth(40)
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        self._refresh_theme_toggle_label()

        self.btn_submit = QPushButton("최종 제출 (채점하기)")
        self.btn_submit.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 7px 16px; border-radius: 5px; border: none; }
            QPushButton:hover { background-color: #5CBF60; }
            QPushButton:pressed { background-color: #3E9142; }
            QPushButton:disabled { background-color: #3A3D42; color: #8A8D92; }
        """)
        self.btn_submit.clicked.connect(self.submit_exam)

        header_layout.addWidget(self.progress_label)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_font_minus)
        header_layout.addWidget(self.btn_font_plus)
        header_layout.addSpacing(20)
        header_layout.addWidget(self.btn_prev)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.btn_next)
        header_layout.addStretch()
        header_layout.addWidget(self.timer_label)
        header_layout.addSpacing(12)
        header_layout.addWidget(self.btn_theme_toggle)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.btn_reset)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.btn_submit)

        main_layout.addLayout(header_layout)

        self.nav_layout = QHBoxLayout()
        self.nav_buttons = {}
        for p in self.problems:
            btn = QPushButton(str(p["no"]))
            btn.setFixedSize(34, 28)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, no=p["no"]: self._jump_to_problem(no))
            self.nav_layout.addWidget(btn)
            self.nav_buttons[p["no"]] = btn
        self.nav_layout.addStretch()
        main_layout.addLayout(self.nav_layout)

        h_splitter = QSplitter(Qt.Horizontal)
        
        self.md_viewer = QTextBrowser()
        self.md_viewer.setOpenLinks(False)
        self.md_viewer.anchorClicked.connect(self._on_inline_code_clicked)
        h_splitter.addWidget(self.md_viewer)
        
        v_splitter = QSplitter(Qt.Vertical)
        
        code_widget = QWidget()
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_run = QPushButton("▶ 현재 문제 실행")
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: #007ACC; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px; border: none; }
            QPushButton:hover { background-color: #1B8FE0; }
            QPushButton:pressed { background-color: #005A9E; }
            QPushButton:disabled { background-color: #3A3D42; color: #8A8D92; }
        """)
        self.btn_run.clicked.connect(self.run_current_code)

        self.btn_answer = QPushButton("정답 보기 (0점 처리)")
        self.btn_answer.setStyleSheet("""
            QPushButton { background-color: #B22222; color: white; padding: 7px 14px; border-radius: 5px; border: none; }
            QPushButton:hover { background-color: #C93838; }
            QPushButton:pressed { background-color: #8E1B1B; }
            QPushButton:disabled { background-color: #3A3D42; color: #8A8D92; }
        """)
        self.btn_answer.clicked.connect(self.show_answer)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_run)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_answer)

        self.lock_banner = QLabel()
        self.lock_banner.setWordWrap(True)
        self.lock_banner.setVisible(False)

        self.code_editor = QPlainTextEdit()
        self.highlighter = PythonHighlighter(self.code_editor.document())
        self.code_editor.textChanged.connect(self.on_code_typed)

        code_layout.addLayout(btn_layout)
        code_layout.addWidget(self.lock_banner)
        code_layout.addWidget(self.code_editor)
        
        v_splitter.addWidget(code_widget)
        
        self.tabs = QTabWidget()
        self.console_output = QTextBrowser()
        self.console_output.setFont(QFont("Consolas", 15))
        
        self.plot_container = QVBoxLayout()
        plot_widget = QWidget()
        plot_widget.setLayout(self.plot_container)
        
        self.answer_output = QTextBrowser()
        self.answer_output.setFont(QFont("Consolas", 15))

        self.tabs.addTab(self.console_output, "콘솔 출력")
        self.tabs.addTab(plot_widget, "시각화 출력")
        self.tabs.addTab(self.answer_output, "정답 보기")

        # 탭 글씨 크기 고정
        self.tabs.setFont(QFont("Malgun Gothic", 12))
        
        v_splitter.addWidget(self.tabs)
        
        h_splitter.addWidget(v_splitter)
        h_splitter.setSizes([500, 700])
        
        main_layout.addWidget(h_splitter)

    def apply_theme(self):
        t = theme.tokens()
        self.setStyleSheet(f"QMainWindow {{ background-color: {t['window_bg']}; }}")

        # 세 영역(문제/코드/콘솔)을 색상 hue 자체가 다르게 줘서 곁눈질로도 구분되게 함.
        # 코드 에디터: 익숙한 VSCode 다크 + 파란색 강조선("여기에 입력")
        self._style_code_editor(revealed=False)
        self.code_editor.setPlaceholderText("# 여기에 코드를 작성하세요")

        self.lock_banner.setStyleSheet(f"""
            QLabel {{
                background-color: {t['reveal_bg']};
                color: {t['reveal_text']};
                font-weight: bold;
                padding: 6px 10px;
                border: 1px solid {t['reveal_border']};
                border-radius: 4px;
                margin-top: 6px;
            }}
        """)

        # 콘솔 출력: 따뜻한 톤 다크 + 초록색 강조선("결과 확인")
        self.console_output.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['console_bg']};
            color: {t['editor_text']};
            border: 1px solid {t['console_border']};
            border-left: 4px solid {t['accent_green']};
            border-radius: 4px;
            padding: 8px;
            selection-background-color: {t['selection_bg']};
        }}
        """)
        self._reset_console_placeholder()

        # 정답 보기 탭: 콘솔과 같은 다크톤 + 골드 강조선("정답" 배지 색과 통일)
        self.answer_output.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['answer_bg']};
            color: {t['editor_text']};
            border: 1px solid {t['answer_border']};
            border-left: 4px solid {t['accent_gold']};
            border-radius: 4px;
            padding: 8px;
            selection-background-color: {t['selection_bg']};
        }}
        """)
        self._reset_answer_placeholder()

        # 문제 지문: 남색 계열 + 하늘색 강조선("읽는 곳")
        self.md_viewer.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['panel_bg']};
            color: {t['panel_text']};
            border: 1px solid {t['panel_border']};
            border-left: 4px solid {t['accent_blue']};
            border-radius: 4px;
            padding: 15px;
        }}
        """)

        # 상단 툴바 버튼들을 한 톤으로 통일 (기본 OS 버튼 느낌 제거)
        toolbar_btn_style = f"""
        QPushButton {{
            background-color: {t['btn_bg']};
            color: {t['btn_text']};
            border: 1px solid {t['btn_border']};
            border-radius: 5px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{ background-color: {t['btn_hover']}; }}
        QPushButton:pressed {{ background-color: {t['btn_pressed']}; }}
        """
        for btn in (self.btn_font_minus, self.btn_font_plus, self.btn_prev, self.btn_next, self.btn_reset,
                    self.btn_theme_toggle):
            btn.setStyleSheet(toolbar_btn_style)

        self.timer_label.setStyleSheet(f"color: {t['panel_text']};")

        if getattr(self, "problems", None):
            self.md_viewer.setHtml(self._build_problem_html(self.problems[self.current_idx]))

    def _style_code_editor(self, revealed):
        t = theme.tokens()
        border_color = t['reveal_border'] if revealed else t['accent_blue_editor']
        self.code_editor.setStyleSheet(f"""
        QPlainTextEdit {{
            background-color: {t['editor_bg']};
            color: {t['editor_text']};
            border: 1px solid {t['editor_border']};
            border-left: 4px solid {border_color};
            border-radius: 4px;
            padding: 8px;
            selection-background-color: {t['selection_bg']};
        }}
        """)

    def _refresh_theme_toggle_label(self):
        self.btn_theme_toggle.setText("☀️" if theme.get_mode() == "dark" else "🌙")
        self.btn_theme_toggle.setToolTip("라이트 모드로 전환" if theme.get_mode() == "dark" else "다크 모드로 전환")

    def toggle_theme(self):
        theme.toggle_mode()
        self._refresh_theme_toggle_label()
        self.apply_theme()
        if getattr(self, "problems", None):
            self._apply_lock_state(self.problems[self.current_idx])
            self._refresh_problem_nav()

    def _reset_console_placeholder(self):
        self.console_output.setHtml(
            f"<i style='color:{theme.tokens()['muted_text']};'>▶ '현재 문제 실행'을 누르면 출력/에러/채점 결과가 여기에 표시됩니다.</i>"
        )

    def _reset_answer_placeholder(self):
        self.answer_output.setHtml(
            f"<i style='color:{theme.tokens()['muted_text']};'>'정답 보기'를 누르면 이 탭에 정답 코드가 표시됩니다. "
            "(코드 에디터에 작성 중인 내 코드는 지워지지 않습니다)</i>"
        )

    def _is_revealed(self, p):
        graded = self.session_manager.get_data()["graded_results"]
        entry = graded.get(str(p["no"]))
        return bool(entry and entry.get("note") == "정답 보기 사용")

    def _apply_lock_state(self, p):
        # 정답을 본 문제는 채점 결과만 0점으로 영구 고정하고, 코드 에디터는 계속 편집/실행할 수
        # 있게 둡니다(연습 목적). 읽기전용으로 완전히 막으면 "정답과 비교하며 직접 타이핑해보기"가
        # 불가능해지는 반면, 실행을 허용해도 run_current_code()가 revealed 문제는 항상 0점으로
        # 기록하므로 "정답 보기 = 0점 확정" 원칙은 그대로 지켜집니다.
        locked = self._is_revealed(p)
        self.btn_answer.setEnabled(not locked)
        self.lock_banner.setVisible(locked)
        self._style_code_editor(revealed=locked)
        if locked:
            self.lock_banner.setText("🔒 정답 확인 완료 — 연습은 자유롭게 하실 수 있지만, 이 문제는 항상 0점으로 처리됩니다.")
            self._render_answer_tab(p["answer_code"])

    def _render_answer_tab(self, answer_code):
        import html as html_mod
        t = theme.tokens()
        escaped = html_mod.escape(answer_code)
        self.answer_output.setHtml(
            f"<div style='font-family:Consolas; font-size:15px; color:{t['editor_text']};'>"
            f"<p style='color:{t['accent_gold']}; font-weight:bold; margin-bottom:10px;'>"
            "✅ 정답 코드 (참고용 — 내 코드와 비교해보세요)</p>"
            f"<pre style='white-space:pre-wrap; margin:0;'>{escaped}</pre>"
            "</div>"
        )

    def change_font_size(self, delta):
        new_size = self.editor_font_size + delta
        if 10 <= new_size <= 36:
            self.editor_font_size = new_size
            self._refresh_font_sizes()

    def reset_font_size(self):
        self.editor_font_size = 18
        self._refresh_font_sizes()

    def _refresh_font_sizes(self):
        self.update_font_sizes()
        p = self.problems[self.current_idx]
        self.md_viewer.setHtml(self._build_problem_html(p))

    def update_font_sizes(self):
        font = QFont("Consolas", self.editor_font_size)
        self.code_editor.setFont(font)

    def _build_problem_html(self, p):
        # 코드 에디터 글꼴 크기(A+/A-)에 맞춰 문제 지문 크기도 같이 커지고 작아지도록 동기화
        t = theme.tokens()
        base = self.editor_font_size + 6
        h2_size = base + 6
        badge_size = self.editor_font_size
        css = f"""
        <style>
            p, li, b, strong {{
                font-family: 'Malgun Gothic', sans-serif;
                font-size: {base}px;
                line-height: 1.6;
                color: {t['panel_text']};
            }}
            h2 {{ color: {t['accent_blue']}; margin-top: 0; font-size: {h2_size}px; }}
            code {{
                background-color: {t['code_inline_bg']};
                padding: 2px 6px;
                border-radius: 4px;
                font-family: Consolas;
                color: {t['code_inline_text']};
                font-size: {base}px;
            }}
            .points-badge {{
                display: inline-block;
                background-color: {t['accent_gold']};
                color: #1A1A1A;
                font-weight: bold;
                padding: 3px 12px;
                border-radius: 12px;
                font-size: {badge_size}px;
            }}
        </style>
        """
        md_text = f"## 문제 {p['no']}\n\n<span class='points-badge'>배점 {p['points']}점</span>\n\n{p['prompt_markdown']}"
        body = make_code_copyable(markdown.markdown(md_text, extensions=['fenced_code']))
        return css + f"<div style='font-size: {base}px; font-family: Malgun Gothic; color: {t['panel_text']};'>" + body + "</div>"

    def _on_inline_code_clicked(self, url):
        text = extract_copy_text(url)
        if text is None:
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"📋 복사됨: {text}", 1500)

    def tick_timer(self):
        self.elapsed += 1
        rem = self.time_limit - self.elapsed
        if rem <= 0:
            self.clock_timer.stop()
            self.timer_label.setText("00:00 - 시간 종료!")
            # 시간초과로 자동 제출되기 전에 최종 경과시간을 반드시 저장해야 합니다. 저장하지 않으면
            # elapsed_seconds가 time_limit 미만에 머물러, 이 세션이 나중에 "미완료"로 오분류됩니다.
            curr_prob_no = self.problems[self.current_idx]["no"]
            self.session_manager.update_state(elapsed_seconds=self.elapsed, current_problem_no=curr_prob_no)
            self.submit_exam()
            return

        m, s = divmod(rem, 60)
        self.timer_label.setText(f"{m:02d}:{s:02d}")
        # 남은 시간이 넉넉할 때부터 빨간색이면 시작하자마자 "위험" 신호로 느껴지므로,
        # 마지막 10분(그리고 그 절반인 5분)부터 단계적으로 경고 색을 씁니다.
        if rem <= 300:
            self.timer_label.setStyleSheet("color: #FF5252;")
        elif rem <= 600:
            self.timer_label.setStyleSheet("color: #FFB74D;")
        else:
            self.timer_label.setStyleSheet(f"color: {theme.tokens()['panel_text']};")

        curr_prob_no = self.problems[self.current_idx]["no"]
        self.session_manager.update_state(elapsed_seconds=self.elapsed, current_problem_no=curr_prob_no)

    def on_code_typed(self):
        curr_prob_no = self.problems[self.current_idx]["no"]
        self.session_manager.on_code_changed(curr_prob_no, self.code_editor.toPlainText())
        
    def load_problem(self, idx):
        if idx < 0 or idx >= len(self.problems):
            return
        self.current_idx = idx
        p = self.problems[idx]

        self.progress_label.setText(f"문제 {idx+1} / {len(self.problems)} | {p['session']}")

        self.md_viewer.setHtml(self._build_problem_html(p))

        session_data = self.session_manager.get_data()
        saved_code = session_data["code_by_problem"].get(str(p['no']), "")

        self.code_editor.blockSignals(True)
        self.code_editor.setPlainText(saved_code)
        self.code_editor.blockSignals(False)

        self._reset_console_placeholder()
        self._reset_answer_placeholder()
        self.clear_plot()
        self._apply_lock_state(p)
        self.tabs.setCurrentWidget(self.answer_output if self._is_revealed(p) else self.console_output)

        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < len(self.problems) - 1)
        self._refresh_problem_nav()

    def _jump_to_problem(self, problem_no):
        for i, p in enumerate(self.problems):
            if p["no"] == problem_no:
                self.load_problem(i)
                return

    def _refresh_problem_nav(self):
        t = theme.tokens()
        graded = self.session_manager.get_data()["graded_results"]
        for p in self.problems:
            btn = self.nav_buttons[p["no"]]
            entry = graded.get(str(p["no"]))
            is_current = (p["no"] == self.problems[self.current_idx]["no"])
            if entry and entry.get("note") == "정답 보기 사용":
                color, text_color = "#C9A227", "white"  # 정답 보기 사용 (골드)
            elif entry and entry.get("is_correct"):
                color, text_color = "#4CAF50", "white"  # 정답 (초록)
            elif entry:
                color, text_color = "#B22222", "white"  # 오답 (빨강)
            else:
                color, text_color = t['btn_bg'], t['btn_text']  # 미응시
            border = f"2px solid {t['accent_blue']}" if is_current else f"1px solid {t['panel_border']}"
            btn.setChecked(is_current)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}; color: {text_color}; font-weight: bold;
                    border: {border}; border-radius: 4px;
                }}
            """)

    def prev_problem(self):
        self.load_problem(self.current_idx - 1)

    def next_problem(self):
        self.load_problem(self.current_idx + 1)

    def reset_exam(self):
        reply = QMessageBox.question(
            self, "처음부터 다시 풀기",
            "지금까지의 답안과 채점 결과가 모두 초기화되고 1번 문제로 돌아갑니다. 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.session_manager.create_new_session(self.exam_data["exam_id"], self.exam_data["time_limit_minutes"])
            self.elapsed = 0
            self.load_problem(0)
        
    def show_answer(self):
        p = self.problems[self.current_idx]
        reply = QMessageBox.question(self, "정답 보기", "정답을 보면 이 문제는 0점 처리됩니다. 계속하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.session_manager.update_state(graded_updates={str(p["no"]): {"is_correct": False, "points_earned": 0, "note": "정답 보기 사용", "detail": "❌ 코드를 실행해보지 않고 정답을 먼저 확인하여 0점 처리되었습니다."}})
            self.session_manager.save_now()
            self._apply_lock_state(p)
            self.tabs.setCurrentWidget(self.answer_output)
            self._refresh_problem_nav()
            
    def _on_plot_callback(self, fig):
        self.plot_signal.emit(fig)
        
    def _on_console_callback(self, text):
        self.console_signal.emit(text)
        
    def _is_stale_run_update(self):
        """지금 그리려는 콘솔/그래프 갱신이, 실행이 시작된 뒤 이미 다른 문제로 넘어가서
        더 이상 화면에 보이지 않는 문제의 것인지 확인합니다."""
        return self._active_run_no is not None and self._active_run_no != self.problems[self.current_idx]["no"]

    @Slot(object)
    def render_plot(self, fig):
        if self._is_stale_run_update():
            return
        self.clear_plot()
        canvas = FigureCanvasQTAgg(fig)
        self.plot_container.addWidget(canvas)
        self.tabs.setCurrentIndex(1)

    @Slot(str)
    def append_console(self, text):
        if self._is_stale_run_update():
            return
        self.console_output.append(text)

    @Slot()
    def _on_run_finished(self):
        self._is_running = False
        self._active_run_no = None
        self.btn_run.setEnabled(True)
        self.btn_submit.setEnabled(True)
        self._refresh_problem_nav()

    def clear_plot(self):
        for i in reversed(range(self.plot_container.count())): 
            widget_to_remove = self.plot_container.itemAt(i).widget()
            self.plot_container.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)
            
    def run_current_code(self):
        if self._is_running:
            # matplotlib은 process-global 상태를 쓰기 때문에 실행이 겹치면 서로의 그래프
            # 캡처를 깨뜨릴 수 있어, 한 번에 하나의 실행만 허용합니다.
            return

        p = self.problems[self.current_idx]
        code = self.code_editor.toPlainText()

        self.console_output.clear()
        self.clear_plot()
        self.console_output.append("실행 중...")

        self._is_running = True
        self._active_run_no = p["no"]
        self.btn_run.setEnabled(False)
        # 채점이 아직 안 끝난 문제가 있는 채로 "최종 제출"이 눌리면, 실행이 끝난 뒤 나올 결과가
        # 최종 리포트/오답노트에는 전혀 반영되지 않고 그냥 미응시로 처리되어버립니다. 실행 중에는
        # 아예 제출 버튼을 막아서 이 상황 자체가 생기지 않게 합니다.
        self.btn_submit.setEnabled(False)

        session_data = self.session_manager.get_data()
        all_problems = session_data["code_by_problem"]
        run_generation = self.session_manager.get_generation()

        def _run():
            try:
                timeout = 180.0 if "딥러닝" in p.get("session", "") else 30.0
                ns, out, err = self.executor.run_problem(p["no"], code, all_problems, timeout=timeout)

                if err:
                    is_correct = False
                    detail = "❌ 코드 실행 중 에러가 발생하여 오답 처리되었습니다. (콘솔 확인)"
                else:
                    is_correct, detail = self.grader.grade_problem(ns, p)

                # revealed 여부는 실행을 "시작"하던 시점이 아니라 지금(실행이 끝난 시점) 다시 확인합니다.
                # 실행 중(최대 180초)에 사용자가 "정답 보기"를 누르는 경우에도 잠금이 항상 이기도록 하기
                # 위함입니다. 그리고 실제 기록은 record_graded_result()가 락 안에서 한 번 더 확인하므로,
                # 이 확인과 기록 사이의 아주 짧은 순간에 정답 보기가 눌리더라도 결국 잠금이 유지됩니다.
                if self._is_revealed(p):
                    # 정답을 이미 확인한 문제는 실행/연습은 자유롭게 허용하되, 채점 결과는
                    # 무엇을 실행하든 항상 0점으로 고정합니다(정답 보기 = 0점 확정 원칙 유지).
                    detail += "  (※ 정답을 확인한 문제라 실행 결과와 무관하게 0점으로 고정됩니다)"
                    computed_entry = {"is_correct": False, "points_earned": 0, "note": "정답 보기 사용", "detail": detail}
                else:
                    earned = p["points"] if is_correct else 0
                    computed_entry = {"is_correct": is_correct, "points_earned": earned, "detail": detail}

                self.console_signal.emit(f"\n[채점 결과] {detail}")
                # expected_generation: 실행 도중 reset_exam()으로 세션 자체가 통째로 바뀌었다면
                # (즉 지금 이 결과가 이미 사라진 옛 세션을 향한 것이라면) 새 세션에 잘못 기록되지
                # 않도록 막습니다.
                self.session_manager.record_graded_result(p["no"], computed_entry, expected_generation=run_generation)
            finally:
                self.run_finished_signal.emit()

        # daemon=True: 창을 닫아도 이 스레드 때문에 프로세스가 안 죽고 남아있지 않도록 합니다.
        # (CodeExecutor의 타임아웃은 sys.settrace 기반이라 C-level 대기/무한루프는 못 끊으므로,
        # 정말 안 끝나는 스레드가 있어도 최소한 앱 종료는 막지 않게 됩니다.)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        
    def closeEvent(self, event):
        # 이미 제출 완료된 뒤(submit_exam이 스스로 self.close()를 호출하는 경로)라면
        # 다시 확인창을 띄우지 않고 그대로 닫습니다.
        session_data = self.session_manager.get_data()
        if session_data.get("is_submitted", False):
            event.accept()
            return

        reply = QMessageBox.question(
            self, "종료 확인",
            "아직 제출하지 않았습니다. 지금까지 푼 코드는 저장되어 있어 다음에 실행하면 이어서 풀 수 있습니다.\n종료하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            curr_prob_no = self.problems[self.current_idx]["no"]
            self.session_manager.update_state(elapsed_seconds=self.elapsed, current_problem_no=curr_prob_no)
            self.session_manager.stop_all()
            self.session_manager.save_now()
            event.accept()
        else:
            event.ignore()

    def submit_exam(self):
        if self._is_running:
            # 시간초과 자동제출은 버튼 비활성화를 거치지 않고 직접 이 메서드를 호출하므로,
            # 아직 채점 중인 문제가 있다면(최대 180초) 그 결과가 나올 때까지 기다렸다가
            # 제출합니다. 그렇지 않으면 실행이 끝나기 직전에 결과가 통째로 유실됩니다.
            if not getattr(self, "_submit_wait_notified", False):
                self._submit_wait_notified = True
                self.console_output.append("\n⏳ 아직 채점 중인 문제가 있어, 결과가 나온 뒤 자동으로 제출됩니다...")
            QTimer.singleShot(300, self.submit_exam)
            return

        self.clock_timer.stop()
        self.session_manager.stop_all()
        # is_submitted 플래그를 남겨야 find_unfinished_sessions()가 이 세션을 완료로 인식합니다
        # (elapsed_seconds만으로는 시간초과 자동제출 경로에서 정확히 반영되지 않을 수 있음).
        self.session_manager.mark_submitted()
        self.session_manager.save_now()
        
        session_data = self.session_manager.get_data()
        graded = session_data["graded_results"]
        
        results_list = []
        for p in self.problems:
            res = graded.get(str(p["no"]))
            if res:
                results_list.append((p["no"], p["points"], res["is_correct"]))
            else:
                results_list.append((p["no"], p["points"], False))
                
        report = self.grader.report(results_list, self.exam_data["total_points_v1"])

        QMessageBox.information(self, "최종 제출", report)

        review_dialog = ReviewNoteDialog(self.exam_data, self.problems, graded,
                                          session_data["code_by_problem"], parent=self)
        review_dialog.exec()

        self.close()
