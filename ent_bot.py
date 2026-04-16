from __future__ import annotations

import os
import time
import json
import keyboard
import cv2
import numpy as np
import win32gui
import easyocr
from typing import Optional, Tuple, List

# 기준 경로 (스크립트 위치 기준)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from capture_window import WindowCapture
from interception import move_to, mouse_down, mouse_up, auto_capture_devices, click, press, key_down, key_up, set_devices

# ──────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────
WINDOW      = "Lineage Classic"
CONFIG_PATH = os.path.join(BASE_DIR, "ent_config.json")

# OCR
NPC_NAME      = "엔트"          # 탐지할 NPC 이름
PICKUP_KEYWORD = "정령의돌"     # 바닥 드랍 아이템 키워드 (공백 제거 후 매칭)
PICKUP_EXCLUDE = ["판매", "관매", "전수", "마법", "마볍"]  # NPC 제외 (오독 포함)
PICKUP_CONF    = 0.4            # 드랍 아이템 최소 신뢰도
OCR_INTERVAL  = 0.5             # OCR 스캔 간격 (초)
try:
    import torch
    OCR_GPU = torch.cuda.is_available()
except Exception:
    OCR_GPU = False
OCR_SCAN_RECT = (10, 53, 1272, 696)  # OCR 스캔 영역 (x1,y1,x2,y2)

GRID_SPACING  = 120             # 웨이포인트 간격 (px)

# 엔트 미발견 복귀
NPC_NOT_FOUND_TIMEOUT = 300.0   # 5분간 엔트 못 찾으면 두루마리 복귀 (초)

# 두루마리 복귀
SCROLL_KEY    = "f10"           # 두루마리 열기 키
SCROLL_CLICK  = (49, 118)      # 요정 숲 클릭 좌표 (창 내)
SCROLL_WAIT   = 5.0            # 이동 대기 시간 (초)

# 무게 게이지
WEIGHT_POS    = (55, 866)       # 무게 게이지 체크 위치 (창 내)
WEIGHT_CHECK_INTERVAL = 30.0    # 무게 체크 간격 (초)

# 창고
WAREHOUSE_SCROLL_CLICK = (57, 122)  # 두루마리 → 요정 숲 (창고용)
WAREHOUSE_NPC_CLICK    = (854, 342) # 창고 지기 NPC
WAREHOUSE_DEPOSIT_CLICK = (92, 165) # 물건을 맡긴다
WAREHOUSE_OK_CLICK     = (288, 555) # OK 버튼
WAREHOUSE_ITEM_THRESHOLD = 0.7      # 아이템 템플릿 매칭 임계값

# 혈맹 창고
USE_CLAN_WAREHOUSE = False
CLAN_WAREHOUSE_SCROLL_CLICK  = (54, 282)
CLAN_WAREHOUSE_NPC_CLICK     = (714, 318)
CLAN_WAREHOUSE_DEPOSIT_CLICK = (65, 323)
CLAN_WAREHOUSE_OK_CLICK      = (288, 555)

# ent_config.json 로드
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"설정 파일 없음: {CONFIG_PATH}\n먼저 ent_setup.py를 실행해 설정을 저장하세요.")
with open(CONFIG_PATH, encoding="utf-8") as f:
    _cfg = json.load(f)

PATROL_ZONE = tuple(_cfg["patrol_zone"])

# 타이밍
MOVE_WAIT_SEC     = 3.5    # 이동 후 대기 (충분히 이동할 시간)
APPROACH_WAIT_SEC = 2.5    # NPC 접근 후 대화창 대기
DIALOG_WAIT_SEC   = 0.5    # 대화창 확인 후 ESC 전 대기
AFTER_ESC_SEC     = 0.3    # ESC 후 공격 전 대기
ATTACK_INTERVAL   = 0.3    # 재공격 간격
NPC_GONE_TIMEOUT  = 4.0    # NPC 사라짐 판정 타임아웃 (초)
SCAN_INTERVAL     = 0.08   # 순찰 중 탐지 간격

# 플레이어 기준점 (창 중앙 근처)
PLAYER_POS = (636, 340)

# 공격 성공 판정 (채팅 로그 "버섯포자의 즙이 부족합니다" 감지)
ATK_CHECK_DELAY = 0.5               # 공격 후 확인 대기 (초)
ATK_FAIL_THRESHOLD = 3              # 연속 공격 실패 횟수 → 이동
CHAT_ATK_THRESHOLD = 0.7            # 채팅 템플릿 매칭 임계값

# ──────────────────────────────────────────────────────
# 초기화
# ──────────────────────────────────────────────────────
print("디바이스 감지 중... (마우스 움직여주세요)")
auto_capture_devices(keyboard=True, mouse=True, verbose=True)

# 혈맹 창고 설정 로드
USE_CLAN_WAREHOUSE = _cfg.get("use_clan_warehouse", False)
if "clan_warehouse_scroll_click" in _cfg:
    CLAN_WAREHOUSE_SCROLL_CLICK = tuple(_cfg["clan_warehouse_scroll_click"])
if "clan_warehouse_npc_click" in _cfg:
    CLAN_WAREHOUSE_NPC_CLICK = tuple(_cfg["clan_warehouse_npc_click"])
if "clan_warehouse_deposit_click" in _cfg:
    CLAN_WAREHOUSE_DEPOSIT_CLICK = tuple(_cfg["clan_warehouse_deposit_click"])
if "clan_warehouse_ok_click" in _cfg:
    CLAN_WAREHOUSE_OK_CLICK = tuple(_cfg["clan_warehouse_ok_click"])

# ent_config.json에 keyboard_device / mouse_device 지정되어 있으면 강제 덮어쓰기
_kb_override = _cfg.get("keyboard_device")
_ms_override = _cfg.get("mouse_device")
if _kb_override is not None or _ms_override is not None:
    set_devices(keyboard=_kb_override, mouse=_ms_override)
    print(f"디바이스 오버라이드  KB={_kb_override}  Mouse={_ms_override}")

wincap = WindowCapture(WINDOW)
print(f"창 감지 완료  ({wincap.offset_x}, {wincap.offset_y})\n")

# OCR 로드
print("EasyOCR 로딩 중...")
reader = easyocr.Reader(['ko'], gpu=OCR_GPU)
print(f"EasyOCR 로딩 완료  GPU={OCR_GPU}")
last_ocr_t = 0.0
last_ocr_results = []  # 디버그: [(x1,y1,x2,y2,text,conf), ...]

# Close 버튼 템플릿 (대화창 감지용)
CLOSE_BTN_PATH = os.path.join(BASE_DIR, "templates", "close_btn.png")
CLOSE_THRESHOLD = 0.7
close_tmpl = cv2.imread(CLOSE_BTN_PATH, cv2.IMREAD_COLOR)
print(f"Close 버튼 템플릿 로딩 완료  {close_tmpl.shape[1]}x{close_tmpl.shape[0]}")

# Restart 버튼 템플릿 (사망 감지용)
RESTART_BTN_PATH = os.path.join(BASE_DIR, "templates", "restart_btn.png")
RESTART_THRESHOLD = 0.8
restart_tmpl = cv2.imread(RESTART_BTN_PATH, cv2.IMREAD_COLOR)
print(f"Restart 버튼 템플릿 로딩 완료  {restart_tmpl.shape[1]}x{restart_tmpl.shape[0]}")

# 아이템 템플릿 (창고 맡기기용)
FRUIT_TMPL_PATH = os.path.join(BASE_DIR, "templates", "ent_fruit.png")
STEM_TMPL_PATH  = os.path.join(BASE_DIR, "templates", "ent_stem.png")
fruit_tmpl = cv2.imread(FRUIT_TMPL_PATH, cv2.IMREAD_COLOR)
stem_tmpl  = cv2.imread(STEM_TMPL_PATH, cv2.IMREAD_COLOR)
print(f"아이템 템플릿 로딩: 열매={fruit_tmpl.shape[1]}x{fruit_tmpl.shape[0]}, 줄기={stem_tmpl.shape[1]}x{stem_tmpl.shape[0]}")

# 공격 성공 판정용 채팅 템플릿
CHAT_ATK_PATH = os.path.join(BASE_DIR, "templates", "chat_attack.png")
chat_atk_tmpl = cv2.imread(CHAT_ATK_PATH, cv2.IMREAD_COLOR)
print(f"채팅 공격 템플릿 로딩 완료  {chat_atk_tmpl.shape[1]}x{chat_atk_tmpl.shape[0]}")

# 부활 실패 감지용 채팅 템플릿 ("오랫동안 부활하지 않아")
CHAT_REVIVE_PATH = os.path.join(BASE_DIR, "templates", "chat_revive.png")
chat_revive_tmpl = cv2.imread(CHAT_REVIVE_PATH, cv2.IMREAD_COLOR)
if chat_revive_tmpl is not None:
    print(f"채팅 부활 템플릿 로딩 완료  {chat_revive_tmpl.shape[1]}x{chat_revive_tmpl.shape[0]}")
else:
    print(f"채팅 부활 템플릿 없음 (선택사항)")

# ──────────────────────────────────────────────────────
# 8방향 순찰
# ──────────────────────────────────────────────────────
import random

PATROL_DIST   = 500  # 좌우/하단 클릭 거리 (px) — 화면 끝까지
PATROL_DIST_UP = 200  # 상단 방향 클릭 거리 (px) — UI 영역 회피

# 8방향: 우, 우하, 하, 좌하, 좌, 좌상, 상, 우상
DIRECTIONS = [
    ( 1,  0), ( 1,  1), ( 0,  1), (-1,  1),
    (-1,  0), (-1, -1), ( 0, -1), ( 1, -1),
]
dir_idx = random.randint(0, 7)
patrol_steps = 0        # 같은 방향으로 이동한 횟수
MAX_PATROL_STEPS = 5    # 이 횟수만큼 이동 후 방향 전환 (더 멀리 직진)
print(f"8방향 순찰  거리={PATROL_DIST}px  방향전환={MAX_PATROL_STEPS}회  시작방향={DIR_NAMES[dir_idx]}")

last_npc_found_t = time.time()  # 마지막 엔트 발견 시간
last_weight_check_t = 0.0

# 갇힘 감지
patrol_history = []             # 최근 순찰 클릭 좌표 [(x,y), ...]
STUCK_HISTORY_SIZE = 10         # 최근 N회 기록
STUCK_RADIUS = 150              # 이 반경 이내에 모여있으면 갇힘 (px)
STUCK_CHECK_INTERVAL = 60.0     # 갇힘 체크 최소 간격 (초)
STUCK_NO_MOVE_MAX = 8           # 연속 이동불가 N회 → 두루마리 복귀
last_stuck_check_t = 0.0
patrol_no_move_count = 0

def check_weight_red(frame) -> bool:
    """무게 게이지가 빨간색인지 체크"""
    global last_weight_check_t
    now = time.time()
    if now - last_weight_check_t < WEIGHT_CHECK_INTERVAL:
        return False
    last_weight_check_t = now
    wx, wy = WEIGHT_POS
    roi = frame[wy-5:wy+5, wx-5:wx+5]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 0] < 8) & (hsv[:, :, 1] > 150)
    ratio = np.sum(mask) / mask.size
    if ratio > 0.3:
        print(f"[WEIGHT] 무게 초과 감지! (빨강 비율={ratio:.2f})")
        return True
    return False


def find_item(frame, tmpl, name="item"):
    """템플릿 매칭으로 아이템 찾기 → 중앙 좌표 반환"""
    result = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= WAREHOUSE_ITEM_THRESHOLD:
        th, tw = tmpl.shape[:2]
        cx = max_loc[0] + tw // 2
        cy = max_loc[1] + th // 2
        print(f"    [{name}] 발견! score={max_val:.3f} pos=({cx},{cy})")
        return (cx, cy)
    print(f"    [{name}] 미발견 score={max_val:.3f}")
    return None


def type_number(num_str):
    """숫자 입력"""
    for ch in num_str:
        press(ch)
        time.sleep(0.05)


def type_location_cmd():
    """/위치 명령 입력 → 채팅 로그 밀어내기 (한글 직접 타이핑)"""
    press('enter')
    time.sleep(0.3)
    press('/')
    time.sleep(0.2)
    press('hangul')
    time.sleep(0.2)
    # 위 = ㅇ(d) + ㅜ(n) + ㅣ(l)
    press('d')
    time.sleep(0.05)
    press('n')
    time.sleep(0.05)
    press('l')
    time.sleep(0.1)
    # 치 = ㅊ(c) + ㅣ(l)
    press('c')
    time.sleep(0.05)
    press('l')
    time.sleep(0.2)
    press('hangul')
    time.sleep(0.1)
    press('enter')
    time.sleep(0.5)
    print(f"[CHAT] /위치 입력 완료")


def check_chat_attack(frame) -> bool:
    """채팅 영역에서 '버섯포자의 즙이 부족합니다' 템플릿 감지"""
    x1, y1, x2, y2 = CHAT_RECT
    chat_roi = frame[y1:y2, x1:x2]
    if chat_roi.size == 0 or chat_atk_tmpl is None:
        return False
    if chat_roi.shape[0] < chat_atk_tmpl.shape[0] or chat_roi.shape[1] < chat_atk_tmpl.shape[1]:
        return False
    result = cv2.matchTemplate(chat_roi, chat_atk_tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return max_val >= CHAT_ATK_THRESHOLD


def deposit_items():
    """공통: 엔트의 열매/줄기 찾아서 맡기기"""
    frame = wincap.get_screenshot()
    fruit_pos = find_item(frame, fruit_tmpl, "엔트의 열매")
    if fruit_pos:
        click_move(fruit_pos)
        time.sleep(0.5)
        type_number("9999")
        time.sleep(0.3)

    frame = wincap.get_screenshot()
    stem_pos = find_item(frame, stem_tmpl, "엔트의 줄기")
    if stem_pos:
        click_move(stem_pos)
        time.sleep(0.5)
        type_number("9999")
        time.sleep(0.3)


def run_warehouse():
    """창고 루틴: 설정에 따라 개인/혈맹 창고 분기"""
    if USE_CLAN_WAREHOUSE:
        run_clan_warehouse()
    else:
        run_personal_warehouse()


def run_personal_warehouse():
    """개인 창고 루틴"""
    print(f"[WAREHOUSE] 개인 창고 루틴 시작")

    key_down(SCROLL_KEY)
    time.sleep(0.1)
    key_up(SCROLL_KEY)
    time.sleep(1.0)

    for _ in range(30):
        chk = wincap.get_screenshot()
        if is_dialog_open(chk):
            break
        time.sleep(0.1)
    time.sleep(0.3)

    click_move(WAREHOUSE_SCROLL_CLICK)
    print(f"[WAREHOUSE] 두루마리 클릭  pos={WAREHOUSE_SCROLL_CLICK}")
    time.sleep(SCROLL_WAIT)

    chk = wincap.get_screenshot()
    if is_dialog_open(chk):
        key_down('esc')
        time.sleep(0.1)
        key_up('esc')
        time.sleep(0.5)

    click_move(WAREHOUSE_NPC_CLICK)
    print(f"[WAREHOUSE] 창고 지기 클릭  pos={WAREHOUSE_NPC_CLICK}")
    time.sleep(2.0)

    for _ in range(30):
        chk = wincap.get_screenshot()
        if is_dialog_open(chk):
            break
        time.sleep(0.1)
    time.sleep(0.3)

    click_move(WAREHOUSE_DEPOSIT_CLICK)
    print(f"[WAREHOUSE] 물건을 맡긴다  pos={WAREHOUSE_DEPOSIT_CLICK}")
    time.sleep(1.0)

    deposit_items()

    click_move(WAREHOUSE_OK_CLICK)
    print(f"[WAREHOUSE] OK 클릭  pos={WAREHOUSE_OK_CLICK}")
    time.sleep(1.0)
    print(f"[WAREHOUSE] 개인 창고 루틴 완료 → PATROL 재개")


def run_clan_warehouse():
    """혈맹 창고 루틴"""
    print(f"[CLAN_WH] 혈맹 창고 루틴 시작")

    key_down(SCROLL_KEY)
    time.sleep(0.1)
    key_up(SCROLL_KEY)
    time.sleep(1.0)

    for _ in range(30):
        chk = wincap.get_screenshot()
        if is_dialog_open(chk):
            break
        time.sleep(0.1)
    time.sleep(0.3)

    click_move(CLAN_WAREHOUSE_SCROLL_CLICK)
    print(f"[CLAN_WH] 두루마리 클릭  pos={CLAN_WAREHOUSE_SCROLL_CLICK}")
    time.sleep(SCROLL_WAIT)

    chk = wincap.get_screenshot()
    if is_dialog_open(chk):
        key_down('esc')
        time.sleep(0.1)
        key_up('esc')
        time.sleep(0.5)

    click_move(CLAN_WAREHOUSE_NPC_CLICK)
    print(f"[CLAN_WH] 혈맹 창고지기 클릭  pos={CLAN_WAREHOUSE_NPC_CLICK}")
    time.sleep(2.0)

    for _ in range(30):
        chk = wincap.get_screenshot()
        if is_dialog_open(chk):
            break
        time.sleep(0.1)
    time.sleep(0.3)

    click_move(CLAN_WAREHOUSE_DEPOSIT_CLICK)
    print(f"[CLAN_WH] 물건을 맡긴다  pos={CLAN_WAREHOUSE_DEPOSIT_CLICK}")
    time.sleep(1.0)

    deposit_items()

    click_move(CLAN_WAREHOUSE_OK_CLICK)
    print(f"[CLAN_WH] OK 클릭  pos={CLAN_WAREHOUSE_OK_CLICK}")
    time.sleep(1.0)

    # 사냥터로 복귀
    print(f"[CLAN_WH] 사냥터 복귀 시작")
    scroll_return()
    print(f"[CLAN_WH] 혈맹 창고 루틴 완료 → PATROL 재개")


def scroll_return():
    """두루마리로 요정 숲 복귀"""
    print(f"[RETURN] 두루마리로 복귀 시작")
    key_down(SCROLL_KEY)
    time.sleep(0.1)
    key_up(SCROLL_KEY)
    time.sleep(1.0)
    for _ in range(30):
        chk = wincap.get_screenshot()
        if is_dialog_open(chk):
            break
        time.sleep(0.1)
    time.sleep(0.3)
    click_move(SCROLL_CLICK)
    print(f"[RETURN] 두루마리 클릭  pos={SCROLL_CLICK}")
    time.sleep(SCROLL_WAIT)
    chk = wincap.get_screenshot()
    if is_dialog_open(chk):
        key_down('esc')
        time.sleep(0.1)
        key_up('esc')
        time.sleep(0.5)
    print(f"[RETURN] 복귀 완료")
    post_return_move()

def post_return_move():
    """복귀 후 3방향(11시/1시/3시) 중 랜덤 하나로 20초 직진 + OCR 스캔
    장애물로 이동 불가 시 다른 방향으로 전환"""
    # 복귀 후 잔여 대화창 처리 + 안정화
    time.sleep(1.0)
    chk = wincap.get_screenshot()
    if chk is not None and is_dialog_open(chk):
        key_down('esc')
        time.sleep(0.1)
        key_up('esc')
        time.sleep(0.5)
        print(f"[RETURN] 잔여 대화창 ESC 처리")

    DIRS = [(-1, -1), (1, -1), (1, 0)]      # 11시, 1시, 3시
    NAMES = ["↖(11시)", "↗(1시)", "→(3시)"]
    order = list(range(3))
    random.shuffle(order)
    dir_idx = 0
    dx, dy = DIRS[order[dir_idx]]
    print(f"[RETURN] {NAMES[order[dir_idx]]} 방향 20초 무빙 시작")

    global npc_pos, last_npc_seen_t, last_npc_found_t, approach_dist0, approach_fail, state, state_enter_t
    global prev_player_roi

    stuck_count = 0
    end_time = time.time() + 20.0
    while time.time() < end_time:
        px, py = PLAYER_POS
        dist = PATROL_DIST
        tx = max(21, min(px + dx * dist, 1242))
        ty = max(30, min(py + dy * dist, 714))
        click_move((tx, ty))

        # 모션 감지 baseline
        prev_player_roi = None
        baseline = wincap.get_screenshot()
        if baseline is not None:
            is_player_moving(baseline)

        # 2초 이동 대기 + OCR 스캔
        moved = False
        wait_end = time.time() + 2.0
        while time.time() < wait_end:
            frame = wincap.get_screenshot()
            if frame is not None:
                npc, pickup = find_npc_ocr(frame)
                if pickup is not None:
                    print(f"[PICKUP] 정령의 돌 발견! 줍기  pos={pickup}")
                    click_move(pickup)
                    time.sleep(1.0)
                if npc is not None:
                    npc_pos = npc
                    last_npc_seen_t = time.time()
                    last_npc_found_t = time.time()
                    approach_dist0 = abs(npc[0] - PLAYER_POS[0]) + abs(npc[1] - PLAYER_POS[1])
                    approach_fail = 0
                    print(f"[RETURN] 무빙 중 엔트 발견! pos={npc} 거리={approach_dist0}")
                    click_move(npc_pos)
                    state = "APPROACH"
                    state_enter_t = time.time()
                    print(f"[STATE] → APPROACH")
                    return
                if is_player_moving(frame):
                    moved = True
            time.sleep(0.2)

        if moved:
            stuck_count = 0
        else:
            stuck_count += 1
            if stuck_count >= 2:
                # 장애물 → 다음 방향으로 전환
                dir_idx += 1
                if dir_idx >= len(order):
                    print(f"[RETURN] 모든 방향 막힘 → 무빙 종료")
                    break
                dx, dy = DIRS[order[dir_idx]]
                print(f"[RETURN] 장애물 감지 → {NAMES[order[dir_idx]]} 방향 전환")
                stuck_count = 0

    print(f"[RETURN] 20초 무빙 완료")

# ──────────────────────────────────────────────────────
# OCR NPC 탐지
def is_dialog_open(frame) -> bool:
    """Close 버튼 템플릿 매칭으로 대화창 열림 감지"""
    result = cv2.matchTemplate(frame, close_tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return max_val >= CLOSE_THRESHOLD

def is_dead(frame) -> bool:
    """Restart 버튼 템플릿 매칭으로 사망 감지"""
    result = cv2.matchTemplate(frame, restart_tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_val >= RESTART_THRESHOLD, max_loc

# 채팅 영역 (비교용)
CHAT_RECT = (220, 900, 520, 935)  # (x1, y1, x2, y2)
ATK_MSG_TIMEOUT = 10.0  # 이 시간 동안 새 부족 메시지 없으면 자동공격 풀림

def get_chat_snapshot(frame):
    """채팅 영역만 크롭"""
    x1, y1, x2, y2 = CHAT_RECT
    return frame[y1:y2, x1:x2].copy()

def chat_changed(before, after, threshold=5000) -> bool:
    """채팅 영역이 변했는지 (새 메시지 발생 여부)"""
    if before is None:
        return False
    diff = cv2.absdiff(before, after)
    return int(np.sum(diff)) > threshold

MOTION_SIZE = 30         # 캐릭터 주변 감지 영역 (±px)
MOTION_THRESHOLD = 10.0  # 이 이상이면 공격/이동 중
prev_player_roi = None

def is_player_moving(frame) -> bool:
    """캐릭터 주변 픽셀 변화로 공격/이동 중인지 판단"""
    global prev_player_roi
    px, py = PLAYER_POS
    x1 = max(0, px - MOTION_SIZE)
    y1 = max(0, py - MOTION_SIZE)
    x2 = min(frame.shape[1], px + MOTION_SIZE)
    y2 = min(frame.shape[0], py + MOTION_SIZE)
    roi = frame[y1:y2, x1:x2]

    if prev_player_roi is not None and roi.shape == prev_player_roi.shape:
        diff = cv2.absdiff(roi, prev_player_roi)
        diff_mean = float(np.mean(diff))
        prev_player_roi = roi.copy()
        return diff_mean > MOTION_THRESHOLD
    prev_player_roi = roi.copy()
    return False

# ──────────────────────────────────────────────────────
def find_npc_ocr(frame):
    """OCR 스캔 → (npc좌표, 드랍아이템좌표) 반환. 없으면 각각 None."""
    global last_ocr_t
    now = time.time()
    if now - last_ocr_t < OCR_INTERVAL:
        return None, None
    if now < ocr_pause_until:
        return None, None
    last_ocr_t = now

    # 빈 프레임 방어
    if frame is None or frame.size == 0:
        return None, None

    # 지정 영역만 크롭
    sx1, sy1, sx2, sy2 = OCR_SCAN_RECT
    game_frame = frame[sy1:sy2, sx1:sx2]
    if game_frame.size == 0:
        return None, None

    results = reader.readtext(game_frame, detail=1)
    # 디버그용: 모든 OCR 결과 저장
    last_ocr_results.clear()
    candidates = []
    pickup_pos = None
    for (bbox, text, conf) in results:
        x1 = int(bbox[0][0])
        y1 = int(bbox[0][1])
        x2 = int(bbox[2][0])
        y2 = int(bbox[2][1])
        last_ocr_results.append((x1 + sx1, y1 + sy1, x2 + sx1, y2 + sy1, text, conf))

        text_clean = text.strip().replace(" ", "")
        if NPC_NAME in text_clean:
            cx = (x1 + x2) // 2 + sx1
            cy = y2 + 45 + sy1
            candidates.append((cx, cy, conf))

        # 드랍 아이템 감지 (NPC 제외)
        if "정령" in text_clean and not any(ex in text_clean for ex in PICKUP_EXCLUDE) and conf >= PICKUP_CONF and pickup_pos is None:
            cx = (x1 + x2) // 2 + sx1
            cy = (y1 + y2) // 2 + sy1
            pickup_pos = (cx, cy)
            print(f"[PICKUP] '{text}' conf={conf:.2f} → ({cx},{cy})")

    npc_found = None
    if candidates:
        # 현재 타겟이 있으면 가장 가까운 엔트 선택 (타겟 고정)
        if npc_pos is not None:
            candidates.sort(key=lambda c: abs(c[0] - npc_pos[0]) + abs(c[1] - npc_pos[1]))
        else:
            # 타겟 없으면 플레이어에 가장 가까운 엔트
            candidates.sort(key=lambda c: abs(c[0] - PLAYER_POS[0]) + abs(c[1] - PLAYER_POS[1]))
        cx, cy, conf = candidates[0]
        print(f"[OCR] '{NPC_NAME}' conf={conf:.2f} → ({cx},{cy})  [{len(candidates)}마리]")
        npc_found = (cx, cy)

    return npc_found, pickup_pos

# ──────────────────────────────────────────────────────
# 동작
# ──────────────────────────────────────────────────────
def click_move(win_pos: Tuple[int,int]):
    """창 내 좌표 클릭 → 이동"""
    sx, sy = wincap.get_screen_position(win_pos)
    move_to(sx, sy)
    time.sleep(0.05)
    mouse_down("left")
    time.sleep(0.03)
    mouse_up("left")

DRAG_DIST = 80  # 공격 드래그 거리 (px)

def ctrl_drag_attack(win_pos: Tuple[int,int]):
    """Ctrl+좌클릭 유지+5시 방향 느린 드래그 → 자동공격 시작"""
    sx, sy = wincap.get_screen_position(win_pos)
    dx = int(DRAG_DIST * 0.5)
    dy = int(DRAG_DIST * 0.87)
    move_to(sx, sy)
    time.sleep(0.3)
    key_down('ctrl')
    time.sleep(0.3)
    mouse_down("left")
    time.sleep(0.3)
    # 드래그 (5스텝, 총 0.1초)
    steps = 5
    for i in range(1, steps + 1):
        move_to(sx + int(dx * i / steps), sy + int(dy * i / steps))
        time.sleep(0.02)
    time.sleep(0.3)
    mouse_up("left")
    time.sleep(0.2)
    key_up('ctrl')

# ──────────────────────────────────────────────────────
# 키 처리
# ──────────────────────────────────────────────────────
paused  = False
running = True

def emergency_exit():
    key_up('ctrl')
    mouse_up("left")
    print("\n[F12] 긴급 종료")
    os._exit(0)

def on_key(e):
    global paused, running
    if e.name == 'q': running = False
    if e.name == 'p':
        paused = not paused
        print("일시정지" if paused else "재개")

keyboard.on_press(on_key)
keyboard.add_hotkey('f12', emergency_exit)

def flee_and_patrol():
    """포기 후 랜덤 방향 이동 → 같은 엔트 재발견 방지"""
    dx, dy = random.choice(DIRECTIONS)
    dist = random.randint(300, PATROL_DIST)
    tx = PLAYER_POS[0] + dx * dist
    ty = PLAYER_POS[1] + dy * dist
    tx = max(21, min(tx, 1242))
    ty = max(30, min(ty, 714))
    d_name = ["→","↘","↓","↙","←","↖","↑","↗"][DIRECTIONS.index((dx,dy))]
    print(f"[FLEE] 포기 → {d_name} 이동 dist={dist} pos=({tx},{ty})")
    click_move((tx, ty))
    time.sleep(2.0)

# ──────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────
state           = "PATROL"
wp_idx          = 0
npc_pos         = None   # 창 내 NPC 좌표
state_enter_t   = time.time()
last_attack_t   = 0.0
last_npc_seen_t = 0.0
atk_fail_count  = 0      # 연속 공격 실패 카운터
reattack_fail   = 0      # 연속 재공격 실패 (끼임 판정용)
REATTACK_FAIL_MAX = 3    # 이 횟수 초과 → 100px 이동 후 재시도
escape_retry    = 0      # 이탈 대화 연속 시도 횟수
ESCAPE_RETRY_MAX = 3     # 이 횟수 초과 → 끼임 탈출
atk_confirmed   = False  # 채팅 기반 공격 성공 확인
fight_npc_pos   = None   # 공격 시작 시 엔트 위치 (이동 감지용)
ATK_CONFIRM_TIMEOUT = 1.5  # 공격 후 이 시간 안에 버섯포자 미감지 → 실패
approach_fail   = 0      # 접근 실패 카운터 (길막 판정)
APPROACH_FAIL_MAX = 3    # 이 횟수 초과 → 포기
approach_dist0  = None   # 접근 시작 시 NPC↔PLAYER 거리
CLOSE_ENOUGH    = 80     # 이 거리 이내면 공격 사거리 (px)
last_atk_msg_y  = None   # 마지막 부족 메시지 y위치
last_atk_msg_t  = 0.0    # 마지막 부족 메시지 감지 시간
ocr_pause_until = 0.0    # 이 시간까지 OCR 일시정지

cv2.namedWindow("ent_bot", cv2.WINDOW_NORMAL)
cv2.resizeWindow("ent_bot", 800, 600)
print("시작  P=일시정지  Q=종료  F12=긴급종료\n")

def set_state(s: str):
    global state, state_enter_t
    state = s
    state_enter_t = time.time()
    print(f"[STATE] → {s}")

while running:
    frame = wincap.get_screenshot()
    if frame is None or frame.size == 0:
        time.sleep(0.1)
        continue

    if paused:
        cv2.waitKey(100)
        continue

    now = time.time()
    elapsed = now - state_enter_t

    # ── 사망 감지 → Restart 클릭 ────────────────────
    dead, restart_loc = is_dead(frame)
    if dead:
        rh, rw = restart_tmpl.shape[:2]
        rx = restart_loc[0] + rw // 2
        ry = restart_loc[1] + rh // 2
        sx, sy = wincap.get_screen_position((rx, ry))
        move_to(sx, sy)
        time.sleep(0.1)
        mouse_down("left")
        time.sleep(0.03)
        mouse_up("left")
        print(f"[DEAD] 사망 감지 → Restart 클릭  ({rx},{ry})")
        time.sleep(5.0)  # 부활 대기 (넉넉히)
        npc_pos = None
        print(f"[DEAD] 부활 완료 → 창고 루틴 (두루마리 이동 + 물건 맡기기)")
        run_warehouse()
        last_npc_found_t = time.time()
        last_weight_check_t = time.time()
        set_state("PATROL")
        continue

    # ── "오랫동안 부활하지 않아" 감지 → Restart 재시도 ──
    if chat_revive_tmpl is not None:
        x1, y1, x2, y2 = CHAT_RECT
        chat_roi = frame[y1:y2, x1:x2]
        if chat_roi.size > 0 and chat_roi.shape[0] >= chat_revive_tmpl.shape[0] and chat_roi.shape[1] >= chat_revive_tmpl.shape[1]:
            rev_result = cv2.matchTemplate(chat_roi, chat_revive_tmpl, cv2.TM_CCOEFF_NORMED)
            _, rev_score, _, _ = cv2.minMaxLoc(rev_result)
            if rev_score >= 0.7:
                print(f"[DEAD] '오랫동안 부활하지 않아' 감지! score={rev_score:.3f} → Ctrl+Q")
                key_down('ctrl')
                time.sleep(0.3)
                press('q')
                time.sleep(0.3)
                key_up('ctrl')
                time.sleep(2.0)
                # Restart 버튼 대기 → 클릭
                for _ in range(30):
                    chk = wincap.get_screenshot()
                    dead2, restart_loc2 = is_dead(chk)
                    if dead2:
                        rh, rw = restart_tmpl.shape[:2]
                        rx = restart_loc2[0] + rw // 2
                        ry = restart_loc2[1] + rh // 2
                        click_move((rx, ry))
                        print(f"[DEAD] Restart 클릭  ({rx},{ry})")
                        break
                    time.sleep(0.1)
                time.sleep(5.0)
                # /위치로 부활 메시지 밀어내기 (중복 감지 방지)
                type_location_cmd()
                npc_pos = None
                run_warehouse()
                last_npc_found_t = time.time()
                last_weight_check_t = time.time()
                set_state("PATROL")
                continue

    # ── 대화창 감지 → 즉시 ESC (APPROACH 제외) ──────
    if state != "APPROACH":
        dlg_result = cv2.matchTemplate(frame, close_tmpl, cv2.TM_CCOEFF_NORMED)
        _, dlg_score, _, _ = cv2.minMaxLoc(dlg_result)
        if dlg_score >= CLOSE_THRESHOLD:
            # "오랫동안 부활" 체크 (대화창 전체 프레임에서)
            if chat_revive_tmpl is not None:
                rev_r = cv2.matchTemplate(frame, chat_revive_tmpl, cv2.TM_CCOEFF_NORMED)
                _, rev_s, _, _ = cv2.minMaxLoc(rev_r)
                print(f"[DEBUG] 부활 템플릿 score={rev_s:.3f}")
                if rev_s >= 0.7:
                    print(f"[DEAD] '오랫동안 부활하지 않아' 감지! score={rev_s:.3f} → ESC → Ctrl+Q")
                    # 먼저 대화창 닫기
                    key_down('esc')
                    time.sleep(0.3)
                    key_up('esc')
                    time.sleep(1.0)
                    # Ctrl+Q (press 방식)
                    key_down('ctrl')
                    time.sleep(0.3)
                    press('q')
                    time.sleep(0.3)
                    key_up('ctrl')
                    time.sleep(2.0)
                    for _ in range(30):
                        chk = wincap.get_screenshot()
                        dead2, restart_loc2 = is_dead(chk)
                        if dead2:
                            rh, rw = restart_tmpl.shape[:2]
                            rx = restart_loc2[0] + rw // 2
                            ry = restart_loc2[1] + rh // 2
                            click_move((rx, ry))
                            print(f"[DEAD] Restart 클릭  ({rx},{ry})")
                            break
                        time.sleep(0.1)
                    time.sleep(5.0)
                    type_location_cmd()
                    npc_pos = None
                    run_warehouse()
                    last_npc_found_t = time.time()
                    last_weight_check_t = time.time()
                    set_state("PATROL")
                    continue
            key_up('ctrl')
            mouse_up("left")
            time.sleep(0.05)
            key_down('esc')
            time.sleep(0.1)
            key_up('esc')
            print(f"[DIALOG] 대화창 감지 → ESC  score={dlg_score:.3f}")
            time.sleep(0.5)
            # ESC 후 현재 상태가 FIGHTING이면 재공격
            if state == "FIGHTING" and npc_pos is not None:
                npc, _ = find_npc_ocr(wincap.get_screenshot())
                if npc is not None:
                    npc_pos = npc
                ctrl_drag_attack(npc_pos)
                last_attack_t = time.time()
                last_atk_msg_t = time.time()
                print(f"[DIALOG] ESC 후 재공격  pos={npc_pos}")
            continue

    # ── 무게 초과 → 창고 루틴 ────────────────────────
    if state in ("PATROL", "FIGHTING") and check_weight_red(frame):
        run_warehouse()
        npc_pos = None
        last_weight_check_t = time.time()
        set_state("PATROL")
        continue

    # ── PATROL: 엔트 찾기 ──────────────────────────────
    if state == "PATROL":
        npc, pickup = find_npc_ocr(frame)
        if pickup is not None:
            print(f"[PICKUP] 정령의 돌 발견! 줍기  pos={pickup}")
            click_move(pickup)
            time.sleep(1.0)
        if npc is not None:
            # 1. 엔트 발견 → 대화 걸기 (일반 클릭)
            npc_pos = npc
            last_npc_seen_t = now
            last_npc_found_t = now
            approach_dist0 = abs(npc[0] - PLAYER_POS[0]) + abs(npc[1] - PLAYER_POS[1])
            approach_fail = 0
            print(f"[NPC 발견] 대화 클릭  pos={npc}  거리={approach_dist0}")
            click_move(npc_pos)
            set_state("APPROACH")
        else:
            if elapsed >= MOVE_WAIT_SEC:
                # 엔트 미발견 복귀 체크
                if now - last_npc_found_t >= NPC_NOT_FOUND_TIMEOUT:
                    print(f"[RETURN] {NPC_NOT_FOUND_TIMEOUT:.0f}초간 엔트 미발견 → 두루마리 복귀")
                    scroll_return()
                    npc_pos = None
                    last_npc_found_t = time.time()
                    state_enter_t = time.time()
                    continue

                # 갇힘 감지: 최근 순찰 위치가 좁은 범위에 몰려있으면 복귀
                if len(patrol_history) >= STUCK_HISTORY_SIZE and now - last_stuck_check_t >= STUCK_CHECK_INTERVAL:
                    last_stuck_check_t = now
                    xs = [p[0] for p in patrol_history]
                    ys = [p[1] for p in patrol_history]
                    spread = max(xs) - min(xs) + max(ys) - min(ys)
                    if spread < STUCK_RADIUS:
                        print(f"[STUCK] 갇힘 감지! 범위={spread}px → 두루마리 복귀")
                        scroll_return()
                        npc_pos = None
                        patrol_history.clear()
                        last_npc_found_t = time.time()
                        state_enter_t = time.time()
                        continue

                dx, dy = DIRECTIONS[dir_idx]
                dist = random.randint(150, PATROL_DIST) if dy >= 0 else random.randint(80, PATROL_DIST_UP)
                # 랜덤 오프셋: 같은 방향이라도 매번 다른 좌표 (캐릭터별 동선 분산)
                ox = random.randint(-80, 80)
                oy = random.randint(-50, 50)
                tx = PLAYER_POS[0] + dx * dist + ox
                ty = PLAYER_POS[1] + dy * dist + oy
                tx = max(21, min(tx, 1242))
                ty = max(30, min(ty, 714))
                click_move((tx, ty))
                patrol_history.append((tx, ty))
                if len(patrol_history) > STUCK_HISTORY_SIZE:
                    patrol_history.pop(0)
                patrol_steps += 1
                d_name = ["→","↘","↓","↙","←","↖","↑","↗"][dir_idx]
                print(f"[PATROL] {d_name} dist={dist} pos=({tx},{ty})  ({patrol_steps}/{MAX_PATROL_STEPS})")
                # 방향 전환 스텝도 랜덤 → 캐릭터마다 다른 타이밍에 전환
                steps_limit = random.randint(max(2, MAX_PATROL_STEPS - 2), MAX_PATROL_STEPS + 2)
                if patrol_steps >= steps_limit:
                    # 순차 모드에서도 가끔 방향 건너뛰기
                    skip = random.choice([1, 1, 1, 2])
                    dir_idx = (dir_idx + skip) % 8
                    patrol_steps = 0
                    print(f"[PATROL] 방향 전환 → {['→','↘','↓','↙','←','↖','↑','↗'][dir_idx]}")
                # 이동 완료 대기 (멈추면 바로 다음, 최대 3.5초)
                move_start = time.time()
                time.sleep(0.5)  # 최소 대기
                # 모션 감지 기준 프레임 설정
                prev_player_roi = None
                _baseline = wincap.get_screenshot()
                is_player_moving(_baseline)  # prev_roi 저장용
                time.sleep(0.2)

                moved_at_all = False
                while time.time() - move_start < MOVE_WAIT_SEC:
                    chk = wincap.get_screenshot()
                    # 이동 중 엔트 발견 체크
                    npc_chk, pickup_chk = find_npc_ocr(chk)
                    if pickup_chk is not None:
                        print(f"[PICKUP] 정령의 돌 발견! 줍기  pos={pickup_chk}")
                        click_move(pickup_chk)
                        time.sleep(1.0)
                    if npc_chk is not None:
                        npc_pos = npc_chk
                        last_npc_seen_t = time.time()
                        last_npc_found_t = time.time()
                        print(f"[PATROL] 이동 중 엔트 발견!  pos={npc_chk}")
                        click_move(npc_pos)
                        patrol_no_move_count = 0
                        set_state("APPROACH")
                        break
                    if is_player_moving(chk):
                        moved_at_all = True
                    else:
                        break
                    time.sleep(0.1)

                # 이동 불가 연속 감지 → 갇힘 탈출
                if moved_at_all:
                    patrol_no_move_count = 0
                else:
                    patrol_no_move_count += 1
                    print(f"[PATROL] 이동 불가 ({patrol_no_move_count}/{STUCK_NO_MOVE_MAX})")
                    if patrol_no_move_count >= STUCK_NO_MOVE_MAX:
                        print(f"[STUCK] 연속 이동 불가 {patrol_no_move_count}회 → 두루마리 복귀")
                        scroll_return()
                        npc_pos = None
                        patrol_history.clear()
                        patrol_no_move_count = 0
                        last_npc_found_t = time.time()
                        state_enter_t = time.time()
                        continue
                state_enter_t = time.time()
            time.sleep(SCAN_INTERVAL)

    # ── APPROACH: 대화창 대기 → ESC → 공격 ─────────────
    elif state == "APPROACH":
        dlg_r = cv2.matchTemplate(frame, close_tmpl, cv2.TM_CCOEFF_NORMED)
        _, ds, _, _ = cv2.minMaxLoc(dlg_r)
        if ds >= CLOSE_THRESHOLD:
            key_down('esc')
            time.sleep(0.1)
            key_up('esc')
            print(f"[APPROACH] 대화창 → ESC  score={ds:.3f}")
            time.sleep(0.5)
            # ESC 후 Ctrl+드래그 공격
            npc, _ = find_npc_ocr(wincap.get_screenshot())
            if npc is not None:
                npc_pos = npc
            if npc_pos is not None:
                ctrl_drag_attack(npc_pos)
                last_attack_t = time.time()
                last_atk_msg_t = time.time()
                approach_fail = 0
                atk_confirmed = False
                # 이전 버섯포자 메시지 잔존 시 /위치로 클리어
                if check_chat_attack(wincap.get_screenshot()):
                    print(f"[APPROACH] 이전 버섯포자 잔존 → /위치 클리어")
                    type_location_cmd()
                    ctrl_drag_attack(npc_pos)
                    last_attack_t = time.time()
                    last_atk_msg_t = time.time()
                fight_npc_pos = npc_pos
                print(f"[APPROACH] Ctrl+드래그 공격  pos={npc_pos}")
                set_state("FIGHTING")
        elif elapsed >= APPROACH_WAIT_SEC:
            # 대화창 안 열림 → 거리 체크로 길막 판정
            npc, _ = find_npc_ocr(wincap.get_screenshot())
            if npc is not None:
                npc_pos = npc
            if npc_pos is not None:
                cur_dist = abs(npc_pos[0] - PLAYER_POS[0]) + abs(npc_pos[1] - PLAYER_POS[1])
                if cur_dist <= CLOSE_ENOUGH:
                    # 가까이 왔음 → 공격 시도
                    print(f"[APPROACH] 사거리 도달 거리={cur_dist}px → 공격")
                    set_state("ATTACK")
                elif approach_dist0 is not None and cur_dist >= approach_dist0 - 20:
                    # 거리가 안 줄었음 → 길막
                    approach_fail += 1
                    if approach_fail >= APPROACH_FAIL_MAX:
                        print(f"[APPROACH] 길막 {approach_fail}회 → 포기")
                        npc_pos = None
                        approach_fail = 0
                        flee_and_patrol()
                        set_state("PATROL")
                    else:
                        print(f"[APPROACH] 길막 감지! 거리={cur_dist}px (시작={approach_dist0}) → 재시도 ({approach_fail}/{APPROACH_FAIL_MAX})")
                        click_move(npc_pos)
                        state_enter_t = time.time()
                else:
                    # 거리 줄어드는 중 → 계속 접근
                    approach_dist0 = cur_dist
                    print(f"[APPROACH] 접근 중 거리={cur_dist}px → 재클릭")
                    click_move(npc_pos)
                    state_enter_t = time.time()
            else:
                print(f"[APPROACH] 대화창 안 열림 + 엔트 없음 → PATROL")
                set_state("PATROL")
        time.sleep(0.05)

    # ── ATTACK: 공격 시도 ─────────────────────────────
    elif state == "ATTACK":
        npc, pickup = find_npc_ocr(frame)
        if pickup is not None:
            print(f"[PICKUP] 정령의 돌 발견! 줍기  pos={pickup}")
            click_move(pickup)
            time.sleep(1.0)
        if npc is not None:
            npc_pos = npc
            last_npc_seen_t = now

        if npc_pos is not None and now - last_attack_t >= ATTACK_INTERVAL:
            ctrl_drag_attack(npc_pos)
            last_attack_t = time.time()
            last_atk_msg_t = time.time()
            last_npc_seen_t = time.time()
            atk_confirmed = False
            # 이전 버섯포자 메시지 잔존 시 /위치로 클리어
            if check_chat_attack(wincap.get_screenshot()):
                print(f"[ATK] 이전 버섯포자 잔존 → /위치 클리어")
                type_location_cmd()
                ctrl_drag_attack(npc_pos)
                last_attack_t = time.time()
                last_atk_msg_t = time.time()
            fight_npc_pos = npc_pos
            print(f"[ATK] Ctrl+드래그  pos={npc_pos}")
            set_state("FIGHTING")
        else:
            gone_sec = now - last_npc_seen_t if last_npc_seen_t else elapsed
            if gone_sec >= NPC_GONE_TIMEOUT:
                print(f"[ATK] NPC 사라짐 → PATROL")
                npc_pos = None
                atk_fail_count = 0
                set_state("PATROL")
        time.sleep(0.05)

    # ── FIGHTING: 자동공격 대기 (엔트 죽을 때까지) ───────
    elif state == "FIGHTING":
        npc, pickup = find_npc_ocr(frame)
        if pickup is not None:
            print(f"[PICKUP] 정령의 돌 발견! 공격 중단 → 줍기  pos={pickup}")
            key_up('ctrl')
            mouse_up("left")
            time.sleep(0.3)
            click_move(pickup)
            time.sleep(2.0)
            # 주운 후 엔트 재공격
            if npc_pos is not None:
                print(f"[PICKUP] 줍기 완료 → 엔트 재공격")
                npc_new, _ = find_npc_ocr(wincap.get_screenshot())
                if npc_new is not None:
                    npc_pos = npc_new
                click_move(npc_pos)
                time.sleep(1.5)
                chk = wincap.get_screenshot()
                if is_dialog_open(chk):
                    key_down('esc')
                    time.sleep(0.1)
                    key_up('esc')
                    time.sleep(0.5)
                ctrl_drag_attack(npc_pos)
                last_attack_t = time.time()
                last_atk_msg_t = time.time()
            continue
        if npc is not None:
            last_npc_found_t = now
            npc_pos = npc
            last_npc_seen_t = now

        # 엔트 이탈 감지 → 재추적 (공격 시작 위치 대비 이동)
        if npc is not None and fight_npc_pos is not None:
            npc_moved = abs(npc[0] - fight_npc_pos[0]) + abs(npc[1] - fight_npc_pos[1])
            if npc_moved > 80:
                print(f"[FIGHTING] 엔트 이동! {npc_moved}px (시작={fight_npc_pos}) → 재공격")
                npc_new, _ = find_npc_ocr(wincap.get_screenshot())
                if npc_new is not None:
                    npc_pos = npc_new
                ctrl_drag_attack(npc_pos)
                fight_npc_pos = npc_pos
                last_attack_t = time.time()
                last_atk_msg_t = time.time()
                atk_confirmed = False
                continue

        # 채팅 템플릿 기반 공격 확인
        chat_active = check_chat_attack(frame)
        if not atk_confirmed:
            if chat_active:
                atk_confirmed = True
                last_atk_msg_t = now
                reattack_fail = 0
                escape_retry = 0
                print(f"[FIGHTING] 공격 확인 ✓ (버섯포자 감지)")
            elif now - last_atk_msg_t >= ATK_CONFIRM_TIMEOUT:
                # 공격 후 시간 내 버섯포자 미감지 → 공격 안 닿음
                reattack_fail += 1
                if reattack_fail > REATTACK_FAIL_MAX:
                    print(f"[FIGHTING] 공격 실패 {reattack_fail}회 → 포기")
                    npc_pos = None
                    reattack_fail = 0
                    flee_and_patrol()
                    set_state("PATROL")
                else:
                    # 8방향 랜덤 우회 후 재공격
                    _ATK_DIRS = ["↑","→","↓","←","↖","↗","↘","↙"]
                    _ATK_OFFSETS = [(0,-180),(180,0),(0,180),(-180,0),
                                   (-130,-130),(130,-130),(130,130),(-130,130)]
                    if npc_pos is not None:
                        moved = False
                        dirs_order = list(range(8))
                        random.shuffle(dirs_order)
                        for di in dirs_order:
                            ox, oy = _ATK_OFFSETS[di]
                            mx = max(21, min(npc_pos[0] + ox, 1242))
                            my = max(30, min(npc_pos[1] + oy, 714))
                            print(f"[FIGHTING] {_ATK_DIRS[di]} 우회 시도 ({mx},{my})  ({reattack_fail}/{REATTACK_FAIL_MAX})")
                            prev_player_roi = None
                            baseline = wincap.get_screenshot()
                            is_player_moving(baseline)
                            click_move((mx, my))
                            time.sleep(0.5)
                            echk = wincap.get_screenshot()
                            if is_player_moving(echk):
                                moved = True
                                print(f"[FIGHTING] {_ATK_DIRS[di]} 이동 성공 → 재공격")
                                time.sleep(0.3)
                                break
                            print(f"[FIGHTING] {_ATK_DIRS[di]} 이동 불가 → 다음 방향")
                        if not moved:
                            print(f"[FIGHTING] 모든 방향 이동 불가 → 두루마리 복귀")
                            scroll_return()
                            npc_pos = None
                            reattack_fail = 0
                            set_state("PATROL")
                            continue
                        ctrl_drag_attack(npc_pos)
                        fight_npc_pos = npc_pos
                        last_attack_t = time.time()
                        last_atk_msg_t = time.time()
        else:
            # 공격 확인된 상태 → 3초마다 /위치로 클리어 후 재확인
            if now - last_atk_msg_t >= 3.0:
                type_location_cmd()
                time.sleep(1.5)
                chk = wincap.get_screenshot()
                if check_chat_attack(chk):
                    last_atk_msg_t = time.time()
                    print(f"[FIGHTING] 공격 재확인 ✓")
                else:
                    # 버섯포자 안 뜸 → 자동공격 풀림
                    print(f"[FIGHTING] 자동공격 풀림 → 재공격")
                    if npc_pos is not None:
                        npc_new, _ = find_npc_ocr(wincap.get_screenshot())
                        if npc_new is not None:
                            npc_pos = npc_new
                        ctrl_drag_attack(npc_pos)
                        fight_npc_pos = npc_pos
                        last_attack_t = time.time()
                        last_atk_msg_t = time.time()
                        atk_confirmed = False
                    else:
                        print(f"[FIGHTING] 자동공격 풀림 + 엔트 없음 → PATROL")
                        set_state("PATROL")

        # 엔트 이름 사라짐 → 사망 → /위치 입력
        gone_sec = now - last_npc_seen_t if last_npc_seen_t else elapsed
        if gone_sec >= NPC_GONE_TIMEOUT:
            print(f"[FIGHTING] 엔트 사라짐 → 사망")
            type_location_cmd()
            npc_pos = None
            atk_fail_count = 0
            atk_confirmed = False
            set_state("PATROL")
        time.sleep(0.1)

    # ── 디버그 (3프레임에 1번 업데이트) ──────────────
    if not hasattr(set_state, '_dbg_cnt'):
        set_state._dbg_cnt = 0
    set_state._dbg_cnt += 1
    if set_state._dbg_cnt % 3 == 0:
        dbg = frame.copy()
        if npc_pos:
            cv2.circle(dbg, npc_pos, 10, (0,0,255), 2)
        cv2.circle(dbg, PLAYER_POS, 8, (255,100,0), 2)
        cv2.putText(dbg, f"{state}", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)
        cv2.imshow("ent_bot", dbg)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        running = False

key_up('ctrl')
mouse_up("left")
cv2.destroyAllWindows()
print("종료")
