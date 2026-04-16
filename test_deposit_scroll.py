"""
혈맹 창고 맡기기 - 스크롤 검색 테스트
──────────────────────────────────────
사전 조건: 게임 창에서 창고 '물건을 맡긴다' 화면이 이미 열려있는 상태에서 실행.
아이템(엔트의 열매/줄기)이 보이지 않으면 마우스 스크롤로 내려서 찾습니다.
"""
from __future__ import annotations

import os
import sys
import time
import cv2
import numpy as np

from capture_window import WindowCapture
from interception import auto_capture_devices, set_devices, click, move_to, scroll

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW = "Lineage Classic"
ITEM_THRESHOLD = 0.7
MAX_SCROLL = 5          # 최대 스크롤 시도 횟수
SCROLL_PAUSE = 0.5      # 스크롤 후 대기 시간 (초)


def load_template(name):
    path = os.path.join(BASE_DIR, "templates", name)
    tmpl = cv2.imread(path, cv2.IMREAD_COLOR)
    if tmpl is None:
        print(f"[ERROR] 템플릿 로드 실패: {path}")
        sys.exit(1)
    return tmpl


def find_item(frame, tmpl, name="item"):
    result = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= ITEM_THRESHOLD:
        th, tw = tmpl.shape[:2]
        cx = max_loc[0] + tw // 2
        cy = max_loc[1] + th // 2
        print(f"  [{name}] 발견! score={max_val:.3f} pos=({cx},{cy})")
        return (cx, cy)
    print(f"  [{name}] 미발견 score={max_val:.3f}")
    return None


def scroll_to_bottom(count=6):
    """아이템 목록을 맨 아래로 스크롤"""
    print(f"  스크롤 다운 {count}회 (맨 아래로)")
    for _ in range(count):
        scroll("down")
        time.sleep(0.3)


def find_item_with_scroll(wincap, tmpl, name="item"):
    """현재 화면에서 아이템을 찾고, 없으면 스크롤 업하며 재검색"""
    frame = wincap.get_screenshot()
    pos = find_item(frame, tmpl, name)
    if pos:
        return pos

    for i in range(1, MAX_SCROLL + 1):
        print(f"  [{name}] 스크롤 업 {i}/{MAX_SCROLL}")
        scroll("up")
        time.sleep(SCROLL_PAUSE)
        frame = wincap.get_screenshot()
        pos = find_item(frame, tmpl, name)
        if pos:
            return pos

    print(f"  [{name}] {MAX_SCROLL}회 스크롤 후에도 미발견")
    return None


def main():
    print("=== 혈맹 창고 스크롤 검색 테스트 ===")
    print(f"  최대 스크롤: {MAX_SCROLL}회")
    print(f"  매칭 임계값: {ITEM_THRESHOLD}")
    print()

    # 디바이스 초기화
    print("  디바이스 감지 중... (마우스를 움직여주세요)")
    auto_capture_devices(keyboard=True, mouse=True, verbose=True)

    # 템플릿 로드
    fruit_tmpl = load_template("ent_fruit.png")
    stem_tmpl = load_template("ent_stem.png")
    print(f"  엔트의 열매 템플릿: {fruit_tmpl.shape}")
    print(f"  엔트의 줄기 템플릿: {stem_tmpl.shape}")

    # 캡처 초기화
    wincap = WindowCapture(WINDOW)
    time.sleep(0.5)

    print()
    print(">>> 창고 '물건을 맡긴다' 화면을 열어놓고 진행하세요!")
    print(">>> 5초 후 시작합니다... (Ctrl+C로 취소)")
    try:
        for i in range(5, 0, -1):
            print(f"  {i}...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n취소됨")
        return

    print()
    print("─── 맨 아래로 스크롤 ───")
    scroll_to_bottom()
    time.sleep(0.5)

    print()
    print("─── 엔트의 열매 검색 (스크롤 업) ───")
    fruit_pos = find_item_with_scroll(wincap, fruit_tmpl, "엔트의 열매")

    print()
    print("─── 엔트의 줄기 검색 (스크롤 업) ───")
    stem_pos = find_item_with_scroll(wincap, stem_tmpl, "엔트의 줄기")

    print()
    print("=== 결과 ===")
    print(f"  엔트의 열매: {fruit_pos if fruit_pos else '미발견'}")
    print(f"  엔트의 줄기: {stem_pos if stem_pos else '미발견'}")


if __name__ == "__main__":
    main()
