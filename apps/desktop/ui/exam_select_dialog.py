import json
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QFrame,
                               QScrollArea, QWidget, QGridLayout)
from PySide6.QtGui import QFont

from ui import theme
from ui.selectable_card import SelectableCard


class ExamSelectDialog(QDialog):
    """시작 화면: data/ 폴더에 있는 모의고사 중 하나를 골라 exam_id를 반환."""

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("모의고사 선택")
        self.resize(640, 560)
        self.selected_exam_id = None

        self.exams = []  # [(exam_id, title, total_points_v1, num_problems)]
        for path in sorted(data_dir.glob("모의고사*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.exams.append((d["exam_id"], d.get("title", d["exam_id"]),
                                    d.get("total_points_v1", 0), len(d.get("problems", []))))
            except Exception:
                continue

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.title_label = QLabel("📝 풀어볼 모의고사를 선택하세요")
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
        for i, (exam_id, title, points, n) in enumerate(self.exams):
            card = SelectableCard(exam_id, title, [f"{n}문제", f"{points}점 만점"])
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

    def _on_card_clicked(self, exam_id):
        self.selected_exam_id = exam_id
        self.accept()
