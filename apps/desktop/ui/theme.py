"""다크/라이트 테마 토큰 + 현재 모드 저장(QSettings, 재시작해도 유지).

웹 버전은 헤더에 다크/라이트 토글이 있는데 데스크탑은 다크 전용이었다 — 이 모듈은
study_window.py/main_window.py가 공통으로 쓰는 색상표를 한 곳에 모아, 토글 버튼 하나로
두 창 모두 테마를 바꿀 수 있게 한다."""
from PySide6.QtCore import QSettings

_SETTINGS = QSettings("Maltas", "AICE_Simulator")

DARK = {
    "window_bg": "#1E1E1E",
    "panel_bg": "#17212B",
    "panel_border": "#2D3E4E",
    "panel_text": "#E6E6E6",
    "editor_bg": "#1E1E1E",
    "editor_text": "#D4D4D4",
    "editor_border": "#333333",
    "example_bg": "#1B1A17",
    "example_border": "#3A362F",
    "console_bg": "#1B1A17",
    "console_border": "#3A362F",
    "answer_bg": "#1E1B12",
    "answer_border": "#4A3F1F",
    "accent_blue": "#4FC1FF",
    "accent_blue_editor": "#007ACC",
    "accent_gold": "#C9A227",
    "accent_green": "#6A9955",
    "reveal_bg": "#3D1F1F",
    "reveal_text": "#FF8A80",
    "reveal_border": "#B22222",
    "btn_bg": "#333844",
    "btn_hover": "#414957",
    "btn_pressed": "#2B303A",
    "btn_border": "#454C5C",
    "btn_text": "#E6E6E6",
    "code_inline_bg": "#1E1E1E",
    "code_inline_text": "#CE9178",
    "muted_text": "#6B6B6B",
    "selection_bg": "#264F78",
}

LIGHT = {
    "window_bg": "#F5F6F8",
    "panel_bg": "#FFFFFF",
    "panel_border": "#D7DCE3",
    "panel_text": "#1A1A1A",
    "editor_bg": "#FFFFFF",
    "editor_text": "#1A1A1A",
    "editor_border": "#C9CED6",
    "example_bg": "#FFFBEF",
    "example_border": "#E8DDBB",
    "console_bg": "#F7F7F5",
    "console_border": "#DDDDD5",
    "answer_bg": "#FFF9E8",
    "answer_border": "#E3D28F",
    "accent_blue": "#0B6FB0",
    "accent_blue_editor": "#1266C4",
    "accent_gold": "#8A6D1F",
    "accent_green": "#3D7A3D",
    "reveal_bg": "#FDEAEA",
    "reveal_text": "#B22222",
    "reveal_border": "#D98A8A",
    "btn_bg": "#E8EAEE",
    "btn_hover": "#D9DCE3",
    "btn_pressed": "#C7CBD3",
    "btn_border": "#C3C8D0",
    "btn_text": "#1A1A1A",
    "code_inline_bg": "#EEF0F3",
    "code_inline_text": "#A0522D",
    "muted_text": "#8A8D92",
    "selection_bg": "#BFD9F2",
}

THEMES = {"dark": DARK, "light": LIGHT}


def get_mode():
    mode = _SETTINGS.value("theme_mode", "dark")
    return mode if mode in THEMES else "dark"


def set_mode(mode):
    _SETTINGS.setValue("theme_mode", mode)


def toggle_mode():
    new_mode = "light" if get_mode() == "dark" else "dark"
    set_mode(new_mode)
    return new_mode


def tokens():
    return THEMES[get_mode()]
