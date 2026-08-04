import re

from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        # VSCode Dark Theme colors
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ["def", "class", "import", "from", "as", "if", "elif", "else",
                    "for", "while", "return", "pass", "break", "continue"]
        for word in keywords:
            self.rules.append((rf'\b{word}\b', keyword_format))

        boolean_format = QTextCharFormat()
        boolean_format.setForeground(QColor("#569cd6"))
        for word in ["True", "False", "None"]:
            self.rules.append((rf'\b{word}\b', boolean_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))
        self.rules.append((r'".*?"', string_format))
        self.rules.append((r"'.*?'", string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))
        self.rules.append((r'#.*', comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
