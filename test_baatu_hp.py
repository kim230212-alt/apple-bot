"""바투 HP 기준 픽셀 설정 도구

실행:
  python test_baatu_hp.py
  python test_baatu_hp.py ent_config2.json

조작:
  클릭  → 감시 좌표 설정 (baatu_hp_pos)
  S     → config 저장
  Q     → 종료

사용법:
  1. HP를 원하는 기준치까지 소모 (바투 쓰거나 맞으면서)
  2. HP 바 채워진 부분의 오른쪽 끝(경계선) 클릭
  3. HP 회복/소모하면서 READY ↔ WAITING 바뀌는지 확인
  4. S키로 저장

  READY   → HP 충분 (바투 허용)
  WAITING → HP 부족 (바투 스킵)
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

hp_pos_cfg = cfg.get("baatu_hp_pos") or [333, 770]
watch_pos  = list(hp_pos_cfg)
threshold  = int(cfg.get("baatu_hp_threshold", 200))

def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        watch_pos[0] = x
        watch_pos[1] = y
        print(f"[SET] baatu_hp_pos = ({x}, {y})")

cv2.namedWindow("baatu_hp", cv2.WINDOW_NORMAL)
cv2.resizeWindow("baatu_hp", 900, 650)
cv2.setMouseCallback("baatu_hp", on_mouse)

print(f"config: {CONFIG}")
print(f"현재 baatu_hp_pos={watch_pos}  baatu_hp_threshold={threshold}")
print("HP 바 경계선 클릭  |  S=저장  Q=종료\n")

while True:
    f = wc.get_screenshot()
    if f is not None:
        if f.ndim == 3 and f.shape[2] == 4:
            f = cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)

        hx, hy = watch_pos
        fh, fw = f.shape[:2]
        status = "???"
        bgr_txt = ""
        color = (150, 150, 150)

        if 0 <= hx < fw and 0 <= hy < fh:
            b = int(f[hy, hx][0])
            g = int(f[hy, hx][1])
            r = int(f[hy, hx][2])
            bright = b + g + r
            bgr_txt = f"BGR=({b},{g},{r}) 합={bright}"
            # HP 바는 채워지면 어두움 → bright < threshold 이면 READY
            if bright < threshold:
                status = "READY"
                color  = (0, 255, 0)
            else:
                status = "WAITING"
                color  = (0, 100, 255)

        cv2.drawMarker(f, (hx, hy), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)
        cv2.putText(f, f"[{status}] {bgr_txt}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
        cv2.putText(f, f"pos=({hx},{hy})  thr={threshold}  클릭=좌표설정  S=저장  Q=종료",
                    (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.imshow("baatu_hp", f)

    key = cv2.waitKey(30) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s"):
        cfg["baatu_hp_pos"] = [watch_pos[0], watch_pos[1]]
        cfg["baatu_hp_threshold"] = threshold
        with open(CFG_PATH, "w", encoding="utf-8") as f_out:
            json.dump(cfg, f_out, ensure_ascii=False, indent=2)
        print(f"[SAVED] baatu_hp_pos={watch_pos}  thr={threshold}  →  {CONFIG}")

cv2.destroyAllWindows()
print("종료")
