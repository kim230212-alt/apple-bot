"""MP 감시 픽셀 설정 도구

실행:
  python test_mp_detect.py
  python test_mp_detect.py ent_config2.json

조작:
  클릭  → 감시 좌표 설정 (mp_full_pos)
  S     → config 저장
  Q     → 종료

사용법:
  1. MP를 원하는 기준치까지 소모
  2. MP 바 채워진 부분의 오른쪽 끝(경계선) 클릭
  3. 상태가 READY ↔ WAITING 바뀌는지 확인
  4. S키로 저장
"""

import sys, os, json
import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG   = sys.argv[1] if len(sys.argv) > 1 else "ent_config.json"
CFG_PATH = os.path.join(BASE_DIR, CONFIG)

sys.path.insert(0, BASE_DIR)
from capture_window import WindowCapture

with open(CFG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

win_title = cfg.get("window_title", "Lineage Classic")
win_idx   = int(cfg.get("window_index", 0))
wc = WindowCapture(win_title, window_index=win_idx)

watch_pos = list(cfg.get("mp_full_pos", [780, 769]))
threshold = int(cfg.get("mp_bright_threshold", 250))

def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        watch_pos[0] = x
        watch_pos[1] = y
        print(f"[SET] mp_full_pos = ({x}, {y})")

cv2.namedWindow("mp_detect", cv2.WINDOW_NORMAL)
cv2.resizeWindow("mp_detect", 900, 650)
cv2.setMouseCallback("mp_detect", on_mouse)

print(f"config: {CONFIG}")
print(f"현재 mp_full_pos={watch_pos}  mp_bright_threshold={threshold}")
print("MP 바 경계선을 클릭해서 좌표 설정  |  S=저장  Q=종료\n")

while True:
    f = wc.get_screenshot()
    if f is not None:
        if f.ndim == 3 and f.shape[2] == 4:
            f = cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)

        mx, my = watch_pos
        fh, fw = f.shape[:2]
        status = "???"
        bgr_txt = ""
        color = (150, 150, 150)

        if 0 <= mx < fw and 0 <= my < fh:
            b = int(f[my, mx][0])
            g = int(f[my, mx][1])
            r = int(f[my, mx][2])
            bright = b + g + r
            bgr_txt = f"BGR=({b},{g},{r}) 합={bright}"
            if bright < threshold:
                status = "READY"
                color  = (0, 255, 0)
            else:
                status = "WAITING"
                color  = (0, 100, 255)

        cv2.drawMarker(f, (mx, my), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)
        cv2.putText(f, f"[{status}] {bgr_txt}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
        cv2.putText(f, f"pos=({mx},{my})  thr={threshold}  클릭=좌표설정  S=저장  Q=종료",
                    (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.imshow("mp_detect", f)

    key = cv2.waitKey(30) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s"):
        cfg["mp_full_pos"] = [watch_pos[0], watch_pos[1]]
        cfg["mp_bright_threshold"] = threshold
        with open(CFG_PATH, "w", encoding="utf-8") as f_out:
            json.dump(cfg, f_out, ensure_ascii=False, indent=2)
        print(f"[SAVED] mp_full_pos={watch_pos}  →  {CONFIG}")

cv2.destroyAllWindows()
print("종료")
