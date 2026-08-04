import html as html_mod
from pathlib import Path

import markdown
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                               QTextBrowser, QMessageBox, QFileDialog, QLabel,
                               QApplication)
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtPrintSupport import QPrinter


class ReviewNoteDialog(QDialog):
    """최종 제출 후 틀린 문제들만 모아 오답노트(문제/내 코드/틀린 이유/정답)를 보여주고,
    클립보드 복사 또는 PDF 저장을 할 수 있게 하는 창."""

    def __init__(self, exam_data, problems, graded_results, code_by_problem, parent=None):
        super().__init__(parent)
        self.exam_data = exam_data
        self.wrong_items = self._collect_wrong_items(problems, graded_results, code_by_problem)
        self.setWindowTitle(f"오답노트 - {exam_data.get('title', '')}")
        self.resize(1000, 800)
        self._setup_ui()

    def _collect_wrong_items(self, problems, graded_results, code_by_problem):
        items = []
        for p in problems:
            entry = graded_results.get(str(p["no"]))
            if entry and entry.get("is_correct"):
                continue
            my_code = (code_by_problem.get(str(p["no"])) or "").strip()
            if entry and entry.get("detail"):
                detail = entry["detail"]
            elif entry:
                detail = "❌ 오답 처리되었습니다. (상세 사유 없음)"
            else:
                detail = "이 문제는 실행/채점을 시도한 기록이 없습니다. (미응시)"
            items.append({
                "no": p["no"],
                "session": p.get("session", ""),
                "points": p.get("points", 0),
                "prompt_markdown": p.get("prompt_markdown", ""),
                "my_code": my_code if my_code else "(제출된 코드 없음)",
                "detail": detail,
                "answer_code": p.get("answer_code", ""),
            })
        return items

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel()
        header.setFont(QFont("Malgun Gothic", 13, QFont.Bold))
        if self.wrong_items:
            header.setText(f"틀린 문제 {len(self.wrong_items)}개 — 문제 / 내 코드 / 틀린 이유 / 정답을 정리했습니다.")
        else:
            header.setText("🎉 틀린 문제가 없습니다! 오답노트가 필요 없어요.")
        layout.addWidget(header)

        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setHtml(self._build_html())
        layout.addWidget(self.viewer)

        btn_layout = QHBoxLayout()
        self.btn_copy = QPushButton("📋 클립보드에 복사")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        self.btn_pdf = QPushButton("💾 PDF로 저장")
        self.btn_pdf.clicked.connect(self._save_as_pdf)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_copy)
        btn_layout.addWidget(self.btn_pdf)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        if not self.wrong_items:
            self.btn_copy.setEnabled(False)
            self.btn_pdf.setEnabled(False)

    def _build_html(self):
        css = """
        <style>
            body { font-family: 'Malgun Gothic', sans-serif; font-size: 14px; color: #222222; }
            h1 { color: #1A1A1A; }
            h2 { color: #B22222; border-bottom: 2px solid #B22222; padding-bottom: 4px; margin-top: 28px; }
            .points-badge { display:inline-block; background:#C9A227; color:#1A1A1A; font-weight:bold;
                             padding:2px 10px; border-radius:10px; font-size:12px; margin-left:8px; }
            .session-label { color:#777777; margin-bottom:6px; }
            .section-label { font-weight:bold; color:#555555; margin-top:12px; }
            pre { background:#1E1E1E; color:#D4D4D4; padding:10px; border-radius:4px;
                  white-space:pre-wrap; font-family:Consolas, monospace; font-size:13px; }
            .my-code pre { border-left: 4px solid #007ACC; }
            .answer-code pre { border-left: 4px solid #C9A227; }
            .reason { background:#3D1F1F; color:#FF8A80; padding:8px 10px; border-radius:4px;
                      border:1px solid #B22222; }
            hr { border: none; border-top: 1px dashed #999999; margin: 24px 0; }
        </style>
        """
        parts = [css, f"<h1>오답노트 &mdash; {html_mod.escape(self.exam_data.get('title', ''))}</h1>"]
        if not self.wrong_items:
            parts.append("<p>🎉 모든 문제를 맞혔습니다. 오답노트가 없습니다.</p>")
        for item in self.wrong_items:
            prompt_html = markdown.markdown(item["prompt_markdown"] or "*(지문 없음)*")
            parts.append(
                f"<h2>문제 {item['no']} <span class='points-badge'>배점 {item['points']}점</span></h2>"
                f"<div class='session-label'>{html_mod.escape(item['session'])}</div>"
                "<div class='section-label'>📄 문제 지문</div>"
                f"<div>{prompt_html}</div>"
                "<div class='section-label'>✍️ 내가 제출한 코드</div>"
                f"<div class='my-code'><pre>{html_mod.escape(item['my_code'])}</pre></div>"
                "<div class='section-label'>❌ 왜 틀렸는가</div>"
                f"<div class='reason'>{html_mod.escape(item['detail'])}</div>"
                "<div class='section-label'>✅ 정답 코드 (주석 포함 &mdash; 왜 이렇게 푸는지 참고)</div>"
                f"<div class='answer-code'><pre>{html_mod.escape(item['answer_code'])}</pre></div>"
                "<hr/>"
            )
        return "".join(parts)

    def _build_plain_text(self):
        lines = [f"===== 오답노트 — {self.exam_data.get('title', '')} =====", ""]
        if not self.wrong_items:
            lines.append("🎉 모든 문제를 맞혔습니다. 오답노트가 없습니다.")
        for item in self.wrong_items:
            lines.append(f"--- 문제 {item['no']} [{item['session']}] (배점 {item['points']}점) ---")
            lines.append("[문제 지문]")
            lines.append(item["prompt_markdown"] or "(지문 없음)")
            lines.append("")
            lines.append("[내가 제출한 코드]")
            lines.append(item["my_code"])
            lines.append("")
            lines.append("[왜 틀렸는가]")
            lines.append(item["detail"])
            lines.append("")
            lines.append("[정답 코드]")
            lines.append(item["answer_code"])
            lines.append("")
            lines.append("")
        return "\n".join(lines)

    def _copy_to_clipboard(self):
        QApplication.clipboard().setText(self._build_plain_text())
        QMessageBox.information(self, "복사 완료",
                                 "오답노트가 클립보드에 복사되었습니다. 원하는 곳에 붙여넣기(Ctrl+V) 하세요.")

    def _save_as_pdf(self):
        default_name = f"{self.exam_data.get('exam_id', '오답노트')}_오답노트.pdf"
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()
        path, _ = QFileDialog.getSaveFileName(
            self, "오답노트 PDF로 저장", str(default_dir / default_name), "PDF 파일 (*.pdf)"
        )
        if not path:
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)

        doc = QTextDocument()
        doc.setHtml(self._build_html())
        doc.print_(printer)

        QMessageBox.information(self, "저장 완료", f"오답노트를 PDF로 저장했습니다:\n{path}")
