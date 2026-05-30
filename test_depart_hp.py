"""출발 기준 HP 픽셀 설정 도구

실행:
  python test_depart_hp.py
  python test_depart_hp.py ent_config2.json

조작:
  클릭    → 감시 좌표 설정 + 현재 픽셀 bright 기준으로 threshold 자동 설정
  +/-     → threshold 조절 (10 단위)
  S       → config 저장
  Q       → 종료

사용법:
  1. HP를 사냥터 출발 가능한 최소치까지 채움
  2. HP 바 채워진 부분의 오른쪽 끝(경계선) 클릭
     → threshold 자동 설정됨 (클릭 위치 bright + 50)
  3. HP 올리거나 내리면서 READY ↔ WAITING 바뀌는지 확인
  4. +/- 로 미세 조정 후 S키 저장

  READY   → HP 충분 → 출발 가능
  WAITING → HP 부족 → 대기
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

hp_pos_cfg = cfg.get("depart_hp_pos") or cfg.get("baatu_hp_pos") or [333, 770]
watch_pos  = list(hp_pos_cfg)
threshold  = int(cfg.get("depart_hp_threshold", cfg.get("baatu_hp_threshold", 200)))

last_frame = [None]

def on_mouse(event, x, y, flags, param):
    global threshold
    if event == cv2.EVENT_LBUTTONDOWN:
        watch_pos[0] = x
        watch_pos[1] = y
        # 클릭 위치 현재 bright 로 threshold 자동 설정
        f = last_frame[0]
        if f is not None:
            fh, fw = f.shape[:2]
            if 0 <= x < fw and 0 <= y < fh:
                b = int(f[y, x][0])
                g = int(f[y, x][1])
                r = int(f[y, x][2])
                bright = b + g + r
                threshold = bright + 50
                print(f"[SET] depart_hp_pos=({x},{y})  bright={bright}  threshold={threshold} (자동)")

cv2.namedWindow("depart_hp", cv2.WINDOW_NORMAL)
cv2.resizeWindow("depart_hp", 900, 650)
cv2.setMouseCallback("depart_hp", on_mouse)

print(f"config: {CONFIG}")
print(f"현재 depart_hp_pos={watch_pos}  depart_hp_threshold={threshold}")
print("HP 바 경계선 클릭  |  +/-=threshold 조절  S=저장  Q=종료\n")

while True:
    f = wc.get_screenshot()
    if f is not None:
        if f.ndim == 3 and f.shape[2] == 4:
            f = cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)
        last_frame[0] = f

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
            if bright <= threshold:
                status = "READY"
                color  = (0, 255, 0)
            else:
                status = "WAITING"
                color  = (0, 100, 255)

        cv2.drawMarker(f, (hx, hy), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)
        cv2.putText(f, f"[{status}] {bgr_txt}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
        cv2.putText(f, f"pos=({hx},{hy})  thr={threshold}  +/-=조절  S=저장  Q=종료",
                    (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.imshow("depart_hp", f)

    key = cv2.waitKey(30) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s"):
        cfg["depart_hp_pos"] = [watch_pos[0], watch_pos[1]]
        cfg["depart_hp_threshold"] = threshold
        with open(CFG_PATH, "w", encoding="utf-8") as f_out:
            json.dump(cfg, f_out, ensure_ascii=False, indent=2)
        print(f"[SAVED] depart_hp_pos={watch_pos}  thr={threshold}  →  {CONFIG}")
    elif key == ord("+") or key == ord("="):
        threshold += 10
        print(f"threshold → {threshold}")
    elif key == ord("-"):
        threshold = max(0, threshold - 10)
        print(f"threshold → {threshold}")

cv2.destroyAllWindows()
print("종료")
