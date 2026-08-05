import re
import threading

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QSplitter, QPlainTextEdit,
                               QTabWidget, QTextBrowser, QMessageBox, QScrollArea,
                               QApplication, QFrame)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QShortcut, QKeySequence

import markdown

from engine.code_executor import CodeExecutor
from engine.grader import Grader
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from resource_path import get_base_dir
from ui import theme
from ui.highlighter import PythonHighlighter
from ui.markdown_utils import make_code_copyable, extract_copy_text
from ui.study_review_dialog import StudyReviewDialog


def _unit_idx(section_no, practice_no=0):
    """섹션의 예제 코드/각 TODO 문제를 하나의 정수 인덱스로 매핑합니다.
    (CodeExecutor.run_problem이 기대하는 '누적 실행 순서' 정수 키를 그대로 재사용하기 위함 —
    섹션당 문제 99개 미만이라는 전제로 section_no*100 + practice_no)"""
    return section_no * 100 + practice_no


_EXAMPLE_CELL_MARKER_RE = re.compile(r'^\s*#\s*%%\s*(.*)$')


def _split_example_cells(code):
    """'# %% 라벨' 마커로 example_code를 여러 셀로 나눈다 (웹의 splitExampleCells와 동일 로직).
    한 코드창에 몰아 보여주면 어려운 예제를, 개념 단위로 잘라 각각 라벨을 붙여 보여주기 위함."""
    lines = code.split("\n")
    cells = []
    current_label = None
    current_lines = []
    for line in lines:
        m = _EXAMPLE_CELL_MARKER_RE.match(line)
        if m:
            cells.append((current_label, "\n".join(current_lines).strip()))
            current_label = m.group(1).strip() or None
            current_lines = []
        else:
            current_lines.append(line)
    cells.append((current_label, "\n".join(current_lines).strip()))
    return [(label, c) for label, c in cells if c]


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
        root_layout = QVBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 상단 바: 챕터 제목 + 글꼴/테마/복습 버튼만 두는 얇은 바 (섹션 이동은 좌측 사이드바가 담당)
        self.top_bar = QWidget()
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(24, 14, 24, 14)

        self.chapter_title_label = QLabel(self.chapter_data.get("title", ""))
        self.chapter_title_label.setFont(QFont("Malgun Gothic", 15, QFont.Bold))

        self.btn_font_minus = QPushButton("A-")
        self.btn_font_minus.setFixedWidth(40)
        self.btn_font_minus.clicked.connect(lambda: self.change_font_size(-2))
        self.btn_font_plus = QPushButton("A+")
        self.btn_font_plus.setFixedWidth(40)
        self.btn_font_plus.clicked.connect(lambda: self.change_font_size(2))

        self.btn_review = QPushButton("📝 복습 모드")
        self.btn_review.clicked.connect(self.open_review_mode)

        self.btn_reset_chapter = QPushButton("↺ 처음부터 다시 풀기")
        self.btn_reset_chapter.clicked.connect(self.reset_chapter)

        self.btn_theme_toggle = QPushButton()
        self.btn_theme_toggle.setFixedWidth(40)
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        self._refresh_theme_toggle_label()

        top_bar_layout.addWidget(self.chapter_title_label)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.btn_font_minus)
        top_bar_layout.addWidget(self.btn_font_plus)
        top_bar_layout.addSpacing(16)
        top_bar_layout.addWidget(self.btn_theme_toggle)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(self.btn_reset_chapter)
        top_bar_layout.addSpacing(8)
        top_bar_layout.addWidget(self.btn_review)
        root_layout.addWidget(self.top_bar)

        # 본문: 좌측에 섹션 목록을 상시 노출하는 사이드바(스포티파이의 플레이리스트 목록과 같은 역할) +
        # 우측에 기존 이론/예제/TODO 콘텐츠. 예전엔 섹션 번호만 작은 버튼으로 한 줄에 눌러담았는데,
        # 지금은 제목까지 보이는 카드형 목록으로 바꿔서 지금 몇 번 섹션에 뭐가 있는지 한눈에 훑을 수 있다.
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(232)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 18, 12, 12)
        sidebar_layout.setSpacing(8)

        self.sidebar_title = QLabel("섹션 목록")
        self.sidebar_title.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        sidebar_layout.addWidget(self.sidebar_title)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_list_widget = QWidget()
        self._sidebar_list_layout = QVBoxLayout(sidebar_list_widget)
        self._sidebar_list_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebar_list_layout.setSpacing(3)
        self.section_nav_buttons = {}
        for s in self.sections:
            btn = QPushButton(self._sidebar_item_text(s))
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, no=s["no"]: self._jump_to_section(no))
            self._sidebar_list_layout.addWidget(btn)
            self.section_nav_buttons[s["no"]] = btn
        self._sidebar_list_layout.addStretch()
        sidebar_scroll.setWidget(sidebar_list_widget)
        sidebar_layout.addWidget(sidebar_scroll)
        body_layout.addWidget(self.sidebar)

        h_splitter = QSplitter(Qt.Horizontal)
        h_splitter.setHandleWidth(14)
        self.h_splitter = h_splitter

        # 좌측: 이론 + 개념 정리 (섹션 전체에서 공통)
        self.theory_viewer = QTextBrowser()
        self.theory_viewer.setOpenLinks(False)
        self.theory_viewer.anchorClicked.connect(self._on_inline_code_clicked)
        h_splitter.addWidget(self.theory_viewer)

        v_splitter = QSplitter(Qt.Vertical)
        # 스플리터 핸들 자체를 넓게 잡고 배경색과 같게 칠해서, 예제/TODO/콘솔 세 카드 사이에
        # 확실한 여백처럼 보이게 한다 — 예제와 문제가 경계 없이 붙어 보인다는 피드백을 반영.
        v_splitter.setHandleWidth(14)
        self.v_splitter = v_splitter

        # 우측 상단: 예제 코드 (카드로 감싸서 TODO 카드와 뚜렷하게 분리)
        self.example_card = QWidget()
        example_layout = QVBoxLayout(self.example_card)
        example_layout.setContentsMargins(16, 14, 16, 14)
        example_layout.setSpacing(10)

        example_header = QHBoxLayout()
        self.example_label = QLabel("💻 예제 코드 (직접 실행해서 결과를 확인해보세요)")
        self.example_label.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        self.btn_run_example = QPushButton("▶ 예제 실행해보기")
        self.btn_run_example.clicked.connect(self.run_current_example)
        example_header.addWidget(self.example_label)
        example_header.addStretch()
        example_header.addWidget(self.btn_run_example)

        # 예제 코드는 "# %%" 마커로 여러 개념 단위 셀로 나뉘어 표시된다(_set_example_code).
        # 셀 개수가 섹션마다 달라 전체 높이가 유동적이므로 스크롤 영역으로 감싼다.
        self._example_cell_editors = []
        example_scroll = QScrollArea()
        example_scroll.setWidgetResizable(True)
        example_scroll.setMaximumHeight(240)
        example_scroll.setFrameShape(QFrame.NoFrame)
        self._example_container = QWidget()
        self._example_cells_layout = QVBoxLayout(self._example_container)
        self._example_cells_layout.setContentsMargins(4, 4, 4, 4)
        self._example_cells_layout.setSpacing(8)
        example_scroll.setWidget(self._example_container)

        example_layout.addLayout(example_header)
        example_layout.addWidget(example_scroll)
        v_splitter.addWidget(self.example_card)

        # 우측 중단: TODO 문제 (마찬가지로 카드로 감싼다)
        self.practice_card = QWidget()
        practice_layout = QVBoxLayout(self.practice_card)
        practice_layout.setContentsMargins(16, 14, 16, 14)
        practice_layout.setSpacing(10)

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
        self.practice_prompt_viewer.setOpenLinks(False)
        self.practice_prompt_viewer.anchorClicked.connect(self._on_inline_code_clicked)

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
        v_splitter.addWidget(self.practice_card)

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

        # h_splitter를 여백 있는 컨테이너로 한 번 더 감싼다 — 안 그러면 카드들이 창 가장자리에
        # 딱 붙어서, 둥근 모서리가 잘려 보이는 것처럼 어색해진다.
        content_wrap = QWidget()
        content_wrap_layout = QVBoxLayout(content_wrap)
        content_wrap_layout.setContentsMargins(16, 16, 16, 16)
        content_wrap_layout.addWidget(h_splitter)
        body_layout.addWidget(content_wrap, 1)
        root_layout.addWidget(body_widget, 1)

        # 하단 바: 이전/다음 섹션 이동 + 진행 상황을, 재생바 형태로 화면 맨 아래 고정.
        # 사이드바가 "어디로 갈지 고르는 곳"이라면, 여기는 "순서대로 진행하는" 주 동선이라
        # 둘의 역할을 분리했다(막힌 섹션이면 next_section 내부에서 그대로 안내 메시지가 뜬다).
        self.bottom_bar = QWidget()
        bottom_bar_layout = QHBoxLayout(self.bottom_bar)
        bottom_bar_layout.setContentsMargins(24, 12, 24, 12)

        self.btn_prev_section = QPushButton("◀ 이전 섹션")
        self.btn_prev_section.clicked.connect(self.prev_section)

        self.progress_label = QLabel()
        self.progress_label.setFont(QFont("Malgun Gothic", 12, QFont.Bold))
        self.progress_label.setAlignment(Qt.AlignCenter)

        self.btn_next_section = QPushButton("다음 섹션 ▶")
        self.btn_next_section.clicked.connect(lambda: self.next_section(user_triggered=True))

        bottom_bar_layout.addWidget(self.btn_prev_section)
        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.progress_label)
        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.btn_next_section)
        root_layout.addWidget(self.bottom_bar)

    def _sidebar_item_text(self, section):
        title = section["title"]
        if len(title) > 16:
            title = title[:16] + "…"
        return f"{section['no']}. {title}"

    def apply_theme(self):
        t = theme.tokens()
        self.setStyleSheet(f"QMainWindow {{ background-color: {t['window_bg']}; }}")

        self.top_bar.setStyleSheet(f"background-color: {t['window_bg']}; border-bottom: 1px solid {t['panel_border']};")
        self.bottom_bar.setStyleSheet(f"background-color: {t['bottombar_bg']}; border-top: 1px solid {t['panel_border']};")
        self.sidebar.setStyleSheet(f"background-color: {t['sidebar_bg']};")
        self.chapter_title_label.setStyleSheet(f"color: {t['panel_text']};")
        self.sidebar_title.setStyleSheet(f"color: {t['muted_text']}; letter-spacing: 1px;")

        # 예제/TODO 카드: 뚜렷한 배경+둥근 모서리로 서로 분리되어 보이게 하고, 스플리터 핸들은
        # 창 배경색과 같게 칠해서 카드 사이 "여백"처럼 보이게 한다(실제 드래그 바는 그대로 동작).
        card_style = f"background-color: {t['panel_bg']}; border: 1px solid {t['panel_border']}; border-radius: 12px;"
        self.example_card.setStyleSheet(card_style)
        self.practice_card.setStyleSheet(card_style)
        splitter_handle_style = f"QSplitter::handle {{ background-color: {t['window_bg']}; }}"
        self.h_splitter.setStyleSheet(splitter_handle_style)
        self.v_splitter.setStyleSheet(splitter_handle_style)
        self.progress_label.setStyleSheet(f"color: {t['muted_text']};")
        self.example_label.setStyleSheet(f"color: {t['panel_text']};")
        self.practice_label.setStyleSheet(f"color: {t['panel_text']};")

        self._style_code_editor(revealed=False)
        self.code_editor.setPlaceholderText("# 여기에 코드를 작성하세요")

        self.reveal_banner.setStyleSheet(f"""
            QLabel {{ background-color: {t['reveal_bg']}; color: {t['reveal_text']}; font-weight: bold;
                     padding: 6px 10px; border: 1px solid {t['reveal_border']}; border-radius: 4px; margin-top: 6px; }}
        """)

        self.console_output.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['console_bg']}; color: {t['editor_text']}; border: 1px solid {t['console_border']};
            border-left: 4px solid {t['accent_green']}; border-radius: 4px; padding: 8px;
            selection-background-color: {t['selection_bg']};
        }}
        """)
        self._reset_console_placeholder()

        self.answer_output.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['answer_bg']}; color: {t['editor_text']}; border: 1px solid {t['answer_border']};
            border-left: 4px solid {t['accent_gold']}; border-radius: 4px; padding: 8px;
            selection-background-color: {t['selection_bg']};
        }}
        """)
        self._reset_answer_placeholder()

        self.theory_viewer.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['panel_bg']}; color: {t['panel_text']}; border: 1px solid {t['panel_border']};
            border-left: 4px solid {t['accent_blue']}; border-radius: 4px; padding: 15px;
        }}
        """)

        self.practice_prompt_viewer.setStyleSheet(f"""
        QTextBrowser {{
            background-color: {t['panel_bg']}; color: {t['panel_text']}; border: 1px solid {t['panel_border']};
            border-left: 4px solid {t['accent_blue']}; border-radius: 4px; padding: 10px;
        }}
        """)

        toolbar_btn_style = f"""
        QPushButton {{
            background-color: {t['btn_bg']}; color: {t['btn_text']}; border: 1px solid {t['btn_border']};
            border-radius: 8px; padding: 6px 12px;
        }}
        QPushButton:hover {{ background-color: {t['btn_hover']}; }}
        QPushButton:pressed {{ background-color: {t['btn_pressed']}; }}
        """
        for btn in (self.btn_font_minus, self.btn_font_plus, self.btn_review, self.btn_reset_chapter,
                    self.btn_prev_practice, self.btn_next_practice, self.btn_run_example, self.btn_theme_toggle):
            btn.setStyleSheet(toolbar_btn_style)

        # 하단 재생바의 이전/다음 섹션 버튼은 스포티파이 트랜스포트 버튼처럼 알약형으로 도드라지게.
        pill_btn_style = f"""
        QPushButton {{
            background-color: transparent; color: {t['panel_text']}; border: 1px solid {t['btn_border']};
            border-radius: 18px; padding: 8px 20px; font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {t['btn_hover']}; border-color: {t['brand']}; }}
        QPushButton:pressed {{ background-color: {t['btn_pressed']}; }}
        """
        for btn in (self.btn_prev_section, self.btn_next_section):
            btn.setStyleSheet(pill_btn_style)

        # 예제 코드 셀 스타일도 폰트 크기와 마찬가지로 테마 색을 새로 반영해야 하므로 다시 그린다.
        s = self.sections[self.current_section_idx] if self.sections else None
        if s is not None:
            self._set_example_code(s["example_code"], bool(s["example_code"].strip()))
        self._refresh_theory_html()
        self._refresh_practice_html() if s and s["practices"] else None

    def _style_code_editor(self, revealed):
        t = theme.tokens()
        border_color = t['reveal_border'] if revealed else t['accent_blue_editor']
        self.code_editor.setStyleSheet(f"""
        QPlainTextEdit {{
            background-color: {t['editor_bg']}; color: {t['editor_text']}; border: 1px solid {t['editor_border']};
            border-left: 4px solid {border_color}; border-radius: 4px; padding: 8px;
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
        self._refresh_section_nav()
        pid = None
        if self.sections and self.sections[self.current_section_idx]["practices"]:
            s = self.sections[self.current_section_idx]
            p = s["practices"][self.current_practice_idx]
            pid = self._practice_id(s, p)
        self._style_code_editor(revealed=bool(pid and self.progress_manager.is_revealed(pid)))

    def _reset_console_placeholder(self):
        self.console_output.setHtml(
            f"<i style='color:{theme.tokens()['muted_text']};'>▶ 예제를 실행하거나 '채점하기'를 누르면 결과가 여기에 표시됩니다.</i>"
        )

    def _reset_answer_placeholder(self):
        self.answer_output.setHtml(
            f"<i style='color:{theme.tokens()['muted_text']};'>'정답 보기'를 누르면 이 탭에 정답 코드가 표시됩니다.</i>"
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
        for editor in self._example_cell_editors:
            editor.setFont(font)

    def _theory_css(self):
        t = theme.tokens()
        base = self.editor_font_size + 4
        h2_size = base + 8
        return f"""
        <style>
            p, li, b, strong, td, th {{ font-family: 'Malgun Gothic', sans-serif; font-size: {base}px; line-height: 1.6; color: {t['panel_text']}; }}
            h2, h3 {{ color: {t['accent_blue']}; margin-top: 4px; font-size: {h2_size}px; }}
            code {{ background-color: {t['code_inline_bg']}; padding: 2px 6px; border-radius: 4px; font-family: Consolas; color: {t['code_inline_text']}; font-size: {base}px; }}
            table {{ border-collapse: collapse; margin: 10px 0; }}
            td, th {{ border: 1px solid {t['panel_border']}; padding: 6px 10px; }}
        </style>
        """

    def _refresh_theory_html(self):
        s = self.sections[self.current_section_idx]
        md_text = f"## {s['no']}. {s['title']}\n\n{s['theory_markdown']}\n\n{s['concept_table_markdown']}"
        body = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
        html = self._theory_css() + f"<div>{make_code_copyable(body)}</div>"
        self.theory_viewer.setHtml(html)

    def _refresh_practice_html(self):
        s = self.sections[self.current_section_idx]
        p = s["practices"][self.current_practice_idx]
        md_text = f"**문제 {p['no']}.** {p['prompt_markdown']}"
        body = markdown.markdown(md_text, extensions=['fenced_code'])
        html = self._theory_css() + f"<div>{make_code_copyable(body)}</div>"
        self.practice_prompt_viewer.setHtml(html)

    def _on_inline_code_clicked(self, url):
        text = extract_copy_text(url)
        if text is None:
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"📋 복사됨: {text}", 1500)

    def _render_answer_tab(self, answer_code):
        import html as html_mod
        t = theme.tokens()
        escaped = html_mod.escape(answer_code)
        self.answer_output.setHtml(
            f"<div style='font-family:Consolas; font-size:14px; color:{t['editor_text']};'>"
            f"<p style='color:{t['accent_gold']}; font-weight:bold; margin-bottom:10px;'>✅ 정답 코드 (참고용 — 내 코드와 비교해보세요)</p>"
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
        self._set_example_code(s["example_code"], has_example)
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

    def _set_example_code(self, code, has_example):
        """예제 코드를 '# %%' 마커 기준으로 여러 셀로 나눠 각각 읽기전용 에디터로 보여준다."""
        while self._example_cells_layout.count():
            item = self._example_cells_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._example_cell_editors = []

        t = theme.tokens()
        if not has_example:
            placeholder = QLabel("(이 섹션에는 별도 예제 코드가 없습니다 — 왼쪽 이론을 참고하세요)")
            placeholder.setStyleSheet(f"color: {t['muted_text']}; font-style: italic;")
            self._example_cells_layout.addWidget(placeholder)
            return

        cell_style = f"""
        QPlainTextEdit {{
            background-color: {t['example_bg']}; color: {t['editor_text']}; border: 1px solid {t['example_border']};
            border-left: 4px solid {t['accent_gold']}; border-radius: 4px; padding: 8px;
        }}
        """
        for label, cell_code in _split_example_cells(code):
            if label:
                header = QLabel(label)
                header.setStyleSheet(f"color: {t['accent_gold']}; font-weight: bold; font-size: 11px;")
                self._example_cells_layout.addWidget(header)
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText(cell_code)
            PythonHighlighter(editor.document())
            editor.setFont(QFont("Consolas", self.editor_font_size))
            editor.setStyleSheet(cell_style)
            line_count = cell_code.count("\n") + 1
            editor.setFixedHeight(min(max(editor.fontMetrics().lineSpacing() * (line_count + 1) + 12, 60), 300))
            self._example_cells_layout.addWidget(editor)
            self._example_cell_editors.append(editor)

    def _load_empty_practice_state(self):
        self.practice_label.setText("이 섹션에는 TODO 실습문제가 없습니다 (이론 위주 섹션)")
        self.practice_prompt_viewer.setHtml(
            f"<i style='color:{theme.tokens()['muted_text']};'>이 섹션은 개념 설명 위주라 별도 실습문제가 없습니다. "
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
        self._style_code_editor(revealed)
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
        """좌측 사이드바의 섹션 행 스타일을 다시 그린다. 완료된 섹션은 체크 표시 + 초록,
        지금 보고 있는 섹션은 브랜드 컬러로 채운 알약형(pill) 배경으로 강조한다
        (스포티파이의 "현재 재생 중인 곡" 하이라이트와 같은 역할)."""
        t = theme.tokens()
        session_data = self.progress_manager.get_data()
        completed = set(session_data.get("completed_sections", []))
        for s in self.sections:
            btn = self.section_nav_buttons[s["no"]]
            is_current = (s["no"] == self.sections[self.current_section_idx]["no"])
            is_done = s["no"] in completed
            btn.setText(("✓ " if is_done else "") + self._sidebar_item_text(s))
            btn.setChecked(is_current)

            if is_current:
                bg, hover_bg, text_color, weight = t['sidebar_active_bg'], t['sidebar_active_bg'], t['brand_text'], "bold"
            elif is_done:
                bg, hover_bg, text_color, weight = "transparent", t['sidebar_hover'], t['accent_green'], "normal"
            else:
                bg, hover_bg, text_color, weight = "transparent", t['sidebar_hover'], t['panel_text'], "normal"

            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: {text_color}; font-weight: {weight};
                    border: none; border-radius: 8px; text-align: left; padding: 0 12px; font-size: 13px;
                }}
                QPushButton:hover {{ background-color: {hover_bg}; }}
            """)

    def _jump_to_section(self, section_no):
        for i, s in enumerate(self.sections):
            if s["no"] == section_no:
                self.load_section(i)
                return

    def prev_section(self):
        self.load_section(self.current_section_idx - 1)

    def _has_real_attempt(self, section, practice):
        """힌트/정답만 보고 직접 채점(채점하기)은 안 한 문제를 걸러낸다.
        show_answer()는 attempts를 올리지 않으므로, attempts>0은 곧 '직접 코드를 제출해봤다'는 뜻이다."""
        pid = self._practice_id(section, practice)
        result = self.progress_manager.get_data()["practice_results_by_id"].get(pid)
        return bool(result) and result.get("attempts", 0) > 0

    def _section_complete(self, section):
        return all(self._has_real_attempt(section, p) for p in section["practices"])

    def next_section(self, user_triggered=False):
        if user_triggered and not self._section_complete(self.sections[self.current_section_idx]):
            QMessageBox.information(
                self, "아직 완료되지 않은 문제가 있어요",
                "힌트나 정답을 봤더라도, 직접 코드를 입력하고 '채점하기'를 눌러야 다음 섹션으로 넘어갈 수 있어요."
            )
            return
        self.progress_manager.mark_section_completed(self.sections[self.current_section_idx]["no"])
        if self.current_section_idx + 1 < len(self.sections):
            self.load_section(self.current_section_idx + 1)
        elif user_triggered:
            self._finish_chapter()

    def prev_practice(self):
        self.load_practice(self.current_practice_idx - 1)

    def next_practice(self, user_triggered=False):
        s = self.sections[self.current_section_idx]
        if user_triggered and s["practices"] and not self._has_real_attempt(s, s["practices"][self.current_practice_idx]):
            QMessageBox.information(
                self, "아직 채점하지 않았어요",
                "힌트나 정답을 봤더라도, 직접 코드를 입력하고 '채점하기'를 눌러야 다음 문제로 넘어갈 수 있어요."
            )
            return
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

    def reset_chapter(self):
        """완료 여부와 무관하게 챕터를 처음부터 다시 풀고 싶을 때 쓰는 버튼.
        재진입 시 저장된 코드/정답을 조용히 복원하는 기본 동작은 그대로 두고, 명시적으로
        원할 때만 여기서 전부 초기화한다 — 알림창으로 매번 물어보지 않는 대신 되돌릴 수 없는
        작업이라 확인 한 번은 거친다."""
        reply = QMessageBox.question(
            self, "처음부터 다시 풀기",
            "이 챕터의 진행 상황(코드, 채점 결과, 오답노트)이 모두 초기화됩니다. 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.progress_manager.reset_progress()
        self.load_section(0)

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
                elif not out:
                    # run_problem은 stdout이 비어있으면(예: import만 있고 print가 없는 예제)
                    # 콜백 자체를 안 부르므로, "실행 중..."이 그대로 남아있지 않게 여기서 채워준다.
                    self.console_signal.emit("(출력 없음 — 에러 없이 실행되었습니다)")
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
            # attempts는 여기서 올리지 않는다 — 정답을 "봤다"는 사실만 기록하고, 직접
            # 코드를 입력해 채점하기 전까지는 다음 문제/섹션으로 못 넘어가게 하려는 의도.
            self.progress_manager.ensure_in_wrong_list(pid)
            self.progress_manager.save_now()
            self.reveal_banner.setVisible(True)
            self.reveal_banner.setText("🔒 정답을 확인한 문제입니다 — 이 문제는 복습 리스트에 남습니다. 자유롭게 연습해보세요.")
            self._render_answer_tab(p["answer_code"])
            self.tabs.setCurrentIndex(2)
            self._style_code_editor(revealed=True)

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
