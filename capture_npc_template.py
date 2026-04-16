"""
NPC/아이템 템플릿 캡처 도구
───────────────────────────
게임 화면에서 "엔트", "정령의돌" 등의 텍스트를 드래그로 선택하여
템플릿 이미지로 저장합니다.

사용법:
  python capture_npc_template.py

조작:
  스페이스  : 스크린샷 새로 캡처
  마우스드래그: 영역 선택
  N        : 선택 영역을 NPC 템플릿으로 저장 (npc_001.png, ...)
  P        : 선택 영역을 PICKUP 템플릿으로 저장 (pickup_001.png, ...)
  R        : 선택 초기화
  Q / ESC  : 종료

저장 위치: templates/npc_*.png, templates/pickup_*.png
"""
import os
import sys
import glob
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_window import WindowCapture

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMPL_DIR = os.path.join(BASE_DIR, "templates")
WINDOW_TITLE = "Lineage Classic"

# 마우스 드래그 상태
_drawing = False
_x1, _y1, _x2, _y2 = 0, 0, 0, 0
_frame = None
_display = None


def _mouse_callback(event, x, y, flags, param):
    global _drawing, _x1, _y1, _x2, _y2, _display

    if event == cv2.EVENT_LBUTTONDOWN:
        _drawing = True
        _x1, _y1 = x, y
        _x2, _y2 = x, y
    elif event == cv2.EVENT_MOUSEMOVE and _drawing:
        _x2, _y2 = x, y
        _display = _frame.copy()
        cv2.rectangle(_display, (_x1, _y1), (_x2, _y2), (0, 255, 0), 2)
    elif event == cv2.EVENT_LBUTTONUP:
        _drawing = False
        _x2, _y2 = x, y
        _display = _frame.copy()
        cv2.rectangle(_display, (_x1, _y1), (_x2, _y2), (0, 255, 0), 2)
        # 선택 영역 미리보기 (확대)
        roi = _get_roi()
        if roi is not None:
            h, w = roi.shape[:2]
            zoom = max(3, 200 // max(w, 1))
            zoomed = cv2.resize(roi, (w * zoom, h * zoom), interpolation=cv2.INTER_NEAREST)
            cv2.imshow("Selection (zoomed)", zoomed)


def _get_roi():
    global _x1, _y1, _x2, _y2
    if _frame is None:
        return None
    x1 = min(_x1, _x2)
    y1 = min(_y1, _y2)
    x2 = max(_x1, _x2)
    y2 = max(_y1, _y2)
    if x2 - x1 < 5 or y2 - y1 < 5:
        return None
    return _frame[y1:y2, x1:x2].copy()


def _next_filename(prefix):
    """npc_001.png, npc_002.png, ... 자동 번호 부여"""
    existing = glob.glob(os.path.join(TMPL_DIR, f"{prefix}_*.png"))
    max_num = 0
    for f in existing:
        base = os.path.basename(f)
        # prefix_001.png → 001
        try:
            num_str = base[len(prefix) + 1:].replace(".png", "")
            num = int(num_str)
            max_num = max(max_num, num)
        except ValueError:
            continue
    return os.path.join(TMPL_DIR, f"{prefix}_{max_num + 1:03d}.png")


def main():
    global _frame, _display, _x1, _y1, _x2, _y2

    print("=" * 50)
    print("  NPC/아이템 템플릿 캡처 도구")
    print("=" * 50)
    print()
    print("  스페이스  : 스크린샷 새로 캡처")
    print("  마우스드래그: 텍스트 영역 선택")
    print("  N        : NPC 템플릿 저장 (npc_*.png)")
    print("  P        : PICKUP 템플릿 저장 (pickup_*.png)")
    print("  R        : 선택 초기화")
    print("  Q / ESC  : 종료")
    print()

    try:
        wincap = WindowCapture(WINDOW_TITLE)
    except Exception as e:
        print(f"[오류] 게임 창을 찾을 수 없습니다: {e}")
        sys.exit(1)

    print(f"게임 창 크기: {wincap.w}x{wincap.h}")

    # 첫 캡처
    _frame = wincap.get_screenshot()
    if _frame is None:
        print("[오류] 스크린샷 실패")
        sys.exit(1)

    _display = _frame.copy()

    cv2.namedWindow("Game Capture", cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback("Game Capture", _mouse_callback)

    # 기존 템플릿 표시
    n_npc = len(glob.glob(os.path.join(TMPL_DIR, "npc_*.png")))
    n_pickup = len(glob.glob(os.path.join(TMPL_DIR, "pickup_*.png")))
    print(f"\n기존 템플릿: NPC={n_npc}, PICKUP={n_pickup}")
    print("─" * 50)

    while True:
        cv2.imshow("Game Capture", _display)
        key = cv2.waitKey(50) & 0xFF

        if key == ord('q') or key == 27:  # Q or ESC
            break

        elif key == ord(' '):  # Space: 새 캡처
            _frame = wincap.get_screenshot()
            if _frame is not None:
                _display = _frame.copy()
                _x1, _y1, _x2, _y2 = 0, 0, 0, 0
                print("[캡처] 스크린샷 갱신 완료")
            else:
                print("[오류] 스크린샷 실패")

        elif key == ord('r'):  # R: 선택 초기화
            _x1, _y1, _x2, _y2 = 0, 0, 0, 0
            _display = _frame.copy()
            cv2.destroyWindow("Selection (zoomed)")
            print("[초기화] 선택 영역 초기화")

        elif key == ord('n'):  # N: NPC 템플릿 저장
            roi = _get_roi()
            if roi is None:
                print("[오류] 먼저 영역을 선택하세요 (마우스 드래그)")
                continue
            path = _next_filename("npc")
            cv2.imwrite(path, roi)
            h, w = roi.shape[:2]
            print(f"[저장] NPC 템플릿: {os.path.basename(path)}  {w}x{h}px")
            # 선택 초기화
            _x1, _y1, _x2, _y2 = 0, 0, 0, 0
            _display = _frame.copy()

        elif key == ord('p'):  # P: PICKUP 템플릿 저장
            roi = _get_roi()
            if roi is None:
                print("[오류] 먼저 영역을 선택하세요 (마우스 드래그)")
                continue
            path = _next_filename("pickup")
            cv2.imwrite(path, roi)
            h, w = roi.shape[:2]
            print(f"[저장] PICKUP 템플릿: {os.path.basename(path)}  {w}x{h}px")
            _x1, _y1, _x2, _y2 = 0, 0, 0, 0
            _display = _frame.copy()

    cv2.destroyAllWindows()
    print("\n종료")


if __name__ == "__main__":
    main()
