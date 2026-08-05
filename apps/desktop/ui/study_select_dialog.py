import json
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QFrame,
                               QScrollArea, QWidget, QGridLayout)
from PySide6.QtGui import QFont

from ui import theme
from ui.selectable_card import SelectableCard


class StudySelectDialog(QDialog):
    """학습 모드 시작 화면: data/ 폴더에 있는 학습 챕터 중 하나를 골라 chapter_id를 반환."""

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("학습 챕터 선택")
        self.resize(640, 560)
        self.selected_chapter_id = None

        self.chapters = []  # [(chapter_id, title, num_sections, num_practices)]
        for path in sorted(data_dir.glob("study_*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                sections = d.get("sections", [])
                num_practices = sum(len(s.get("practices", [])) for s in sections)
                self.chapters.append((d["chapter_id"], d.get("title", d["chapter_id"]),
                                       len(sections), num_practices))
            except Exception:
                continue

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.title_label = QLabel("📖 공부할 챕터를 선택하세요")
        self.title_label.setFont(QFont("Malgun Gothic", 16, QFont.Bold))
        layout.addWidget(self.title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(12)

        self.cards = []
        cols = 2
        for i, (chapter_id, title, num_sections, num_practices) in enumerate(self.chapters):
            card = SelectableCard(chapter_id, title, [f"{num_sections}섹션", f"TODO {num_practices}개"])
            card.clicked.connect(self._on_card_clicked)
            grid.addWidget(card, i // cols, i % cols)
            self.cards.append(card)
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        self._apply_dialog_theme()

    def _apply_dialog_theme(self):
        t = theme.tokens()
        self.setStyleSheet(f"QDialog {{ background-color: {t['window_bg']}; }}")
        self.title_label.setStyleSheet(f"color: {t['panel_text']};")
        for card in self.cards:
            card.apply_theme(t)

    def _on_card_clicked(self, chapter_id):
        self.selected_chapter_id = chapter_id
        self.accept()
