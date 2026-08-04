import sys
import os


def get_base_dir():
    """읽기 전용 번들 자원(data/ 등) 기준 경로.

    개발 환경(python main.py)에서는 이 파일이 있는 프로젝트 루트를 반환합니다.
    PyInstaller --onedir 빌드에서는 --add-data로 넣은 파일들이 exe 옆이 아니라
    _internal/ 서브폴더 아래에 위치하므로, sys._MEIPASS(PyInstaller가 이 경로를
    정확히 가리키도록 설정해줌)를 써야 onedir/onefile 어느 쪽이든 안전합니다.
    """
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_writable_dir():
    """세션 저장 등 쓰기 가능한 경로 (exe 옆 폴더).

    _MEIPASS(onedir의 _internal, onefile의 임시폴더)는 읽기 전용/임시 취급해야
    하므로, 사용자가 이어서 풀 세션 파일은 항상 exe가 실제로 위치한 폴더에 저장합니다.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
