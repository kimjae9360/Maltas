from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, Signal

from ui import theme


class ModeCard(QFrame):
    """모의고사/학습 모드 중 하나를 고르는 큰 카드. 시작 화면이 기본 QMessageBox라 너무
    올드해 보인다는 피드백을 받아, 다른 화면들과 같은 테마 톤으로 새로 만들었다."""
    clicked = Signal(str)

    def __init__(self, mode, icon, title, subtitle, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedSize(220, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel(icon)
        self.icon_label.setFont(QFont("Segoe UI Emoji", 28))
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Malgun Gothic", 14, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(QFont("Malgun Gothic", 10))
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

    def mousePressEvent(self, event):
        self.clicked.emit(self.mode)
        super().mousePressEvent(event)

    def apply_theme(self, t):
        self.setStyleSheet(f"""
            ModeCard {{
                background-color: {t['panel_bg']}; border: 1px solid {t['panel_border']}; border-radius: 16px;
            }}
            ModeCard:hover {{ border: 2px solid {t['brand']}; }}
        """)
        self.title_label.setStyleSheet(f"color: {t['panel_text']}; border: none;")
        self.subtitle_label.setStyleSheet(f"color: {t['muted_text']}; border: none;")


class ModeSelectDialog(QDialog):
    """프로그램을 켜면 가장 먼저 보이는 시작 화면: 모의고사 풀기 / 학습 모드 중 선택."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AICE Simulator")
        self.setFixedSize(560, 340)
        self.selected_mode = None  # "exam" | "study" | None(취소)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        self.app_title = QLabel("AICE Simulator")
        self.app_title.setFont(QFont("Malgun Gothic", 20, QFont.Bold))
        self.app_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.app_title)

        self.subtitle = QLabel("무엇을 하시겠습니까?")
        self.subtitle.setFont(QFont("Malgun Gothic", 11))
        self.subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subtitle)

        layout.addSpacing(20)

        card_row = QHBoxLayout()
        card_row.setSpacing(16)
        card_row.setAlignment(Qt.AlignCenter)

        self.exam_card = ModeCard("exam", "📝", "모의고사 풀기", "타이머를 켜고 실전처럼 응시합니다")
        self.study_card = ModeCard("study", "📖", "학습 모드", "이론부터 예제, TODO까지 차근차근")
        for card in (self.exam_card, self.study_card):
            card.clicked.connect(self._on_card_clicked)
            card_row.addWidget(card)

        card_row_widget_layout = QHBoxLayout()
        card_row_widget_layout.addStretch()
        card_row_widget_layout.addLayout(card_row)
        card_row_widget_layout.addStretch()
        layout.addLayout(card_row_widget_layout)

        self._apply_dialog_theme()

    def _apply_dialog_theme(self):
        t = theme.tokens()
        self.setStyleSheet(f"QDialog {{ background-color: {t['window_bg']}; }}")
        self.app_title.setStyleSheet(f"color: {t['panel_text']};")
        self.subtitle.setStyleSheet(f"color: {t['muted_text']};")
        self.exam_card.apply_theme(t)
        self.study_card.apply_theme(t)

    def _on_card_clicked(self, mode):
        self.selected_mode = mode
        self.accept()
