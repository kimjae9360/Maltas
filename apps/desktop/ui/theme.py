"""다크/라이트 테마 토큰 + 현재 모드 저장(QSettings, 재시작해도 유지).

색 구성은 스포티파이류 앱의 "새까만 배경 위에 카드 몇 단계 밝기 + 좌측 사이드바 +
포인트 컬러 하나" 레이아웃 언어를 참고했다. 포인트 컬러 자체는 스포티파이 초록이 아니라
웹 버전(apps/web/app/globals.css의 --brand)과 통일한 보라색을 쓴다 — 데스크탑과 웹이
서로 다른 브랜드 색을 쓰면 "말타스"라는 하나의 서비스로 안 느껴지기 때문.
study_window.py/main_window.py가 공통으로 쓰는 색상표를 한 곳에 모아, 토글 버튼 하나로
두 창 모두 테마를 바꿀 수 있게 한다."""
from PySide6.QtCore import QSettings

_SETTINGS = QSettings("Maltas", "AICE_Simulator")

DARK = {
    "window_bg": "#121212",
    "sidebar_bg": "#000000",
    "sidebar_hover": "#1A1A1A",
    "sidebar_active_bg": "#2A2540",
    "bottombar_bg": "#181818",
    "panel_bg": "#181818",
    "panel_border": "#282828",
    "panel_text": "#E6E6E6",
    "editor_bg": "#181818",
    "editor_text": "#D4D4D4",
    "editor_border": "#282828",
    "example_bg": "#1B1A17",
    "example_border": "#3A362F",
    "console_bg": "#1B1A17",
    "console_border": "#3A362F",
    "answer_bg": "#1E1B12",
    "answer_border": "#4A3F1F",
    "brand": "#8C82FA",
    "brand_text": "#C9C4FC",
    "accent_blue": "#4FC1FF",
    "accent_blue_editor": "#8C82FA",
    "accent_gold": "#C9A227",
    "accent_green": "#6A9955",
    "reveal_bg": "#3D1F1F",
    "reveal_text": "#FF8A80",
    "reveal_border": "#B22222",
    "btn_bg": "#2A2A2A",
    "btn_hover": "#3A3A3A",
    "btn_pressed": "#1F1F1F",
    "btn_border": "#3A3A3A",
    "btn_text": "#E6E6E6",
    "code_inline_bg": "#282828",
    "code_inline_text": "#CE9178",
    "muted_text": "#A7A7A7",
    "selection_bg": "#4A3F8C",
}

LIGHT = {
    "window_bg": "#FFFFFF",
    "sidebar_bg": "#F7F7FB",
    "sidebar_hover": "#EDEDF5",
    "sidebar_active_bg": "#EFEDFD",
    "bottombar_bg": "#F7F7FB",
    "panel_bg": "#FFFFFF",
    "panel_border": "#E6E4F0",
    "panel_text": "#1A1A1A",
    "editor_bg": "#FFFFFF",
    "editor_text": "#1A1A1A",
    "editor_border": "#E6E4F0",
    "example_bg": "#FFFBEF",
    "example_border": "#E8DDBB",
    "console_bg": "#F7F7F5",
    "console_border": "#DDDDD5",
    "answer_bg": "#FFF9E8",
    "answer_border": "#E3D28F",
    "brand": "#5B4FE5",
    "brand_text": "#4638D1",
    "accent_blue": "#0B6FB0",
    "accent_blue_editor": "#5B4FE5",
    "accent_gold": "#8A6D1F",
    "accent_green": "#3D7A3D",
    "reveal_bg": "#FDEAEA",
    "reveal_text": "#B22222",
    "reveal_border": "#D98A8A",
    "btn_bg": "#EEEDFD",
    "btn_hover": "#DEDBFA",
    "btn_pressed": "#CECBF6",
    "btn_border": "#D7D4F5",
    "btn_text": "#1A1A1A",
    "code_inline_bg": "#EEF0F3",
    "code_inline_text": "#A0522D",
    "muted_text": "#6B6A7A",
    "selection_bg": "#CECBF6",
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
