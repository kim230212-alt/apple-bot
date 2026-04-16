"""
템플릿 캡쳐 도구
─────────────────
게임 화면에서 드래그로 각 템플릿을 캡쳐합니다.
키를 눌러 모드를 전환하세요.

1 = Close 버튼 (대화창 닫기)
2 = Restart 버튼 (사망 부활)
3 = 채팅 공격 메시지 (버섯포자의 즙이 부족합니다)
4 = 채팅 부활 메시지 (오랫동안 부활하지 않아)
S = 전체 저장 확인
Q = 종료
"""
import os
import cv2
from capture_window import WindowCapture

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMPL_DIR = os.path.join(BASE_DIR, "templates")
WINDOW = "Lineage Classic"

os.makedirs(TMPL_DIR, exist_ok=True)
wincap = WindowCapture(WINDOW)

MODES = {
    '1': ("close_btn.png",     "Close 버튼"),
    '2': ("restart_btn.png",   "Restart 버튼"),
    '3': ("chat_attack.png",   "채팅 공격 (버섯포자)"),
    '4': ("chat_revive.png",   "채팅 부활 (오랫동안)"),
}

mode = '1'
drag_start = None
drag_end = None
dragging = False
saved = {}

def on_mouse(event, x, y, flags, param):
    global drag_start, drag_end, dragging
    if event == cv2.EVENT_LBUTTONDOWN:
        drag_start = (x, y)
        drag_end = (x, y)
        dragging = True
    elif event == cv2.EVENT_MOUSEMOVE and dragging:
        drag_end = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and dragging:
        dragging = False
        drag_end = (x, y)
        x1 = min(drag_start[0], drag_end[0])
        y1 = min(drag_start[1], drag_end[1])
        x2 = max(drag_start[0], drag_end[0])
        y2 = max(drag_start[1], drag_end[1])
        if abs(x2 - x1) > 3 and abs(y2 - y1) > 3:
            fname, label = MODES[mode]
            path = os.path.join(TMPL_DIR, fname)
            crop = param[y1:y2, x1:x2]
            cv2.imwrite(path, crop)
            saved[mode] = True
            print(f"  [{label}] 저장 완료: {x2-x1}x{y2-y1}  위치=({x1},{y1}) ~ ({x2},{y2})")
            print(f"  → {path}\n")

cv2.namedWindow("capture", cv2.WINDOW_NORMAL)
cv2.resizeWindow("capture", 900, 650)

print(__doc__)
print(f"현재 모드: [1] {MODES['1'][1]}\n")

while True:
    frame = wincap.get_screenshot()
    if frame is None:
        cv2.waitKey(100)
        continue

    cv2.setMouseCallback("capture", on_mouse, frame)
    dbg = frame.copy()

    # HUD
    fname, label = MODES[mode]
    color = (0, 255, 0) if mode in saved else (0, 200, 255)
    cv2.rectangle(dbg, (0, 0), (dbg.shape[1], 32), (30, 30, 30), -1)
    cv2.putText(dbg, f"[{mode}] {label}  |  1/2/3/4=mode  S=check  Q=quit",
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # 드래그 중
    if dragging and drag_start and drag_end:
        x1 = min(drag_start[0], drag_end[0])
        y1 = min(drag_start[1], drag_end[1])
        x2 = max(drag_start[0], drag_end[0])
        y2 = max(drag_start[1], drag_end[1])
        cv2.rectangle(dbg, (x1, y1), (x2, y2), color, 2)

    # 저장 상태
    status_y = 50
    for k, (fn, lb) in MODES.items():
        mark = "OK" if k in saved else "--"
        cv2.putText(dbg, f"[{k}] {lb}: {mark}", (8, status_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0) if k in saved else (100, 100, 100), 1)
        status_y += 18

    cv2.imshow("capture", dbg)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break
    elif chr(key) in MODES:
        mode = chr(key)
        fname, label = MODES[mode]
        print(f"모드 변경 → [{mode}] {label}")
    elif key == ord('s'):
        print("\n=== 저장 상태 ===")
        for k, (fn, lb) in MODES.items():
            exists = os.path.exists(os.path.join(TMPL_DIR, fn))
            print(f"  [{k}] {lb}: {'OK' if exists else 'MISSING'} ({fn})")
        print()

cv2.destroyAllWindows()
print("종료")
