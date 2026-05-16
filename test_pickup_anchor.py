"""
픽업 anchor 슬라이딩 시각화 테스트
────────────────────────────────────
실제 클릭 없이 pickup 템플릿 감지 위치 + anchor 이동 경로를 실시간으로 표시.

조작:
  q   : 종료
  s   : 스냅샷 저장
  c   : anchor 경로 초기화
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

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH  = os.path.join(BASE_DIR, "ent_config.json")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# ── 파라미터 (engine과 동일) ──
PICKUP_THRESHOLD = 0.72
PICKUP_THRESHOLDS = {
    "pickup_001.png": 0.85,
    "pickup_002.png": 0.85,
    "pickup_003.png": 0.72,
    "pickup_004.png": 0.80,
}
STICK_RADIUS     = 100   # anchor 슬라이딩 허용 반경
MISS_CONFIRM     = 4     # N회 연속 미감지 → 종료 판단

# ── 시각화 설정 ──
SCALE        = 0.6       # 미리보기 축소 배율
TRAIL_MAX    = 80        # 경로 최대 점 개수
POLL_MS      = 250       # 스캔 주기 (ms)


def load_templates():
    tmpls = []
    for f in sorted(glob.glob(os.path.join(TEMPLATE_DIR, "pickup_*.png"))):
        img = cv2.imread(f, cv2.IMREAD_COLOR)
        if img is not None:
            name = os.path.basename(f)
            tmpls.append((name, img))
    return tmpls


def find_best_pickup(frame, templates):
    """모든 템플릿 중 최고 점수 위치 반환. (name, score, cx, cy) or None"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best = None
    for name, tmpl in templates:
        tgray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if tmpl.ndim == 3 else tmpl
        th, tw = tgray.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            continue
        res = cv2.matchTemplate(gray, tgray, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        thr = PICKUP_THRESHOLDS.get(name, PICKUP_THRESHOLD)
        if score >= thr:
            cx, cy = loc[0] + tw // 2, loc[1] + th // 2
            if best is None or score > best[1]:
                best = (name, score, cx, cy, tw, th, loc)
    return best


def draw_overlay(frame, detected, anchor, trail, miss):
    vis = frame.copy()
    fh, fw = vis.shape[:2]

    # 경로
    for i in range(1, len(trail)):
        cv2.line(vis, trail[i-1], trail[i], (180, 180, 0), 1)

    # anchor 반경
    if anchor is not None:
        cv2.circle(vis, anchor, STICK_RADIUS, (0, 200, 255), 1)
        cv2.circle(vis, anchor, 5, (0, 200, 255), -1)
        cv2.putText(vis, "anchor", (anchor[0]+8, anchor[1]-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    # 감지 위치
    if detected is not None:
        name, score, cx, cy, tw, th, loc = detected
        x1, y1 = loc[0], loc[1]
        x2, y2 = x1 + tw, y1 + th
        in_radius = (anchor is not None and
                     (cx - anchor[0])**2 + (cy - anchor[1])**2 <= STICK_RADIUS**2)
        color = (0, 255, 80) if in_radius else (0, 80, 255)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
        cv2.circle(vis, (cx, cy), 4, color, -1)
        cv2.putText(vis, f"{name} {score:.3f}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        status = "IN radius" if in_radius else "OUT radius"
        cv2.putText(vis, status, (x1, y2 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    # miss 카운터
    miss_color = (0, 255, 255) if miss == 0 else (0, 100, 255)
    cv2.putText(vis, f"miss={miss}/{MISS_CONFIRM}",
                (10, fh - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, miss_color, 1)
    cv2.putText(vis, f"trail={len(trail)}  radius={STICK_RADIUS}px",
                (10, fh - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    cv2.putText(vis, "q=종료  s=스냅샷  c=경로초기화",
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    # 축소
    w = int(fw * SCALE)
    h = int(fh * SCALE)
    return cv2.resize(vis, (w, h))


def main():
    cfg    = BotConfig(CONFIG_PATH)
    wincap = WindowCapture(cfg.window_title)
    tmpls  = load_templates()
    print(f"[load] pickup 템플릿 {len(tmpls)}개: {[t[0] for t in tmpls]}")
    print(f"[param] stick_radius={STICK_RADIUS}  miss_confirm={MISS_CONFIRM}")
    print("q=종료  s=스냅샷  c=경로 초기화\n")

    anchor : tuple | None = None
    trail  : list[tuple] = []
    miss   = 0
    snap_idx = 0

    while True:
        frame = wincap.get_screenshot()
        if frame is None:
            time.sleep(0.1)
            continue
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        detected = find_best_pickup(frame, tmpls)

        if detected is not None:
            _, _, cx, cy, *_ = detected
            if anchor is None:
                # 첫 감지 → anchor 설정
                anchor = (cx, cy)
                trail  = [anchor]
                miss   = 0
                print(f"[anchor] 초기 설정 → {anchor}")
            else:
                dx = cx - anchor[0]
                dy = cy - anchor[1]
                in_r = dx*dx + dy*dy <= STICK_RADIUS**2
                if in_r:
                    miss = 0
                    # 슬라이딩: anchor 업데이트
                    anchor = (cx, cy)
                    trail.append(anchor)
                    if len(trail) > TRAIL_MAX:
                        trail.pop(0)
                else:
                    miss += 1
                    print(f"[OUT] ({cx},{cy}) radius 밖  miss={miss}")
        else:
            if anchor is not None:
                miss += 1

        if miss >= MISS_CONFIRM and anchor is not None:
            print(f"[END] miss {MISS_CONFIRM}회 → anchor 리셋  경로 {len(trail)}점")
            anchor = None
            trail  = []
            miss   = 0

        vis = draw_overlay(frame, detected, anchor, trail, miss)
        cv2.imshow("픽업 anchor 테스트", vis)

        key = cv2.waitKey(POLL_MS) & 0xFF
        if key == ord('q'):
            break
        if key == ord('s'):
            fname = f"snap_anchor_{snap_idx:03d}.png"
            cv2.imwrite(fname, frame)
            print(f"[스냅샷] {fname}")
            snap_idx += 1
        if key == ord('c'):
            anchor = None
            trail  = []
            miss   = 0
            print("[초기화] anchor + 경로 리셋")

    cv2.destroyAllWindows()
    print("종료")


if __name__ == "__main__":
    main()
