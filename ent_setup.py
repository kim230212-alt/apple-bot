"""
ent_bot.py 설정 도구
────────────────────
[Z] 순찰 구역 설정  : 드래그로 영역 지정
[X] NPC 템플릿 저장 : 드래그로 NPC 잘라내기
[C] 대화창 템플릿   : 드래그로 대화창 잘라내기 (선택)
[S] 설정 저장
[Q] 종료
"""

import os
import cv2
import json
import numpy as np
from capture_window import WindowCapture

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
WINDOW       = "Lineage Classic"
SAVE_DIR     = os.path.join(BASE_DIR, "templates")
CONFIG_PATH  = os.path.join(BASE_DIR, "ent_config.json")

os.makedirs(SAVE_DIR, exist_ok=True)

wincap = WindowCapture(WINDOW)

# ── 상태 ──────────────────────────────────────────────
mode         = "ZONE"     # ZONE / NPC / DIALOG
drag_start   = None
drag_end     = None
dragging     = False

patrol_zone  = None       # (x1,y1,x2,y2)
npc_saved    = False
dialog_saved = False

frame_buf    = None       # 마우스 콜백에서 참조

# ── 마우스 콜백 ───────────────────────────────────────
def on_mouse(event, x, y, flags, param):
    global drag_start, drag_end, dragging
    global patrol_zone, npc_saved, dialog_saved

    if event == cv2.EVENT_LBUTTONDOWN:
        drag_start = (x, y)
        drag_end   = (x, y)
        dragging   = True

    elif event == cv2.EVENT_MOUSEMOVE and dragging:
        drag_end = (x, y)

    elif event == cv2.EVENT_LBUTTONUP and dragging:
        dragging = False
        drag_end = (x, y)

        x1 = min(drag_start[0], drag_end[0])
        y1 = min(drag_start[1], drag_end[1])
        x2 = max(drag_start[0], drag_end[0])
        y2 = max(drag_start[1], drag_end[1])

        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            return  # 너무 작은 드래그 무시

        if mode == "ZONE":
            patrol_zone = (x1, y1, x2, y2)
            print(f"[구역] PATROL_ZONE = {patrol_zone}")

        elif mode == "NPC":
            if frame_buf is not None:
                crop = frame_buf[y1:y2, x1:x2]
                path = os.path.join(SAVE_DIR, "ent_npc.png")
                cv2.imwrite(path, crop)
                npc_saved = True
                print(f"[NPC 템플릿] 저장 완료 → {path}  ({x2-x1}x{y2-y1})")

        elif mode == "DIALOG":
            if frame_buf is not None:
                crop = frame_buf[y1:y2, x1:x2]
                path = os.path.join(SAVE_DIR, "ent_dialog.png")
                cv2.imwrite(path, crop)
                dialog_saved = True
                print(f"[대화창 템플릿] 저장 완료 → {path}  ({x2-x1}x{y2-y1})")

        drag_start = drag_end = None

# ── 창 설정 ───────────────────────────────────────────
WIN_NAME = "ent_setup"
cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WIN_NAME, 900, 650)
cv2.setMouseCallback(WIN_NAME, on_mouse)

MODE_COLOR = {"ZONE": (100,200,255), "NPC": (0,255,100), "DIALOG": (255,180,0)}
MODE_LABEL = {"ZONE": "Z: 순찰구역", "NPC": "X: NPC 템플릿", "DIALOG": "C: 대화창 템플릿"}

print(__doc__)
print("창이 열리면 드래그로 영역/템플릿을 지정하세요.\n")

while True:
    frame      = wincap.get_screenshot()
    frame_buf  = frame.copy()
    dbg        = frame.copy()

    # 순찰 구역 표시
    if patrol_zone:
        x1,y1,x2,y2 = patrol_zone
        cv2.rectangle(dbg, (x1,y1), (x2,y2), (100,100,255), 2)
        cv2.putText(dbg, "PATROL ZONE", (x1+4, y1+18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100,100,255), 1)

    # 드래그 중 사각형
    if dragging and drag_start and drag_end:
        x1 = min(drag_start[0], drag_end[0])
        y1 = min(drag_start[1], drag_end[1])
        x2 = max(drag_start[0], drag_end[0])
        y2 = max(drag_start[1], drag_end[1])
        color = MODE_COLOR[mode]
        cv2.rectangle(dbg, (x1,y1), (x2,y2), color, 2)

    # HUD
    color = MODE_COLOR[mode]
    cv2.rectangle(dbg, (0,0), (dbg.shape[1], 30), (30,30,30), -1)
    cv2.putText(dbg, f"모드: {MODE_LABEL[mode]}  |  Z/X/C=모드변경  S=저장  Q=종료",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)

    # 저장 상태
    status = []
    if patrol_zone:  status.append("구역OK")
    if npc_saved:    status.append("NPC OK")
    if dialog_saved: status.append("대화창OK")
    if status:
        cv2.putText(dbg, "  ".join(status), (8, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,180), 1)

    cv2.imshow(WIN_NAME, dbg)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break
    elif key == ord('z'):
        mode = "ZONE";   print("[모드] 순찰 구역 설정 - 드래그")
    elif key == ord('x'):
        mode = "NPC";    print("[모드] NPC 템플릿 - NPC 위에 드래그")
    elif key == ord('c'):
        mode = "DIALOG"; print("[모드] 대화창 템플릿 - 대화창 위에 드래그")
    elif key == ord('s'):
        if not patrol_zone:
            print("[경고] 순찰 구역을 먼저 설정하세요 (Z키)")
        elif not npc_saved:
            print("[경고] NPC 템플릿을 먼저 저장하세요 (X키)")
        else:
            cfg = {
                "patrol_zone": list(patrol_zone),
                "npc_template": os.path.join(SAVE_DIR, "ent_npc.png"),
                "dialog_template": os.path.join(SAVE_DIR, "ent_dialog.png") if dialog_saved else None,
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(f"\n[저장 완료] {CONFIG_PATH}")
            print(f"  patrol_zone = {patrol_zone}")
            print(f"  npc_template = {cfg['npc_template']}")
            print(f"  dialog_template = {cfg['dialog_template']}")
            print("\nent_bot.py의 PATROL_ZONE 값을 위 값으로 수정하거나,")
            print("ent_config.json을 자동으로 읽도록 설정할 수 있습니다.\n")

cv2.destroyAllWindows()
print("종료")
