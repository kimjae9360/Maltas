from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, Signal


class SelectableCard(QFrame):
    """study_select_dialog.py/exam_select_dialog.py가 공통으로 쓰는 클릭 가능한 카드.
    웹 버전 /study, /exams 페이지의 카드형 목록과 톤을 맞추려고, 예전의 QListWidget 텍스트
    한 줄짜리 행 대신 제목+배지가 있는 카드로 만들었다."""
    clicked = Signal(str)

    def __init__(self, item_id, title, badges, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Malgun Gothic", 13, QFont.Bold))
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        self.badge_labels = [QLabel(text) for text in badges]
        for b in self.badge_labels:
            b.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
            badge_row.addWidget(b)
        badge_row.addStretch()
        layout.addLayout(badge_row)

    def mousePressEvent(self, event):
        self.clicked.emit(self.item_id)
        super().mousePressEvent(event)

    def apply_theme(self, t):
        self.setStyleSheet(f"""
            SelectableCard {{
                background-color: {t['panel_bg']}; border: 1px solid {t['panel_border']}; border-radius: 12px;
            }}
            SelectableCard:hover {{ border-color: {t['brand']}; }}
        """)
        self.title_label.setStyleSheet(f"color: {t['panel_text']}; border: none;")
        for b in self.badge_labels:
            b.setStyleSheet(f"""
                background-color: {t['btn_bg']}; color: {t['brand_text']};
                border-radius: 10px; padding: 2px 10px;
            """)
