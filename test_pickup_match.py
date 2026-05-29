"""
픽업 템플릿 매칭 테스트
────────────────────────
봇이 실제로 사용하는 pickup_*.png 템플릿으로 게임 화면을 스캔.
어떤 아이템이 매칭되고 점수가 얼마인지 실시간으로 확인.

조작:
  스페이스 : 현재 프레임 스캔 + 결과 출력
  S        : 스캔 + debug_pickup/ 에 디버그 이미지 저장
  Q        : 종료
"""
import os
import sys
import time
import glob
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_window import WindowCapture
from ent_bot_config import BotConfig

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
TMPL_DIR   = os.path.join(BASE_DIR, "templates")
DEBUG_DIR  = os.path.join(BASE_DIR, "debug_pickup")
CONFIG_PATH = os.path.join(BASE_DIR, "ent_config.json")

# template_scanner.py 와 동일한 임계값
PICKUP_THRESHOLDS = {
    "pickup_012.png": 0.80,   # 마력의 돌 — 화살 오매칭 방지
}
DEFAULT_THRESHOLD = 0.72

os.makedirs(DEBUG_DIR, exist_ok=True)

def load_templates():
    tmpls = []
    for f in sorted(glob.glob(os.path.join(TMPL_DIR, "pickup_*.png"))):
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            name = os.path.basename(f)
            thr  = PICKUP_THRESHOLDS.get(name, DEFAULT_THRESHOLD)
            tmpls.append((name, img, thr))
            print(f"  로드: {name}  {img.shape[1]}x{img.shape[0]}  thr={thr}")
    return tmpls

def scan(frame, templates):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best_score, best_name, best_pos = 0.0, None, None
    all_hits = []

    for name, tmpl, thr in templates:
        th, tw = tmpl.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            continue
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= thr:
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            all_hits.append((name, max_val, cx, cy, max_loc, tw, th))
            if max_val > best_score:
                best_score = max_val
                best_name  = name
                best_pos   = (cx, cy)
        else:
            all_hits.append((name, max_val, None, None, None, tw, th))

    return all_hits, best_name, best_score, best_pos

def draw_results(frame, hits):
    vis = frame.copy()
    for (name, score, cx, cy, loc, tw, th) in hits:
        if loc is None:
            continue
        x1, y1 = loc
        x2, y2 = x1 + tw, y1 + th
        col = (0, 255, 0) if score >= 0.80 else (0, 200, 255)
        cv2.rectangle(vis, (x1, y1), (x2, y2), col, 2)
        cv2.putText(vis, f"{name} {score:.3f}", (x1, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
    return vis

def main():
    cfg    = BotConfig(CONFIG_PATH)
    wincap = WindowCapture(cfg.window_title)
    print(f"창 감지 완료: {wincap.w}x{wincap.h}")

    print("\n=== 픽업 템플릿 로드 ===")
    templates = load_templates()
    if not templates:
        print("templates/pickup_*.png 파일이 없습니다.")
        return

    print("\n=== 조작 ===")
    print("  SPACE : 스캔 + 결과 출력")
    print("  S     : 스캔 + 디버그 이미지 저장")
    print("  Q     : 종료")
    print("\n창에 포커스 두고 조작하세요.\n")

    cv2.namedWindow("pickup_test", cv2.WINDOW_NORMAL)

    while True:
        frame = wincap.get_screenshot()
        if frame is None:
            time.sleep(0.05)
            continue

        cv2.imshow("pickup_test", frame)
        key = cv2.waitKey(30) & 0xFF

        if key == ord('q'):
            break
        elif key in (ord(' '), ord('s')):
            save = (key == ord('s'))
            hits, best_name, best_score, best_pos = scan(frame, templates)

            print(f"\n[스캔] ──────────────────────────")
            for (name, score, cx, cy, loc, tw, th) in hits:
                hit = "HIT " if loc is not None else "miss"
                print(f"  {hit}  {name:20s}  score={score:.3f}  pos=({cx},{cy})" if loc else
                      f"  {hit}  {name:20s}  score={score:.3f}")

            if best_pos:
                print(f"\n  → 최고 매칭: {best_name}  score={best_score:.3f}  pos={best_pos}")
            else:
                print("\n  → 매칭 없음")

            if save:
                vis  = draw_results(frame, hits)
                ts   = time.strftime("%H%M%S")
                path = os.path.join(DEBUG_DIR, f"{ts}_pickup.png")
                cv2.imwrite(path, vis)
                print(f"  저장: {path}")

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
