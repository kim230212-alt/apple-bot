"""
ent_bot 엔진 (템플릿 매칭 버전)
────────────────────────────────
PaddleOCR/EasyOCR 대신 cv2.matchTemplate() 사용.
별도 프로세스(multiprocessing)로 분리하여
GIL 경합 없이 키보드/마우스 입력이 즉시 반응하도록 함.
GPU/CPU 환경 동일 인식률, OCR 의존성 불필요.
"""
from __future__ import annotations

import os
import time
import random
import threading
import multiprocessing as mp
import glob
import cv2
import numpy as np

import win32gui
from typing import Optional, Tuple, Callable

from template_scanner import template_process_fn

from ent_bot_config import BotConfig
from capture_window import WindowCapture
from interception import (
    move_to, mouse_down, mouse_up, auto_capture_devices,
    click, press, key_down, key_up, set_devices,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 8방향
DIRECTIONS = [
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1),
]
DIR_NAMES = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"]


class BotEngine:
    """엔트 사냥 봇 엔진 — 템플릿 매칭 (OCR 불필요)"""

    def __init__(self, config: BotConfig, log_callback: Callable[[str], None]):
        self.cfg = config
        self.log = log_callback

        # 스레드 제어
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None

        # 공개 상태 (GUI에서 읽기)
        self.state = "IDLE"
        self.npc_pos: Optional[Tuple[int, int]] = None
        self.last_debug_frame = None

        # 내부 상태
        self._state_enter_t = 0.0
        self._last_scan_results = []
        self._last_npc_seen_t = 0.0
        self._last_npc_found_t = 0.0
        self._last_attack_t = 0.0
        self._last_weight_check_t = 0.0
        self._last_stuck_check_t = 0.0
        self._last_atk_msg_t = 0.0
        self._last_atk_msg_y = None
        self._atk_fail_count = 0
        self._reattack_fail = 0
        self._escape_retry = 0
        self._approach_fail = 0
        self._approach_dist0 = None
        self._atk_confirmed = False
        self._fight_npc_pos = None
        self._scan_pause_until = 0.0
        self._dir_idx = 0
        self._patrol_steps = 0
        self._patrol_history = []
        self._patrol_no_move_count = 0
        self._prev_player_roi = None
        self._dbg_cnt = 0

        # ── 스캐너 프로세스 (GIL 회피) ──
        self._scan_proc: Optional[mp.Process] = None
        self._scan_stop_evt: Optional[mp.Event] = None
        self._scan_frame_q: Optional[mp.Queue] = None
        self._scan_result_q: Optional[mp.Queue] = None
        self._scan_done = False

        # 리소스 (initialize에서 로드)
        self._wincap: Optional[WindowCapture] = None
        self._close_tmpl = None
        self._restart_tmpl = None
        self._fruit_tmpl = None
        self._stem_tmpl = None
        self._chat_atk_tmpl = None
        self._chat_revive_tmpl = None
        self._initialized = False

    # ──────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────
    def initialize(self):
        self.log("디바이스 감지 중... (마우스 움직여주세요)")
        auto_capture_devices(keyboard=True, mouse=True, verbose=True)

        kb = self.cfg.keyboard_device
        ms = self.cfg.mouse_device
        if kb is not None or ms is not None:
            set_devices(keyboard=kb, mouse=ms)
            self.log(f"디바이스 오버라이드  KB={kb}  Mouse={ms}")

        self._wincap = WindowCapture(self.cfg.window_title)
        self.log(f"창 감지 완료  ({self._wincap.offset_x}, {self._wincap.offset_y})")

        # 템플릿 확인
        tmpl_dir = os.path.join(BASE_DIR, "templates")
        n_npc = len(glob.glob(os.path.join(tmpl_dir, "npc_*.png")))
        n_pickup = len(glob.glob(os.path.join(tmpl_dir, "pickup_*.png")))
        if n_npc == 0:
            self.log("[경고] NPC 템플릿 없음! capture_npc_template.py로 캡처하세요")

        self.log(f"템플릿 스캐너 시작 중... (NPC={n_npc}, PICKUP={n_pickup})")
        self._scan_stop_evt = mp.Event()
        self._scan_frame_q = mp.Queue(maxsize=2)
        self._scan_result_q = mp.Queue(maxsize=10)
        ready_evt = mp.Event()
        self._scan_proc = mp.Process(
            target=template_process_fn,
            args=(self._scan_stop_evt, self._scan_frame_q,
                  self._scan_result_q, ready_evt),
            daemon=True,
        )
        self._scan_proc.start()
        if ready_evt.wait(timeout=30):
            self.log("템플릿 스캐너 로딩 완료 (별도 프로세스, GIL 회피)")
        else:
            self.log("[경고] 템플릿 스캐너 로딩 시간 초과")

        self._load_templates()
        self._initialized = True
        self.log("초기화 완료 (템플릿 매칭 — PaddleOCR/EasyOCR 불필요)")

    def _load_templates(self):
        def _load(name, required=True):
            path = os.path.join(BASE_DIR, "templates", name)
            tmpl = cv2.imread(path, cv2.IMREAD_COLOR)
            if tmpl is not None:
                self.log(f"  템플릿 로딩: {name}  {tmpl.shape[1]}x{tmpl.shape[0]}")
            elif required:
                self.log(f"  [경고] 템플릿 없음: {name}")
            return tmpl

        self._close_tmpl = _load("close_btn.png")
        self._restart_tmpl = _load("restart_btn.png")
        self._fruit_tmpl = _load("ent_fruit.png")
        self._stem_tmpl = _load("ent_stem.png")
        self._chat_atk_tmpl = _load("chat_attack.png")
        self._chat_revive_tmpl = _load("chat_revive.png", required=False)

    # ──────────────────────────────────────────
    # 제어
    # ──────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        if not self._initialized:
            self.log("[오류] 먼저 초기화가 필요합니다")
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True
        self.log("일시정지")

    def resume(self):
        self._paused = False
        self.log("재개")

    @property
    def is_running(self):
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self):
        return self._paused

    # ──────────────────────────────────────────
    # 스캔 결과 읽기 (별도 프로세스에서 실행)
    # ──────────────────────────────────────────
    # FIGHTING 집중 스캔 영역 크기 (NPC 중심 ± 반값)
    _FOCUS_HALF = 200

    def _find_npc(self, frame=None):
        """비블로킹: 템플릿 매칭 프로세스의 최신 결과 반환"""
        result = None
        try:
            while True:
                result = self._scan_result_q.get_nowait()
        except Exception:
            pass

        if result is not None:
            self._scan_done = True
            npc = result['npc']
            pickup = result['pickup']
            self._last_scan_results = result['debug_results']
            if npc is not None:
                self.log(f"[TMPL] '{self.cfg.npc_name}' 발견 → ({npc[0]},{npc[1]})")
            if pickup is not None:
                self.log(f"[PICKUP] 정령의 돌 → ({pickup[0]},{pickup[1]})")
            return npc, pickup

        self._scan_done = False
        return None, None

    # ──────────────────────────────────────────
    # 헬퍼 함수
    # ──────────────────────────────────────────
    def _set_state(self, s: str):
        self.state = s
        self._state_enter_t = time.time()
        self.log(f"[STATE] → {s}")

    def _click_move(self, win_pos):
        sx, sy = self._wincap.get_screen_position(win_pos)
        move_to(sx, sy)
        time.sleep(0.05)
        mouse_down("left")
        time.sleep(0.03)
        mouse_up("left")

    def _ctrl_drag_attack(self, win_pos):
        sx, sy = self._wincap.get_screen_position(win_pos)
        dx = int(self.cfg.drag_dist * 0.5)
        dy = int(self.cfg.drag_dist * 0.87)
        move_to(sx, sy)
        time.sleep(0.1)
        key_down("ctrl")
        time.sleep(0.1)
        mouse_down("left")
        time.sleep(0.1)
        steps = 5
        for i in range(1, steps + 1):
            move_to(sx + int(dx * i / steps), sy + int(dy * i / steps))
            time.sleep(0.02)
        time.sleep(0.1)
        mouse_up("left")
        time.sleep(0.05)
        key_up("ctrl")

    def _is_dialog_open(self, frame) -> bool:
        result = cv2.matchTemplate(frame, self._close_tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val >= 0.7

    def _is_dead(self, frame):
        result = cv2.matchTemplate(frame, self._restart_tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        return max_val >= 0.8, max_loc

    def _check_weight_red(self, frame) -> bool:
        now = time.time()
        if now - self._last_weight_check_t < self.cfg.weight_check_interval:
            return False
        self._last_weight_check_t = now
        wx, wy = self.cfg.weight_pos
        roi = frame[wy - 5:wy + 5, wx - 5:wx + 5]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = (hsv[:, :, 0] < 8) & (hsv[:, :, 1] > 150)
        ratio = np.sum(mask) / mask.size
        if ratio > 0.3:
            self.log(f"[WEIGHT] 무게 초과 감지! (빨강 비율={ratio:.2f})")
            return True
        return False

    def _find_item(self, frame, tmpl, name="item"):
        result = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= self.cfg.warehouse_item_threshold:
            th, tw = tmpl.shape[:2]
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            self.log(f"    [{name}] 발견! score={max_val:.3f} pos=({cx},{cy})")
            return (cx, cy)
        self.log(f"    [{name}] 미발견 score={max_val:.3f}")
        return None

    def _type_number(self, num_str):
        for ch in num_str:
            press(ch)
            time.sleep(0.05)

    def _type_location_cmd(self):
        press("enter")
        time.sleep(0.1)
        press("/")
        time.sleep(0.05)
        press("hangul")
        time.sleep(0.05)
        for k in ["d", "n", "l"]:
            press(k)
            time.sleep(0.02)
        time.sleep(0.05)
        for k in ["c", "l"]:
            press(k)
            time.sleep(0.02)
        time.sleep(0.05)
        press("hangul")
        time.sleep(0.05)
        press("enter")
        time.sleep(0.2)
        self.log("[CHAT] /위치 입력 완료")

    def _check_chat_attack(self, frame) -> bool:
        x1, y1, x2, y2 = self.cfg.chat_rect
        chat_roi = frame[y1:y2, x1:x2]
        if chat_roi.size == 0 or self._chat_atk_tmpl is None:
            return False
        if chat_roi.shape[0] < self._chat_atk_tmpl.shape[0] or chat_roi.shape[1] < self._chat_atk_tmpl.shape[1]:
            return False
        result = cv2.matchTemplate(chat_roi, self._chat_atk_tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return max_val >= self.cfg.chat_atk_threshold

    def _is_player_moving(self, frame) -> bool:
        px, py = self.cfg.player_pos
        ms = self.cfg.motion_size
        x1 = max(0, px - ms)
        y1 = max(0, py - ms)
        x2 = min(frame.shape[1], px + ms)
        y2 = min(frame.shape[0], py + ms)
        roi = frame[y1:y2, x1:x2]
        if self._prev_player_roi is not None and roi.shape == self._prev_player_roi.shape:
            diff = cv2.absdiff(roi, self._prev_player_roi)
            diff_mean = float(np.mean(diff))
            self._prev_player_roi = roi.copy()
            return diff_mean > self.cfg.motion_threshold
        self._prev_player_roi = roi.copy()
        return False

    # ──────────────────────────────────────────
    # 창고 / 복귀
    # ──────────────────────────────────────────
    def _run_warehouse(self):
        if self.cfg.use_clan_warehouse:
            self._run_clan_warehouse()
        else:
            self._run_personal_warehouse()

    def _run_personal_warehouse(self):
        self.log("[WAREHOUSE] 개인 창고 루틴 시작")
        key_down(self.cfg.scroll_key)
        time.sleep(0.1)
        key_up(self.cfg.scroll_key)
        time.sleep(1.0)

        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)

        self._click_move(self.cfg.warehouse_scroll_click)
        self.log(f"[WAREHOUSE] 두루마리 클릭  pos={self.cfg.warehouse_scroll_click}")
        time.sleep(self.cfg.scroll_wait)

        chk = self._wincap.get_screenshot()
        if self._is_dialog_open(chk):
            key_down("esc")
            time.sleep(0.1)
            key_up("esc")
            time.sleep(0.5)

        self._click_move(self.cfg.warehouse_npc_click)
        self.log(f"[WAREHOUSE] 창고 지기 클릭  pos={self.cfg.warehouse_npc_click}")
        time.sleep(2.0)

        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)

        self._click_move(self.cfg.warehouse_deposit_click)
        self.log(f"[WAREHOUSE] 물건을 맡긴다  pos={self.cfg.warehouse_deposit_click}")
        time.sleep(1.0)

        self._deposit_items()

        self._click_move(self.cfg.warehouse_ok_click)
        self.log(f"[WAREHOUSE] OK 클릭  pos={self.cfg.warehouse_ok_click}")
        time.sleep(1.0)
        self.log("[WAREHOUSE] 개인 창고 루틴 완료")

    def _run_clan_warehouse(self):
        self.log("[CLAN_WH] 혈맹 창고 루틴 시작")
        key_down(self.cfg.scroll_key)
        time.sleep(0.1)
        key_up(self.cfg.scroll_key)
        time.sleep(1.0)

        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)

        self._click_move(self.cfg.clan_warehouse_scroll_click)
        self.log(f"[CLAN_WH] 두루마리 클릭  pos={self.cfg.clan_warehouse_scroll_click}")
        time.sleep(self.cfg.scroll_wait)

        chk = self._wincap.get_screenshot()
        if self._is_dialog_open(chk):
            key_down("esc")
            time.sleep(0.1)
            key_up("esc")
            time.sleep(0.5)

        self._click_move(self.cfg.clan_warehouse_npc_click)
        self.log(f"[CLAN_WH] 혈맹 창고지기 클릭  pos={self.cfg.clan_warehouse_npc_click}")
        time.sleep(2.0)

        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)

        self._click_move(self.cfg.clan_warehouse_deposit_click)
        self.log(f"[CLAN_WH] 물건을 맡긴다  pos={self.cfg.clan_warehouse_deposit_click}")
        time.sleep(1.0)

        self._deposit_items()

        self._click_move(self.cfg.clan_warehouse_ok_click)
        self.log(f"[CLAN_WH] OK 클릭  pos={self.cfg.clan_warehouse_ok_click}")
        time.sleep(1.0)

        self.log("[CLAN_WH] 사냥터 복귀 시작")
        self._scroll_return()
        self.log("[CLAN_WH] 혈맹 창고 루틴 완료")

    def _deposit_items(self):
        frame = self._wincap.get_screenshot()
        fruit_pos = self._find_item(frame, self._fruit_tmpl, "엔트의 열매")
        if fruit_pos:
            self._click_move(fruit_pos)
            time.sleep(0.5)
            self._type_number("9999")
            time.sleep(0.3)

        frame = self._wincap.get_screenshot()
        stem_pos = self._find_item(frame, self._stem_tmpl, "엔트의 줄기")
        if stem_pos:
            self._click_move(stem_pos)
            time.sleep(0.5)
            self._type_number("9999")
            time.sleep(0.3)

    def _scroll_return(self):
        self.log("[RETURN] 두루마리로 복귀 시작")
        key_down(self.cfg.scroll_key)
        time.sleep(0.1)
        key_up(self.cfg.scroll_key)
        time.sleep(1.0)
        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)
        self._click_move(self.cfg.scroll_click)
        self.log(f"[RETURN] 두루마리 클릭  pos={self.cfg.scroll_click}")
        time.sleep(self.cfg.scroll_wait)
        chk = self._wincap.get_screenshot()
        if self._is_dialog_open(chk):
            key_down("esc")
            time.sleep(0.1)
            key_up("esc")
            time.sleep(0.5)
        self.log("[RETURN] 복귀 완료")
        self._post_return_move()

    def _push_scan_frame(self, frame):
        """스캐너 프로세스에 프레임 전달 (헬퍼)"""
        try:
            self._scan_frame_q.put_nowait({
                'frame': frame,
                'state': self.state,
                'fight_npc_pos': self._fight_npc_pos,
                'ocr_scan_rect': tuple(self.cfg.ocr_scan_rect),
                'npc_name': self.cfg.npc_name,
                'pickup_conf': self.cfg.pickup_conf,
                'pickup_exclude': list(self.cfg.pickup_exclude),
                'player_pos': tuple(self.cfg.player_pos),
                'npc_pos': self.npc_pos,
                'focus_half': self._FOCUS_HALF,
                'ocr_interval': self.cfg.ocr_interval,
            })
        except Exception:
            pass

    def _post_return_move(self):
        """복귀 후 3방향(11시/1시/3시) 중 랜덤 하나로 20초 직진 + 스캔
        장애물로 이동 불가 시 다른 방향으로 전환"""
        # 복귀 후 잔여 대화창 처리 + 안정화
        time.sleep(1.0)
        chk = self._wincap.get_screenshot()
        if chk is not None and self._is_dialog_open(chk):
            key_down("esc")
            time.sleep(0.1)
            key_up("esc")
            time.sleep(0.5)
            self.log("[RETURN] 잔여 대화창 ESC 처리")

        DIRS = [(-1, -1), (1, -1), (1, 0)]      # 11시, 1시, 3시
        NAMES = ["↖(11시)", "↗(1시)", "→(3시)"]
        order = list(range(3))
        random.shuffle(order)
        dir_idx = 0
        dx, dy = DIRS[order[dir_idx]]
        self.log(f"[RETURN] {NAMES[order[dir_idx]]} 방향 20초 무빙 시작")
        stuck_count = 0

        end_time = time.time() + 20.0
        while time.time() < end_time and self._running:
            px, py = self.cfg.player_pos
            dist = self.cfg.patrol_dist
            tx = max(21, min(px + dx * dist, 1242))
            ty = max(30, min(py + dy * dist, 714))
            self._click_move((tx, ty))

            # 모션 감지 baseline
            self._prev_player_roi = None
            baseline = self._wincap.get_screenshot()
            if baseline is not None:
                self._is_player_moving(baseline)

            # 2초 이동 대기 + 스캔
            moved = False
            wait_end = time.time() + 2.0
            while time.time() < wait_end and self._running:
                frame = self._wincap.get_screenshot()
                if frame is not None:
                    self._push_scan_frame(frame)
                    npc, pickup = self._find_npc()
                    if pickup is not None:
                        self._click_move(pickup)
                        time.sleep(1.0)
                    if npc is not None:
                        self.npc_pos = npc
                        self._last_npc_seen_t = time.time()
                        self._last_npc_found_t = time.time()
                        self._approach_dist0 = abs(npc[0] - self.cfg.player_pos[0]) + abs(npc[1] - self.cfg.player_pos[1])
                        self._approach_fail = 0
                        self.log(f"[RETURN] 무빙 중 엔트 발견! pos={npc} 거리={self._approach_dist0}")
                        self._click_move(self.npc_pos)
                        self._set_state("APPROACH")
                        return
                    if self._is_player_moving(frame):
                        moved = True
                time.sleep(0.1)

            if moved:
                stuck_count = 0
            else:
                stuck_count += 1
                if stuck_count >= 2:
                    # 장애물 → 다음 방향으로 전환
                    dir_idx += 1
                    if dir_idx >= len(order):
                        self.log("[RETURN] 모든 방향 막힘 → 무빙 종료")
                        break
                    dx, dy = DIRS[order[dir_idx]]
                    self.log(f"[RETURN] 장애물 감지 → {NAMES[order[dir_idx]]} 방향 전환")
                    stuck_count = 0

        self.log("[RETURN] 20초 무빙 완료")

    def _flee_and_patrol(self):
        dx, dy = random.choice(DIRECTIONS)
        dist = random.randint(300, self.cfg.patrol_dist)
        px, py = self.cfg.player_pos
        tx = max(21, min(px + dx * dist, 1242))
        ty = max(30, min(py + dy * dist, 714))
        d_name = DIR_NAMES[DIRECTIONS.index((dx, dy))]
        self.log(f"[FLEE] 포기 → {d_name} 이동 dist={dist} pos=({tx},{ty})")
        self._click_move((tx, ty))
        time.sleep(2.0)

    # ──────────────────────────────────────────
    # 사망 / 부활 처리
    # ──────────────────────────────────────────
    def _handle_death(self, frame, restart_loc):
        rh, rw = self._restart_tmpl.shape[:2]
        rx = restart_loc[0] + rw // 2
        ry = restart_loc[1] + rh // 2
        sx, sy = self._wincap.get_screen_position((rx, ry))
        move_to(sx, sy)
        time.sleep(0.1)
        mouse_down("left")
        time.sleep(0.03)
        mouse_up("left")
        self.log(f"[DEAD] 사망 감지 → Restart 클릭  ({rx},{ry})")
        time.sleep(5.0)
        self.npc_pos = None
        self.log("[DEAD] 부활 완료 → 창고 루틴")
        self._run_warehouse()
        self._last_npc_found_t = time.time()
        self._last_weight_check_t = time.time()
        self._set_state("PATROL")

    def _handle_revive_fail(self):
        key_down("ctrl")
        time.sleep(0.3)
        press("q")
        time.sleep(0.3)
        key_up("ctrl")
        time.sleep(2.0)
        for _ in range(30):
            chk = self._wincap.get_screenshot()
            dead2, restart_loc2 = self._is_dead(chk)
            if dead2:
                rh, rw = self._restart_tmpl.shape[:2]
                rx = restart_loc2[0] + rw // 2
                ry = restart_loc2[1] + rh // 2
                self._click_move((rx, ry))
                self.log(f"[DEAD] Restart 클릭  ({rx},{ry})")
                break
            time.sleep(0.1)
        time.sleep(5.0)
        self._type_location_cmd()
        self.npc_pos = None
        self._run_warehouse()
        self._last_npc_found_t = time.time()
        self._last_weight_check_t = time.time()
        self._set_state("PATROL")

    def _check_revive_chat(self, frame) -> bool:
        if self._chat_revive_tmpl is None:
            return False
        x1, y1, x2, y2 = self.cfg.chat_rect
        chat_roi = frame[y1:y2, x1:x2]
        if chat_roi.size == 0:
            return False
        if chat_roi.shape[0] < self._chat_revive_tmpl.shape[0] or chat_roi.shape[1] < self._chat_revive_tmpl.shape[1]:
            return False
        rev_result = cv2.matchTemplate(chat_roi, self._chat_revive_tmpl, cv2.TM_CCOEFF_NORMED)
        _, rev_score, _, _ = cv2.minMaxLoc(rev_result)
        return rev_score >= 0.7

    # (디버그 프레임 제거됨)

    # ──────────────────────────────────────────
    # 메인 루프
    # ──────────────────────────────────────────
    def _main_loop(self):
        self._last_npc_found_t = time.time()
        self._last_weight_check_t = 0.0
        self._last_stuck_check_t = 0.0
        self._patrol_history = []
        self._patrol_no_move_count = 0
        self._dir_idx = random.randint(0, 7)
        self._patrol_steps = 0
        self._scan_pause_until = 0.0
        self._set_state("PATROL")
        self.log("봇 시작 (템플릿 매칭)  P=일시정지  Q=종료  F12=긴급종료")

        # 이전 실행의 잔여 결과 제거
        try:
            while True:
                self._scan_result_q.get_nowait()
        except Exception:
            pass

        while self._running:
            frame = self._wincap.get_screenshot()
            if frame is None or frame.size == 0:
                time.sleep(0.1)
                continue

            # 스캐너 프로세스에 최신 프레임 전달 (비블로킹)
            if time.time() >= self._scan_pause_until:
                try:
                    self._scan_frame_q.put_nowait({
                        'frame': frame,
                        'state': self.state,
                        'fight_npc_pos': self._fight_npc_pos,
                        'ocr_scan_rect': tuple(self.cfg.ocr_scan_rect),
                        'npc_name': self.cfg.npc_name,
                        'pickup_conf': self.cfg.pickup_conf,
                        'pickup_exclude': list(self.cfg.pickup_exclude),
                        'player_pos': tuple(self.cfg.player_pos),
                        'npc_pos': self.npc_pos,
                        'focus_half': self._FOCUS_HALF,
                        'ocr_interval': self.cfg.ocr_interval,
                    })
                except Exception:
                    pass  # 큐 가득 참 — 스킵

            if self._paused:
                time.sleep(0.1)
                continue

            now = time.time()
            elapsed = now - self._state_enter_t

            # ── 사망 감지 ──
            dead, restart_loc = self._is_dead(frame)
            if dead:
                self._handle_death(frame, restart_loc)
                continue

            # ── 부활 실패 채팅 감지 ──
            if self._check_revive_chat(frame):
                self.log("[DEAD] '오랫동안 부활하지 않아' 감지! → Ctrl+Q")
                self._handle_revive_fail()
                continue

            # ── 대화창 감지 (APPROACH 제외) ──
            if self.state != "APPROACH":
                dlg_result = cv2.matchTemplate(frame, self._close_tmpl, cv2.TM_CCOEFF_NORMED)
                _, dlg_score, _, _ = cv2.minMaxLoc(dlg_result)
                if dlg_score >= 0.7:
                    if self._check_revive_chat(frame):
                        self.log("[DEAD] 대화창 + 부활 감지 → ESC → Ctrl+Q")
                        key_down("esc")
                        time.sleep(0.3)
                        key_up("esc")
                        time.sleep(1.0)
                        self._handle_revive_fail()
                        continue
                    key_up("ctrl")
                    mouse_up("left")
                    time.sleep(0.05)
                    key_down("esc")
                    time.sleep(0.1)
                    key_up("esc")
                    self.log(f"[DIALOG] 대화창 감지 → ESC  score={dlg_score:.3f}")
                    time.sleep(0.15)
                    if self.state == "FIGHTING" and self.npc_pos is not None:
                        self._ctrl_drag_attack(self.npc_pos)
                        self._fight_npc_pos = self.npc_pos
                        self._last_attack_t = time.time()
                        self._last_atk_msg_t = time.time()
                        self.log(f"[DIALOG] ESC 후 재공격  pos={self.npc_pos}")
                    continue

            # ── 무게 초과 ──
            if self.state in ("PATROL", "FIGHTING") and self._check_weight_red(frame):
                self._run_warehouse()
                self.npc_pos = None
                self._last_weight_check_t = time.time()
                self._set_state("PATROL")
                continue

            # ── PATROL ──
            if self.state == "PATROL":
                self._do_patrol(frame, now, elapsed)

            # ── APPROACH ──
            elif self.state == "APPROACH":
                self._do_approach(frame, now, elapsed)

            # ── ATTACK ──
            elif self.state == "ATTACK":
                self._do_attack(frame, now, elapsed)

            # ── FIGHTING ──
            elif self.state == "FIGHTING":
                self._do_fighting(frame, now, elapsed)


        # 종료 정리
        key_up("ctrl")
        mouse_up("left")
        self.state = "IDLE"
        self.log("봇 중지됨")

    # ──────────────────────────────────────────
    # 상태별 로직
    # ──────────────────────────────────────────
    def _do_patrol(self, frame, now, elapsed):
        npc, pickup = self._find_npc()
        if pickup is not None:
            self._click_move(pickup)
            time.sleep(1.0)
        if npc is not None:
            self.npc_pos = npc
            self._last_npc_seen_t = now
            self._last_npc_found_t = now
            self._approach_dist0 = abs(npc[0] - self.cfg.player_pos[0]) + abs(npc[1] - self.cfg.player_pos[1])
            self._approach_fail = 0
            self.log(f"[NPC 발견] 대화 클릭  pos={npc}  거리={self._approach_dist0}")
            self._click_move(self.npc_pos)
            self._set_state("APPROACH")
        else:
            if elapsed >= self.cfg.move_wait_sec:
                # 엔트 미발견 복귀
                if now - self._last_npc_found_t >= self.cfg.npc_not_found_timeout:
                    self.log(f"[RETURN] {self.cfg.npc_not_found_timeout:.0f}초간 엔트 미발견 → 두루마리 복귀")
                    self._scroll_return()
                    self.npc_pos = None
                    self._last_npc_found_t = time.time()
                    self._state_enter_t = time.time()
                    return

                # 갇힘 감지
                if (
                    len(self._patrol_history) >= self.cfg.stuck_history_size
                    and now - self._last_stuck_check_t >= self.cfg.stuck_check_interval
                ):
                    self._last_stuck_check_t = now
                    xs = [p[0] for p in self._patrol_history]
                    ys = [p[1] for p in self._patrol_history]
                    spread = max(xs) - min(xs) + max(ys) - min(ys)
                    if spread < self.cfg.stuck_radius:
                        self.log(f"[STUCK] 갇힘 감지! 범위={spread}px → 두루마리 복귀")
                        self._scroll_return()
                        self.npc_pos = None
                        self._patrol_history.clear()
                        self._last_npc_found_t = time.time()
                        self._state_enter_t = time.time()
                        return

                dx, dy = DIRECTIONS[self._dir_idx]
                px, py = self.cfg.player_pos
                dist = random.randint(150, self.cfg.patrol_dist) if dy >= 0 else random.randint(80, self.cfg.patrol_dist_up)
                # 랜덤 오프셋: 같은 방향이라도 매번 다른 좌표 (캐릭터별 동선 분산)
                ox = random.randint(-80, 80)
                oy = random.randint(-50, 50)
                tx = max(21, min(px + dx * dist + ox, 1242))
                ty = max(30, min(py + dy * dist + oy, 714))
                self._click_move((tx, ty))
                self._patrol_history.append((tx, ty))
                if len(self._patrol_history) > self.cfg.stuck_history_size:
                    self._patrol_history.pop(0)
                self._patrol_steps += 1
                d_name = DIR_NAMES[self._dir_idx]
                self.log(f"[PATROL] {d_name} dist={dist} pos=({tx},{ty})  ({self._patrol_steps}/{self.cfg.max_patrol_steps})")
                # 방향 전환 스텝도 랜덤 (3~max) → 캐릭터마다 다른 타이밍에 전환
                steps_limit = random.randint(max(2, self.cfg.max_patrol_steps - 2), self.cfg.max_patrol_steps + 2)
                if self._patrol_steps >= steps_limit:
                    if self.cfg.patrol_random:
                        self._dir_idx = random.choice([i for i in range(8) if i != self._dir_idx])
                    else:
                        # 순차 모드에서도 가끔 방향 건너뛰기
                        skip = random.choice([1, 1, 1, 2])
                        self._dir_idx = (self._dir_idx + skip) % 8
                    self._patrol_steps = 0
                    self.log(f"[PATROL] 방향 전환 → {DIR_NAMES[self._dir_idx]}")

                # 이동 완료 대기
                move_start = time.time()
                time.sleep(0.5)
                self._prev_player_roi = None
                _baseline = self._wincap.get_screenshot()
                self._is_player_moving(_baseline)
                time.sleep(0.2)

                moved_at_all = False
                while time.time() - move_start < self.cfg.move_wait_sec:
                    if not self._running:
                        return
                    chk = self._wincap.get_screenshot()
                    # 이동 중에도 스캔 결과 체크 (비블로킹)
                    npc_chk, pickup_chk = self._find_npc()
                    if pickup_chk is not None:
                        self.log(f"[PICKUP] 정령의 돌 발견! 줍기  pos={pickup_chk}")
                        self._click_move(pickup_chk)
                        time.sleep(1.0)
                    if npc_chk is not None:
                        self.npc_pos = npc_chk
                        self._last_npc_seen_t = time.time()
                        self._last_npc_found_t = time.time()
                        self._approach_dist0 = abs(npc_chk[0] - self.cfg.player_pos[0]) + abs(npc_chk[1] - self.cfg.player_pos[1])
                        self._approach_fail = 0
                        self.log(f"[PATROL] 이동 중 엔트 발견!  pos={npc_chk}  거리={self._approach_dist0}")
                        self._click_move(self.npc_pos)
                        self._patrol_no_move_count = 0
                        self._set_state("APPROACH")
                        return
                    if self._is_player_moving(chk):
                        moved_at_all = True
                    else:
                        break
                    time.sleep(0.1)

                # 이동 불가 → 랜덤 무빙 탈출 시도
                if moved_at_all:
                    self._patrol_no_move_count = 0
                else:
                    # 랜덤 방향으로 탈출 시도
                    escape_dirs = list(range(8))
                    random.shuffle(escape_dirs)
                    escaped = False
                    for edi in escape_dirs:
                        edx, edy = DIRECTIONS[edi]
                        epx, epy = self.cfg.player_pos
                        edist = random.randint(200, 400)
                        etx = max(21, min(epx + edx * edist, 1242))
                        ety = max(30, min(epy + edy * edist, 714))
                        self._prev_player_roi = None
                        baseline = self._wincap.get_screenshot()
                        self._is_player_moving(baseline)
                        self._click_move((etx, ety))
                        time.sleep(0.5)
                        echk = self._wincap.get_screenshot()
                        if self._is_player_moving(echk):
                            self.log(f"[PATROL] 이동 불가 → {DIR_NAMES[edi]} 랜덤 탈출 성공")
                            escaped = True
                            self._patrol_no_move_count = 0
                            break
                    if not escaped:
                        self._patrol_no_move_count += 1
                        self.log(f"[PATROL] 랜덤 탈출 실패 ({self._patrol_no_move_count}/{self.cfg.stuck_no_move_max})")
                        if self._patrol_no_move_count >= self.cfg.stuck_no_move_max:
                            self.log(f"[STUCK] 연속 탈출 실패 {self._patrol_no_move_count}회 → 두루마리 복귀")
                            self._scroll_return()
                            self.npc_pos = None
                            self._patrol_history.clear()
                            self._patrol_no_move_count = 0
                            self._last_npc_found_t = time.time()
                            self._state_enter_t = time.time()
                            return
                self._state_enter_t = time.time() - self.cfg.move_wait_sec
            time.sleep(self.cfg.scan_interval)

    def _do_approach(self, frame, now, elapsed):
        dlg_r = cv2.matchTemplate(frame, self._close_tmpl, cv2.TM_CCOEFF_NORMED)
        _, ds, _, _ = cv2.minMaxLoc(dlg_r)
        if ds >= 0.7:
            key_down("esc")
            time.sleep(0.1)
            key_up("esc")
            self.log(f"[APPROACH] 대화창 → ESC  score={ds:.3f}")
            time.sleep(0.15)
            if self.npc_pos is not None:
                self._ctrl_drag_attack(self.npc_pos)
                self._last_attack_t = time.time()
                self._last_atk_msg_t = time.time()
                self._approach_fail = 0
                self._atk_confirmed = False
                if self._check_chat_attack(self._wincap.get_screenshot()):
                    self.log("[APPROACH] 이전 버섯포자 잔존 → /위치 클리어")
                    self._type_location_cmd()
                    self._ctrl_drag_attack(self.npc_pos)
                    self._last_attack_t = time.time()
                    self._last_atk_msg_t = time.time()
                self._fight_npc_pos = self.npc_pos
                self.log(f"[APPROACH] Ctrl+드래그 공격  pos={self.npc_pos}")
                self._set_state("FIGHTING")
        elif elapsed >= self.cfg.approach_wait_sec:
            npc, _ = self._find_npc()
            if npc is not None:
                self.npc_pos = npc
            if self.npc_pos is not None:
                cur_dist = abs(self.npc_pos[0] - self.cfg.player_pos[0]) + abs(self.npc_pos[1] - self.cfg.player_pos[1])
                if cur_dist <= self.cfg.close_enough:
                    self.log(f"[APPROACH] 사거리 도달 거리={cur_dist}px → 공격")
                    self._set_state("ATTACK")
                elif self._approach_dist0 is not None and cur_dist >= self._approach_dist0 - 20:
                    moving = self._is_player_moving(frame)
                    if moving:
                        self.log(f"[APPROACH] 이동 중 거리={cur_dist}px → 대기 연장")
                        self._state_enter_t = time.time()
                    else:
                        self._approach_fail += 1
                        if self._approach_fail >= self.cfg.approach_fail_max:
                            self.log(f"[APPROACH] 길막 {self._approach_fail}회 → 포기")
                            self.npc_pos = None
                            self._approach_fail = 0
                            self._flee_and_patrol()
                            self._set_state("PATROL")
                        else:
                            self.log(f"[APPROACH] 길막 감지! 거리={cur_dist}px (시작={self._approach_dist0}) → 재시도 ({self._approach_fail}/{self.cfg.approach_fail_max})")
                            self._click_move(self.npc_pos)
                            self._state_enter_t = time.time()
                else:
                    self._approach_dist0 = cur_dist
                    self.log(f"[APPROACH] 접근 중 거리={cur_dist}px → 재클릭")
                    self._click_move(self.npc_pos)
                    self._state_enter_t = time.time()
            else:
                self.log("[APPROACH] 대화창 안 열림 + 엔트 없음 → PATROL")
                self._set_state("PATROL")
        time.sleep(0.05)

    def _do_attack(self, frame, now, elapsed):
        npc, pickup = self._find_npc()
        if pickup is not None:
            self.log(f"[PICKUP] 정령의 돌 발견! 줍기  pos={pickup}")
            self._click_move(pickup)
            time.sleep(1.0)
        if npc is not None:
            self.npc_pos = npc
            self._last_npc_seen_t = now
        elif not self._scan_done:
            self._last_npc_seen_t = now

        if self.npc_pos is not None and now - self._last_attack_t >= self.cfg.attack_interval:
            self._ctrl_drag_attack(self.npc_pos)
            self._last_attack_t = time.time()
            self._last_atk_msg_t = time.time()
            self._last_npc_seen_t = time.time()
            self._atk_confirmed = False
            if self._check_chat_attack(self._wincap.get_screenshot()):
                self.log("[ATK] 이전 버섯포자 잔존 → /위치 클리어")
                self._type_location_cmd()
                self._ctrl_drag_attack(self.npc_pos)
                self._last_attack_t = time.time()
                self._last_atk_msg_t = time.time()
            self._fight_npc_pos = self.npc_pos
            self.log(f"[ATK] Ctrl+드래그  pos={self.npc_pos}")
            self._set_state("FIGHTING")
        else:
            gone_sec = now - self._last_npc_seen_t if self._last_npc_seen_t else elapsed
            if gone_sec >= self.cfg.npc_gone_timeout:
                self.log("[ATK] NPC 사라짐 → PATROL")
                self.npc_pos = None
                self._atk_fail_count = 0
                self._set_state("PATROL")
        time.sleep(0.05)

    def _do_fighting(self, frame, now, elapsed):
        npc, pickup = self._find_npc()

        # 정령의 돌 줍기
        if pickup is not None:
            self.log(f"[PICKUP] 정령의 돌 발견! 공격 중단 → 줍기  pos={pickup}")
            key_up("ctrl")
            mouse_up("left")
            time.sleep(0.3)
            self._click_move(pickup)
            time.sleep(2.0)
            if self.npc_pos is not None:
                self.log("[PICKUP] 줍기 완료 → 엔트 재공격")
                self._click_move(self.npc_pos)
                time.sleep(1.5)
                chk = self._wincap.get_screenshot()
                if self._is_dialog_open(chk):
                    key_down("esc")
                    time.sleep(0.1)
                    key_up("esc")
                    time.sleep(0.5)
                self._ctrl_drag_attack(self.npc_pos)
                self._last_attack_t = time.time()
                self._last_atk_msg_t = time.time()
            return

        if npc is not None:
            # 이상치 필터링: FIGHTING 중 이전 위치 대비 너무 큰 점프는 오인식
            if self._fight_npc_pos is not None:
                jump = abs(npc[0] - self._fight_npc_pos[0]) + abs(npc[1] - self._fight_npc_pos[1])
                if jump > 500:
                    self.log(f"[FIGHTING] 스캔 이상치 무시  {jump}px  pos={npc}")
                    npc = None
            if npc is not None:
                self._last_npc_found_t = now
                self.npc_pos = npc
                self._last_npc_seen_t = now
        elif not self._scan_done:
            self._last_npc_seen_t = now

        # 엔트 이탈 감지
        if npc is not None and self._fight_npc_pos is not None:
            npc_moved = abs(npc[0] - self._fight_npc_pos[0]) + abs(npc[1] - self._fight_npc_pos[1])
            move_threshold = 200 if self._atk_confirmed else 80
            if npc_moved > move_threshold:
                self.log(f"[FIGHTING] 엔트 이동! {npc_moved}px → 재공격")
                self._ctrl_drag_attack(self.npc_pos)
                self._fight_npc_pos = self.npc_pos
                self._last_attack_t = time.time()
                self._last_atk_msg_t = time.time()
                self._atk_confirmed = False
                return
            elif self._atk_confirmed:
                self._fight_npc_pos = self.npc_pos

        # 채팅 기반 공격 확인
        chat_active = self._check_chat_attack(frame)
        if not self._atk_confirmed:
            if chat_active:
                self._atk_confirmed = True
                self._last_atk_msg_t = now
                self._reattack_fail = 0
                self._escape_retry = 0
                self.log("[FIGHTING] 공격 확인 (버섯포자 감지)")
            elif now - self._last_atk_msg_t >= self.cfg.atk_confirm_timeout:
                self._reattack_fail += 1
                if self._reattack_fail > self.cfg.reattack_fail_max:
                    self.log(f"[FIGHTING] 공격 실패 {self._reattack_fail}회 → 포기")
                    self.npc_pos = None
                    self._reattack_fail = 0
                    self._flee_and_patrol()
                    self._set_state("PATROL")
                else:
                    DIR_NAMES_ATK = ["↑", "→", "↓", "←", "↖", "↗", "↘", "↙"]
                    REATTACK_DIRS = [(0, -180), (180, 0), (0, 180), (-180, 0),
                                     (-130, -130), (130, -130), (130, 130), (-130, 130)]
                    if self.npc_pos is not None:
                        moved = False
                        dirs_order = list(range(len(REATTACK_DIRS)))
                        random.shuffle(dirs_order)
                        for di in dirs_order:
                            ox, oy = REATTACK_DIRS[di]
                            mx = max(21, min(self.npc_pos[0] + ox, 1242))
                            my = max(30, min(self.npc_pos[1] + oy, 714))
                            self.log(f"[FIGHTING] {DIR_NAMES_ATK[di]} 우회 시도 ({mx},{my})  ({self._reattack_fail}/{self.cfg.reattack_fail_max})")
                            self._prev_player_roi = None
                            baseline = self._wincap.get_screenshot()
                            self._is_player_moving(baseline)
                            self._click_move((mx, my))
                            time.sleep(0.5)
                            chk = self._wincap.get_screenshot()
                            if self._is_player_moving(chk):
                                moved = True
                                self.log(f"[FIGHTING] {DIR_NAMES_ATK[di]} 이동 성공 → 재공격")
                                time.sleep(0.3)
                                break
                            self.log(f"[FIGHTING] {DIR_NAMES_ATK[di]} 이동 불가 → 다음 방향")
                        if not moved:
                            self.log("[FIGHTING] 모든 방향 이동 불가 → 두루마리 복귀")
                            self._scroll_return()
                            self.npc_pos = None
                            self._reattack_fail = 0
                            self._set_state("PATROL")
                            return
                        self._ctrl_drag_attack(self.npc_pos)
                        self._fight_npc_pos = self.npc_pos
                        self._last_attack_t = time.time()
                        self._last_atk_msg_t = time.time()
        else:
            # 공격 확인 상태 → 주기적 재확인
            if now - self._last_atk_msg_t >= 3.0:
                self._type_location_cmd()
                time.sleep(0.8)
                chk = self._wincap.get_screenshot()
                if self._check_chat_attack(chk):
                    self._last_atk_msg_t = time.time()
                    self.log("[FIGHTING] 공격 재확인")
                else:
                    self.log("[FIGHTING] 자동공격 풀림 → 접근 후 재공격")
                    if self.npc_pos is not None:
                        self._click_move(self.npc_pos)
                        time.sleep(0.5)
                        self._ctrl_drag_attack(self.npc_pos)
                        self._fight_npc_pos = self.npc_pos
                        self._last_attack_t = time.time()
                        self._last_atk_msg_t = time.time()
                        self._atk_confirmed = False
                    else:
                        self.log("[FIGHTING] 자동공격 풀림 + 엔트 없음 → PATROL")
                        self._set_state("PATROL")

        # 엔트 이름 사라짐 → 사망
        gone_sec = now - self._last_npc_seen_t if self._last_npc_seen_t else elapsed
        gone_limit = self.cfg.npc_gone_timeout * 4 if self._atk_confirmed else self.cfg.npc_gone_timeout
        if gone_sec >= gone_limit:
            if self._atk_confirmed:
                self._type_location_cmd()
                time.sleep(0.8)
                chk = self._wincap.get_screenshot()
                if self._check_chat_attack(chk):
                    self._last_atk_msg_t = time.time()
                    self._last_npc_seen_t = time.time()
                    self.log("[FIGHTING] 스캔 미감지이나 채팅 공격 확인 → 전투 유지")
                    return
            self.log("[FIGHTING] 엔트 사라짐 → 사망")
            self._type_location_cmd()
            self.npc_pos = None
            self._atk_fail_count = 0
            self._atk_confirmed = False
            self._set_state("PATROL")
        time.sleep(0.1)
