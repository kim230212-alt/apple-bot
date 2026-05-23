"""창고지기 NPC 클릭 + 대화창 열림 감지 단독 테스트

실행:
  python test_wh_npc_dialog.py
  python test_wh_npc_dialog.py ent_config2.json

조작:
  Enter → NPC 클릭 + 대화창 감지 실행
  Q     → 종료
"""

import sys, os, time, json
import cv2
import numpy as np

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG    = sys.argv[1] if len(sys.argv) > 1 else "ent_config.json"
TMPL_DIR  = os.path.join(BASE_DIR, "templates")

sys.path.insert(0, BASE_DIR)
from capture_window import WindowCapture
from interception import (
    auto_capture_devices, set_devices,
    move_to, mouse_down, mouse_up,
)

# ── config 로드 ──────────────────────────────────────────
with open(os.path.join(BASE_DIR, CONFIG), "r", encoding="utf-8") as f:
    cfg_raw = json.load(f)

win_title   = cfg_raw.get("window_title", "Lineage Classic")
win_idx     = int(cfg_raw.get("window_index", 0))
kb_dev      = int(cfg_raw.get("keyboard_device", 0))
ms_dev      = int(cfg_raw.get("mouse_device", -1))
npc_click   = tuple(cfg_raw.get("warehouse_npc_click", [854, 342]))
player_pos  = tuple(cfg_raw.get("player_pos", [640, 400]))

# ── 디바이스 초기화 ──────────────────────────────────────
auto_capture_devices(keyboard=True, mouse=True, verbose=False)
if ms_dev >= 0:
    set_devices(keyboard=kb_dev, mouse=ms_dev)
else:
    set_devices(keyboard=kb_dev)

wincap = WindowCapture(win_title, window_index=win_idx)
print(f"창: '{win_title}'[{win_idx}]  {wincap.w}x{wincap.h}")

# ── 템플릿 로드 ──────────────────────────────────────────
def _load(name):
    p = os.path.join(TMPL_DIR, name)
    t = cv2.imread(p)
    if t is None:
        print(f"[WARN] 템플릿 없음: {p}")
    return t

def _load_gray(name):
    t = _load(name)
    return cv2.cvtColor(t, cv2.COLOR_BGR2GRAY) if t is not None else None

close_tmpl   = _load("close_btn.png")
keeper_tmpl  = _load_gray("warehouse_keeper.png")
keeper_name  = _load("keeper_name.png") if os.path.exists(os.path.join(TMPL_DIR, "keeper_name.png")) else None

print(f"close_btn : {'OK' if close_tmpl is not None else 'MISSING'}")
print(f"warehouse_keeper : {'OK (gray)' if keeper_tmpl is not None else 'MISSING'}")
print(f"keeper_name : {'OK (color)' if keeper_name is not None else '없음 (gray fallback)'}")
print(f"NPC 고정좌표: {npc_click}  |  player_pos: {player_pos}")
print()

def click(win_pos):
    sx, sy = wincap.get_screen_position(win_pos)
    move_to(sx, sy)
    time.sleep(0.1)
    mouse_down("left"); time.sleep(0.05); mouse_up("left")

def is_dialog_open(frame) -> float:
    if close_tmpl is None:
        return 0.0
    res = cv2.matchTemplate(frame, close_tmpl, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(res)[1])

def click_npc() -> str:
    """NPC 클릭. 반환값: 'template' / 'fixed'"""
    # 마우스 대피 후 캡처
    sx, sy = wincap.get_screen_position(player_pos)
    move_to(sx, sy); time.sleep(0.2)
    frame = wincap.get_screenshot()
    if frame is None:
        print("[NPC] 캡처 실패 → 고정 좌표 사용")
        click(npc_click)
        return "fixed"

    # 컬러 템플릿 우선
    if keeper_name is not None:
        src, cmp, thr = frame, keeper_name, 0.75
    elif keeper_tmpl is not None:
        src = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cmp, thr = keeper_tmpl, 0.45
    else:
        print("[NPC] 템플릿 없음 → 고정 좌표")
        click(npc_click)
        return "fixed"

    res = cv2.matchTemplate(src, cmp, cv2.TM_CCOEFF_NORMED)
    score, loc = cv2.minMaxLoc(res)[1], cv2.minMaxLoc(res)[3]
    th, tw = cmp.shape[:2]

    if score < thr:
        print(f"[NPC] 템플릿 매칭 실패 score={score:.3f} (thr={thr}) → 고정 좌표")
        click(npc_click)
        return "fixed"

    cx = loc[0] + tw // 2
    cy = loc[1] + th // 2 + 40
    print(f"[NPC] 템플릿 매칭 성공 score={score:.3f} → 클릭 ({cx},{cy})")
    click((cx, cy))
    return "template"

def run_test():
    print("\n── 테스트 시작 ──")

    # NPC 클릭
    mode = click_npc()
    print(f"[NPC] 클릭 완료 (mode={mode}) → 대화창 대기 중...")

    # 대화창 열림 대기 (최대 3초)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        frame = wincap.get_screenshot()
        if frame is None:
            time.sleep(0.1); continue
        score = is_dialog_open(frame)
        if score >= 0.7:
            print(f"[DIALOG] 열림 확인! close_btn score={score:.3f}")
            return
        time.sleep(0.1)

    # 실패 — 마지막 score 출력
    frame = wincap.get_screenshot()
    score = is_dialog_open(frame) if frame is not None else 0.0
    print(f"[DIALOG] 감지 실패 — close_btn score={score:.3f} (thr=0.7)")
    print("  → NPC 클릭이 안 됐거나, close_btn.png 템플릿이 맞지 않을 수 있습니다.")

# ── 메인 루프 ────────────────────────────────────────────
print("Enter=테스트실행  Q=종료")
while True:
    cmd = input("> ").strip().lower()
    if cmd == "q":
        break
    run_test()

print("종료")
