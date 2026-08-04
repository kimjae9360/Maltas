import json
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QHBoxLayout)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt


class StudySelectDialog(QDialog):
    """학습 모드 시작 화면: data/ 폴더에 있는 학습 챕터 중 하나를 골라 chapter_id를 반환."""

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("학습 챕터 선택")
        self.resize(520, 480)
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

        title_label = QLabel("공부할 챕터를 선택하세요")
        title_label.setFont(QFont("Malgun Gothic", 16, QFont.Bold))
        layout.addWidget(title_label)

        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Malgun Gothic", 13))
        for chapter_id, title, num_sections, num_practices in self.chapters:
            item = QListWidgetItem(f"{title}   ({num_sections}개 섹션 · TODO {num_practices}문제)")
            item.setData(Qt.UserRole, chapter_id)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(self._on_confirm)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_start = QPushButton("선택한 챕터 시작")
        btn_start.setStyleSheet("""
            QPushButton { background-color: #007ACC; color: white; font-weight: bold; padding: 8px 16px; border-radius: 5px; border: none; }
            QPushButton:hover { background-color: #1B8FE0; }
        """)
        btn_start.clicked.connect(self._on_confirm)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_start)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; }
            QLabel { color: #E6E6E6; }
            QListWidget {
                background-color: #17212B; color: #E6E6E6;
                border: 1px solid #2D3E4E; border-radius: 4px; padding: 4px;
            }
            QListWidget::item { padding: 8px; border-radius: 3px; }
            QListWidget::item:selected { background-color: #264F78; }
        """)

    def _on_confirm(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.selected_chapter_id = item.data(Qt.UserRole)
        self.accept()
