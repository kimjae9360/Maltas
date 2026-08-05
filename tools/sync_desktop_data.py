"""
서버 콘텐츠(apps/server/data)를 데스크탑 앱(apps/desktop/data)으로 동기화합니다.

데스크탑 앱은 "웹을 못 쓰는 상황(오프라인 등)을 위한 다운로드형 대안"으로 계속 유지하기로
했으므로, 서버 콘텐츠(문제/이론 수정)가 데스크탑에도 항상 반영되어야 합니다. source of truth는
항상 apps/server/data — 반대 방향(desktop → server) 동기화는 하지 않습니다.

이미 데스크탑에 같은 이름의 파일이 있는 것만 덮어씁니다. 기출동형 시험, 신규 데이터셋(csv/xlsx)처럼
데스크탑에 아직 없는 파일은 의도적으로 건너뜁니다 — 데스크탑 배포 범위를 넓히는 것은 이 스크립트의
역할이 아니라 별도로 결정할 일입니다.

사용법:
  python tools/sync_desktop_data.py          # 실제로 복사
  python tools/sync_desktop_data.py --check  # 복사하지 않고, 어긋난 파일이 있으면 종료코드 1 (CI용)
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass  # 윈도우 기본 콘솔(cp949)에서 한글 출력이 깨지는 것을 막기 위함

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = REPO_ROOT / "apps" / "server" / "data"
DESKTOP_DATA = REPO_ROOT / "apps" / "desktop" / "data"


def find_drifted_files():
    drifted = []
    for server_path in sorted(SERVER_DATA.iterdir()):
        if not server_path.is_file():
            continue
        desktop_path = DESKTOP_DATA / server_path.name
        if not desktop_path.exists():
            continue
        if not filecmp.cmp(server_path, desktop_path, shallow=False):
            drifted.append(server_path.name)
    return drifted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="복사 없이 드리프트 여부만 확인하고, 있으면 종료코드 1을 반환합니다 (CI용).",
    )
    args = parser.parse_args()

    drifted = find_drifted_files()

    if not drifted:
        print("데스크탑 데이터가 서버와 이미 동일합니다. 할 일 없음.")
        return 0

    if args.check:
        print("다음 파일이 서버와 어긋나 있습니다 (desktop이 최신 서버 콘텐츠를 반영하지 못함):")
        for name in drifted:
            print(f"  - {name}")
        print("\n동기화하려면: python tools/sync_desktop_data.py")
        return 1

    for name in drifted:
        shutil.copyfile(SERVER_DATA / name, DESKTOP_DATA / name)
        print(f"동기화됨: {name}")
    print(f"\n총 {len(drifted)}개 파일을 데스크탑으로 동기화했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
