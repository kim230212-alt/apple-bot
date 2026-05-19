"""
픽업 감지 위치 → 커서 이동 + 반복 클릭 테스트
───────────────────────────────────────────────
감지 시: 커서 이동 + 클릭 (down+up)
미감지 시: miss 카운트 → MISS_CONFIRM 도달 시 중단

조작:
  q   : 종료
"""
import os
import sys
import time
import glob
import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capture_window import WindowCapture
from ent_bot_config import BotConfig
from interception import move_to, mouse_down, mouse_up, auto_capture_devices, click

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH  = os.path.join(BASE_DIR, "ent_config.json")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

PICKUP_THRESHOLD = 0.72
PICKUP_THRESHOLDS = {
    "pickup_012.png": 0.80,
}
BINARY_THRESHOLD = 128
POLL_SEC     = 0.3
MISS_CONFIRM = 4


def load_templates():
    tmpls = []
    for f in sorted(glob.glob(os.path.join(TEMPLATE_DIR, "pickup_*.png"))):
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            _, binary = cv2.threshold(img, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
            tmpls.append((os.path.basename(f), binary))
    return tmpls


def find_best_pickup(frame, templates, scan_rect):
    sx1, sy1, sx2, sy2 = scan_rect
    roi = frame[sy1:sy2, sx1:sx2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, gray = cv2.threshold(gray, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
    best = None
    for name, tmpl in templates:
        th, tw = tmpl.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            continue
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        thr = PICKUP_THRESHOLDS.get(name, PICKUP_THRESHOLD)
        if score >= thr:
            cx = loc[0] + tw // 2 + sx1
            cy = loc[1] + th // 2 + sy1
            if cx >= 300 and (best is None or score > best[1]):
                best = (name, score, cx, cy)
    return best


def main():
    cfg    = BotConfig(CONFIG_PATH)
    wincap = WindowCapture(cfg.window_title)
    tmpls  = load_templates()
    print(f"[load] pickup 템플릿 {len(tmpls)}개: {[t[0] for t in tmpls]}")
    print("감지 시 LMB 홀드 / 미감지 시 해제 — q로 종료\n")

    auto_capture_devices()

    scan_rect = tuple(cfg.ocr_scan_rect)
    miss = 0
    click_count = 0

    while True:
        frame = wincap.get_screenshot()
        if frame is None:
            time.sleep(0.1)
            continue
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        result = find_best_pickup(frame, tmpls, scan_rect)
        if result is not None:
            name, score, cx, cy = result
            sx, sy = wincap.get_screen_position((cx, cy))
            move_to(sx, sy)
            mouse_down("left")
            mouse_up("left")
            click_count += 1
            miss = 0
            print(f"[클릭#{click_count}] {name}  score={score:.3f}  스크린=({sx},{sy})")
        else:
            miss += 1
            if miss >= MISS_CONFIRM:
                if click_count > 0:
                    print(f"[종료] 아이템 미감지 {MISS_CONFIRM}회 → 총 클릭 {click_count}회")
                miss = 0
                click_count = 0

        if cv2.waitKey(int(POLL_SEC * 1000)) & 0xFF == ord('q'):
            break

    print("종료")


if __name__ == "__main__":
    main()
