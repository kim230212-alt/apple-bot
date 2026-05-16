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

import ctypes
import win32gui
from typing import Optional, Tuple, Callable


def _force_foreground(hwnd: int) -> None:
    """Windows foreground lock 우회: AttachThreadInput + SetForegroundWindow.
    일반 SetForegroundWindow는 백그라운드 프로세스에서 무시됨."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    cur_thread = kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd:
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(fg_thread, cur_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(fg_thread, cur_thread, False)
            return
    user32.SetForegroundWindow(hwnd)

from template_scanner import template_process_fn

from ent_bot_config import BotConfig
from capture_window import WindowCapture
from interception import (
    move_to, mouse_down, mouse_up, auto_capture_devices,
    click, press, key_down, key_up, set_devices, scroll,
    get_keyboard, get_mouse,
)
from interception.inputs import _g_context as _icp_ctx
from input_lock import input_lock as _ilock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 8방향
DIRECTIONS = [
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1),
]
DIR_NAMES = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"]

# 창고 등 장기 연속 동작 중 타 엔진의 포커스 탈취 방지.
# 0이면 독점 없음, 비-0이면 해당 hwnd가 포커스 독점 중.
_focus_lease_hwnd: int = 0

# 듀얼 모드에서 auto_capture_devices 동시 호출 방지 락
_device_detect_lock = threading.Lock()


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
        self._last_hp_check_t = 0.0
        self._last_hp_f8_t = 0.0
        self._last_stuck_check_t = 0.0
        self._last_zone_check_t = 0.0
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
        self._pickup_lmb_held = False   # 정령의 돌 줍기 중 LMB 유지 상태
        self._last_pickup_name = "아이템"   # 직전 매칭된 픽업 템플릿 파일명
        self._last_pickup_score = 0.0
        self._last_pickup_anchor = None    # 직전 세션 anchor (window coord)
        self._last_pickup_anchor_t = 0.0   # 직전 anchor 종료 시각

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
        self._zone_tmpl = None
        self._pan_mane_tmpl = None
        self._fruit_tmpl = None
        self._stem_tmpl = None
        self._spirit_tmpl = None
        self._mushroom_tmpl = None
        self._mithril_tmpl = None
        self._bark_tmpl = None
        self._chat_atk_tmpl = None
        self._chat_revive_tmpl = None
        self._initialized = False

    # ──────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────
    def initialize(self):
        # Windows Foreground Lock Timeout 비활성화 (SetForegroundWindow 거부 방지)
        try:
            import ctypes as _ctypes
            _ctypes.windll.user32.SystemParametersInfoW(0x2001, 0, 0, 0)
            self.log("포그라운드 잠금 타임아웃 비활성화 완료")
        except Exception:
            pass

        kb = self.cfg.keyboard_device
        ms = self.cfg.mouse_device

        # config에 저장된 device 번호가 이 컴퓨터에서도 유효한지 검증
        def _dev_valid(n):
            try:
                return (n is not None and
                        n < len(_icp_ctx.devices) and
                        _icp_ctx.devices[n].handle not in (-1, 0, None))
            except Exception:
                return False

        if kb is not None and ms is not None and _dev_valid(kb) and _dev_valid(ms):
            # 유효한 캐시 → auto_capture 생략 (멀티 인스턴스 경쟁 방지)
            set_devices(keyboard=kb, mouse=ms)
            self.log(f"디바이스 설정 (캐시)  KB={kb}  Mouse={ms}")
        else:
            if kb is not None and not _dev_valid(kb):
                self.log(f"[WARN] KB={kb} 이 컴퓨터에서 유효하지 않음 → 재감지")
            if ms is not None and not _dev_valid(ms):
                self.log(f"[WARN] Mouse={ms} 이 컴퓨터에서 유효하지 않음 → 재감지")
            with _device_detect_lock:
                # 락 획득 후 다시 확인 (다른 봇이 이미 감지해 config 저장했을 수 있음)
                kb = self.cfg.keyboard_device
                ms = self.cfg.mouse_device
                if kb is not None and ms is not None and _dev_valid(kb) and _dev_valid(ms):
                    set_devices(keyboard=kb, mouse=ms)
                    self.log(f"디바이스 설정 (재확인 캐시)  KB={kb}  Mouse={ms}")
                else:
                    self.log("디바이스 감지 중... (마우스 움직여주세요)")
                    auto_capture_devices(keyboard=True, mouse=True, verbose=True)
            kb = self.cfg.keyboard_device
            ms = self.cfg.mouse_device
            if kb is not None or ms is not None:
                set_devices(keyboard=kb, mouse=ms)
                self.log(f"디바이스 오버라이드  KB={kb}  Mouse={ms}")
                # 마우스 device 미설정 시 감지된 값 저장 → 다음 실행부터 auto_capture 생략
                if ms is None:
                    detected_ms = get_mouse()
                    if detected_ms is not None:
                        self.cfg.mouse_device = detected_ms
                        if self.cfg._path:
                            self.cfg.save()
                        self.log(f"[MS] 마우스 디바이스 저장: {detected_ms}")
            else:
                # auto_capture 결과 검증: 마우스와 같은 장치를 키보드로 잡은 경우 교정
                detected_kb = get_keyboard()
                detected_ms = get_mouse()
                ms_hwid = (_icp_ctx.devices[detected_ms].get_HWID() or "")[:30] if detected_ms is not None else ""
                kb_hwid = (_icp_ctx.devices[detected_kb].get_HWID() or "")[:30] if detected_kb is not None else ""
                if ms_hwid and kb_hwid.startswith(ms_hwid[:20]):
                    self.log(f"[KB] 키보드({detected_kb})가 마우스({detected_ms})와 동일 장치 → 교정 시도")
                    for i in range(20):
                        dev = _icp_ctx.devices[i]
                        hwid = (dev.get_HWID() or "")
                        if hwid and not hwid[:20].startswith(ms_hwid[:20]) and dev.handle not in (-1, 0, None):
                            set_devices(keyboard=i)
                            self.log(f"[KB] 키보드 교정 완료: {detected_kb} → {i}  ({hwid[:50]})")
                            self.cfg.keyboard_device = i
                            if self.cfg._path:
                                self.cfg.save()
                            break
                else:
                    self.log(f"[KB] 키보드 디바이스: {detected_kb}")
                    # 마우스와 같은 수신기(같은 VID/PID)의 실제 키보드 인터페이스(MI_01) 찾기
                    # 예: 로지텍 유니파이잉 수신기 MI_00=마우스, MI_01=키보드
                    # auto_capture가 마우스 매크로 장치(UP:0001_U:0006)를 키보드로 잘못 잡는 경우 교정
                    import re as _re
                    m = _re.search(r'VID_[0-9A-Fa-f]+&PID_[0-9A-Fa-f]+',
                                   (_icp_ctx.devices[detected_ms].get_HWID() or "") if detected_ms is not None else "")
                    if m:
                        vid_pid = m.group()
                        for i in range(10):  # 키보드 슬롯 0-9
                            try:
                                h = (_icp_ctx.devices[i].get_HWID() or "")
                                if (vid_pid in h and "MI_01" in h
                                        and _icp_ctx.devices[i].handle not in (-1, 0, None)):
                                    if i != detected_kb:
                                        set_devices(keyboard=i)
                                        self.log(f"[KB] 수신기 키보드로 교정: {detected_kb}→{i}  {vid_pid} MI_01")
                                        self.cfg.keyboard_device = i
                                        if self.cfg._path:
                                            self.cfg.save()
                                    break
                            except Exception:
                                pass
                # 감지된 마우스 device 저장 (다음 실행 시 auto_capture 생략 가능)
                if detected_ms is not None and self.cfg.mouse_device is None:
                    self.cfg.mouse_device = detected_ms
                    if self.cfg._path:
                        self.cfg.save()
                    self.log(f"[MS] 마우스 디바이스 저장: {detected_ms}")

        idx = getattr(self.cfg, "window_index", 0)
        self._wincap = WindowCapture(self.cfg.window_title, window_index=idx)
        self.log(f"창 감지 완료  ({self._wincap.offset_x}, {self._wincap.offset_y})  크기={self._wincap.w}x{self._wincap.h}")
        if self._wincap.w == 0 or self._wincap.h == 0:
            raise RuntimeError(f"[오류] 게임 창 크기가 0입니다 (최소화 상태이거나 window_index={idx}에 해당하는 창이 없음). 게임 창을 화면에 띄워주세요.")

        # 게임 창 포커스 + 마우스 중앙으로 이동
        try:
            _force_foreground(self._wincap.hwnd)
        except Exception:
            pass
        cx = self._wincap.offset_x + self._wincap.w // 2
        cy = self._wincap.offset_y + self._wincap.h // 2
        move_to(cx, cy)
        self.log(f"게임 창 포커스 + 마우스 이동  ({cx}, {cy})")

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
        self._zone_tmpl = _load("zone_fairy_forest.png", required=False)
        self._pan_mane_tmpl = _load("ent_pan_mane.png", required=False)
        self._fruit_tmpl = _load("ent_fruit.png")
        self._stem_tmpl = _load("ent_stem.png")
        self._spirit_tmpl = _load("ent_spirit.png")
        self._mushroom_tmpl = _load("ent_mushroom.png", required=False)
        self._mithril_tmpl = _load("ent_mithril.png", required=False)
        self._bark_tmpl = _load("ent_bark.png", required=False)
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
        self._release_focus_lease()

    def pause(self):
        self._paused = True
        self.log("일시정지")

    def resume(self):
        self._paused = False
        self.log("재개")

    def _interruptible_sleep(self, secs: float):
        end = time.time() + secs
        while self._running and time.time() < end:
            if self._paused:
                end += 0.1
            time.sleep(0.1)

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
            extra_npc = result.get('extra_npc')
            pickup = result['pickup']
            self._last_pickup_name = result.get('pickup_name') or "아이템"
            self._last_pickup_score = result.get('pickup_score', 0.0)
            self._last_scan_results = result['debug_results']
            if npc is not None:
                self.log(f"[TMPL] '{self.cfg.npc_name}' 발견 → ({npc[0]},{npc[1]})")
            elif extra_npc is not None and self.cfg.extra_npc_enabled:
                npc = extra_npc
                self.log(f"[TMPL] '{self.cfg.extra_npc_name}' 발견 → ({npc[0]},{npc[1]})")
            if pickup is not None:
                self.log(f"[PICKUP] {self._last_pickup_name} score={self._last_pickup_score:.3f} → ({pickup[0]},{pickup[1]})")
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
        self._pickup_release()  # 줍기 LMB 유지 중이면 안전 해제
        sx, sy = self._wincap.get_screen_position(win_pos)
        self._wait_for_lease()
        with _ilock():
            self._ensure_focus()
            move_to(sx, sy)
            time.sleep(0.05)
            mouse_down("left")
            time.sleep(0.03)
            mouse_up("left")

    def _pickup_click_hold(self, win_pos):
        """정령의 돌 줍기 — LMB 유지 + 커서만 이동.
        연속 줍기 시 캐릭터가 멈추지 않고 돌 사이를 부드럽게 이동."""
        sx, sy = self._wincap.get_screen_position(win_pos)
        with _ilock():
            self._ensure_focus()
            move_to(sx, sy)
            if not self._pickup_lmb_held:
                time.sleep(0.05)
                mouse_down("left")
                self._pickup_lmb_held = True

    def _pickup_release(self):
        """_pickup_click_hold 로 눌러진 LMB 해제."""
        if self._pickup_lmb_held:
            mouse_up("left")
            self._pickup_lmb_held = False

    def _acquire_focus_lease(self):
        """창고 등 장기 연속 동작 시작 — 타 엔진이 포커스를 빼앗지 못하게 독점."""
        global _focus_lease_hwnd
        _focus_lease_hwnd = self._wincap.hwnd

    def _release_focus_lease(self):
        """포커스 독점 해제 (장기 동작 완료 또는 엔진 정지 시)."""
        global _focus_lease_hwnd
        try:
            if _focus_lease_hwnd == self._wincap.hwnd:
                _focus_lease_hwnd = 0
        except AttributeError:
            _focus_lease_hwnd = 0

    def _wait_for_lease(self, timeout: float = 120.0):
        """다른 엔진이 포커스 리스를 보유 중이면 리스가 풀릴 때까지 대기.
        락 밖에서 호출해야 함 (락 안에서 대기하면 교착 발생)."""
        deadline = time.time() + timeout
        logged = False
        while self._running and time.time() < deadline:
            if _focus_lease_hwnd == 0 or _focus_lease_hwnd == self._wincap.hwnd:
                return
            if not logged:
                self.log("[대기] 다른 봇 창고 작업 중 — 포커스 리스 해제 대기")
                logged = True
            time.sleep(0.5)

    def _ensure_focus(self) -> bool:
        """포커스 전환 확인 (최대 3회 재시도, 30ms 간격).
        _wait_for_lease() 호출 후 진입 가정 — 리스 체크는 보조용."""
        global _focus_lease_hwnd
        if _focus_lease_hwnd != 0 and _focus_lease_hwnd != self._wincap.hwnd:
            return False  # 리스 대기 없이 진입한 경우 방어
        hwnd = self._wincap.hwnd
        for _ in range(3):
            try:
                _force_foreground(hwnd)
            except Exception:
                pass
            time.sleep(0.03)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        self.log(f"[경고] 포커스 전환 실패 hwnd={hwnd}")
        return False

    # ── 직렬화 입력 헬퍼 (두 봇 동시 실행 시 Named Mutex로 충돌 방지) ──
    def _ikey(self, key, delay=0.1):
        """Lock + focus 확인 + key_down + sleep + key_up"""
        self._wait_for_lease()
        with _ilock():
            if not self._ensure_focus():
                return
            key_down(key)
            time.sleep(delay)
            key_up(key)

    def _ipress(self, key):
        """Lock + focus 확인 + press"""
        self._wait_for_lease()
        with _ilock():
            if not self._ensure_focus():
                return
            press(key)

    def _iscroll(self, direction):
        """Lock + focus 확인 + scroll"""
        self._wait_for_lease()
        with _ilock():
            if not self._ensure_focus():
                return
            scroll(direction)

    def _ikey_force(self, key: str, max_wait: float = 5.0, delay: float = 0.1):
        """포커스 확립 실패 시 최대 max_wait초 재시도 후 키 입력.
        F9/F11 등 복귀 루틴처럼 반드시 눌려야 하는 키 전용."""
        deadline = time.time() + max_wait
        while self._running and time.time() < deadline:
            with _ilock():
                if self._ensure_focus():
                    key_down(key)
                    time.sleep(delay)
                    key_up(key)
                    return
            time.sleep(0.3)
        self.log(f"[경고] {key} 입력 실패 — 포커스 미확립 (max_wait={max_wait:.0f}s)")

    def _run_pickup_until_gone(self, initial_pos, max_duration=15.0,
                               miss_confirm=4, stick_radius=100,
                               anchor_reuse_dist=180, anchor_reuse_window=3.0):
        """픽업 대상이 사라질 때까지 반복 클릭 + 재스캔.
        초기 좌표 기준 stick_radius 내 재탐지만 '타겟 존재'로 간주 (드리프트 방지).
        anchor 지속: 직전 세션 종료 후 anchor_reuse_window 초 내 + anchor_reuse_dist 이내면
        직전 anchor 재사용 → 클러스터 픽업 시 캐릭터 왔다갔다 방지."""
        now0 = time.time()
        if (self._last_pickup_anchor is not None
                and now0 - self._last_pickup_anchor_t < anchor_reuse_window):
            lx, ly = self._last_pickup_anchor
            ix0, iy0 = initial_pos
            if (lx - ix0) ** 2 + (ly - iy0) ** 2 <= anchor_reuse_dist * anchor_reuse_dist:
                self.log(f"[PICKUP] anchor 재사용 {initial_pos} → {self._last_pickup_anchor}")
                initial_pos = self._last_pickup_anchor
        self.log(f"[PICKUP] 연속 줍기 시작 → {self._last_pickup_name} pos={initial_pos}")
        self._pickup_release()   # 혹시 유지 중인 LMB 해제
        t0 = time.time()
        miss = 0
        click_count = 0
        r2 = stick_radius * stick_radius
        ix, iy = initial_pos
        sx, sy = self._wincap.get_screen_position(initial_pos)
        while self._running and time.time() - t0 < max_duration:
            with _ilock():
                self._ensure_focus()
                move_to(sx, sy)
                time.sleep(0.04)
                mouse_down("left")
                time.sleep(0.03)
                mouse_up("left")
            click_count += 1
            time.sleep(0.15)
            frame = self._wincap.get_screenshot()
            if frame is not None:
                if self._check_restart(frame):
                    return
                self._push_scan_frame(frame)
            time.sleep(0.1)
            _, pickup_new = self._find_npc()
            if pickup_new is None:
                miss += 1
            else:
                dx = pickup_new[0] - ix
                dy = pickup_new[1] - iy
                if dx * dx + dy * dy <= r2:
                    miss = 0
                    # 슬라이딩 anchor: 같은 아이템이 카메라 이동으로 화면에서 흐를 때 추적
                    ix, iy = pickup_new
                    sx, sy = self._wincap.get_screen_position(pickup_new)
                else:
                    miss += 1
            if miss >= miss_confirm:
                break
        self._last_pickup_anchor = (ix, iy)
        self._last_pickup_anchor_t = time.time()
        self.log(f"[PICKUP] 연속 줍기 종료  클릭={click_count}회  경과={time.time()-t0:.1f}s")

    def _ctrl_drag_attack(self, win_pos):
        self._pickup_release()  # 줍기 LMB 유지 중이면 안전 해제
        sx, sy = self._wincap.get_screen_position(win_pos)
        dx = int(self.cfg.drag_dist * 0.5)
        dy = int(self.cfg.drag_dist * 0.87)
        with _ilock():
            if not self._ensure_focus():
                return
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

    def _check_restart(self, frame) -> bool:
        """restart 버튼 감지 시 즉시 처리. True 반환이면 호출측은 즉시 return."""
        dead, restart_loc = self._is_dead(frame)
        if dead:
            self._handle_death(frame, restart_loc)
            return True
        return False

    def _check_weight_over(self, frame) -> bool:
        now = time.time()
        if now - self._last_weight_check_t < self.cfg.weight_check_interval:
            return False
        self._last_weight_check_t = now

        x1, y1, x2, y2 = self.cfg.weight_bar
        bar_w = x2 - x1
        if bar_w <= 0:
            return False

        # 바 ROI에서 주황색 픽셀 감지 (HSV: H=10~25, S>120, V>80)
        cy = (y1 + y2) // 2
        bar_roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(bar_roi, cv2.COLOR_BGR2HSV)
        orange_mask = (
            (hsv[:, :, 0] >= 10) & (hsv[:, :, 0] <= 25) &
            (hsv[:, :, 1] > 120) &
            (hsv[:, :, 2] > 80)
        )
        ratio = np.sum(orange_mask) / orange_mask.size
        self.log(f"[WEIGHT] 주황 비율={ratio:.3f}")
        if ratio > 0.05:
            self.log("[WEIGHT] 주황 감지 → 창고 이동")
            return True
        return False

    def _is_in_zone(self, frame) -> bool:
        if self._zone_tmpl is None:
            self.log("[ZONE] 템플릿 없음 → 통과")
            return True
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        tmpl_gray = cv2.cvtColor(self._zone_tmpl, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        self.log(f"[ZONE] score={max_val:.3f}")
        return max_val >= 0.70

    def _is_mp_full(self, frame) -> bool:
        mx, my = self.cfg.mp_full_pos
        roi = frame[my - 5:my + 5, mx - 5:mx + 5]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:,:,0] >= 80) & (hsv[:,:,0] <= 140)
                & (hsv[:,:,1] > 20) & (hsv[:,:,2] > 60))
        return np.sum(mask) / mask.size > 0.3

    def _check_hp_green_and_press(self, frame):
        """HP바가 초록이면 F8 (쿨타임 적용)"""
        now = time.time()
        if now - self._last_hp_check_t < self.cfg.hp_check_interval:
            return
        self._last_hp_check_t = now
        hx, hy = self.cfg.hp_pos
        roi = frame[hy - 3:hy + 3, hx - 5:hx + 5]
        if roi.size == 0:
            return
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 0] >= 40) & (hsv[:, :, 0] <= 85)
                & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 80))
        ratio = np.sum(mask) / mask.size
        if ratio > 0.3:
            if now - self._last_hp_f8_t < self.cfg.hp_f8_cooldown:
                return
            self._last_hp_f8_t = now
            self.log(f"[HP] 초록 감지 → F8  (비율={ratio:.2f})")
            self._ipress("f8")

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
        with _ilock():
            if not self._ensure_focus():
                return
            for ch in num_str:
                press(ch)
                time.sleep(0.05)

    def _type_location_cmd(self):
        with _ilock():
            if not self._ensure_focus():
                return
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
        self._acquire_focus_lease()
        try:
            if self.cfg.use_clan_warehouse:
                self._run_clan_warehouse()
            else:
                self._run_personal_warehouse()
        finally:
            self._release_focus_lease()

    def _run_personal_warehouse(self):
        self.log("[WAREHOUSE] 개인 창고 루틴 시작")
        self._ikey(self.cfg.scroll_key)
        time.sleep(1.0)

        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)

        self._click_move(self.cfg.warehouse_scroll_click)
        self.log(f"[WAREHOUSE] 두루마리 클릭  pos={self.cfg.warehouse_scroll_click}")
        self._interruptible_sleep(self.cfg.scroll_wait)
        if not self._running:
            return

        chk = self._wincap.get_screenshot()
        if self._is_dialog_open(chk):
            self._ikey("esc")
            time.sleep(0.5)

        self._click_move(self.cfg.warehouse_npc_click)
        self.log(f"[WAREHOUSE] 창고 지기 클릭  pos={self.cfg.warehouse_npc_click}")
        self._interruptible_sleep(2.0)
        if not self._running:
            return

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
        self._ikey(self.cfg.scroll_key)
        time.sleep(1.0)

        for _ in range(30):
            chk = self._wincap.get_screenshot()
            if self._is_dialog_open(chk):
                break
            time.sleep(0.1)
        time.sleep(0.3)

        self._click_move(self.cfg.clan_warehouse_scroll_click)
        self.log(f"[CLAN_WH] 두루마리 클릭  pos={self.cfg.clan_warehouse_scroll_click}")
        self.log(f"[CLAN_WH] 이동 대기 → {self.cfg.scroll_wait}초")
        self._interruptible_sleep(self.cfg.scroll_wait)
        if not self._running:
            return

        chk = self._wincap.get_screenshot()
        if self._is_dialog_open(chk):
            self._ikey("esc")
            time.sleep(0.5)

        self._click_move(self.cfg.clan_warehouse_npc_click)
        self.log(f"[CLAN_WH] 혈맹 창고지기 클릭  pos={self.cfg.clan_warehouse_npc_click}")
        self._interruptible_sleep(2.0)
        if not self._running:
            return

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

        self._scroll_return()
        self.log("[CLAN_WH] 혈맹 창고 루틴 완료")

    def _scroll_to_top(self, count=15):
        self.log(f"    스크롤 업 {count}회 (맨 위로)")
        for _ in range(count):
            if not self._running:
                return
            self._iscroll("up")
            time.sleep(0.2)

    def _deposit_items(self, max_scroll_down=12):
        """맨 위부터 아래로 스크롤하며 모든 대상 아이템을 맡긴다 (원패스)."""
        items = [
            (self._fruit_tmpl,    "엔트의 열매"),
            (self._stem_tmpl,     "엔트의 줄기"),
            (self._spirit_tmpl,   "정령의 돌"),
            (self._mushroom_tmpl, "버섯포자의 즙"),
            (self._mithril_tmpl,  "미스릴 원석"),
            (self._bark_tmpl,     "엔트의 껍질"),
            (self._pan_mane_tmpl, "판의 갈기털"),
        ]
        enabled_names = {d["name"] for d in self.cfg.deposit_items if d.get("enabled", True)}
        items = [(t, n) for t, n in items if t is not None and n in enabled_names]

        self._scroll_to_top()
        time.sleep(0.3)

        deposited = set()
        for step in range(max_scroll_down + 1):
            if not self._running:
                break
            frame = self._wincap.get_screenshot()
            for tmpl, name in items:
                if not self._running:
                    break
                if name in deposited:
                    continue
                pos = self._find_item(frame, tmpl, name)
                if pos:
                    self._click_move(pos)
                    time.sleep(0.5)
                    self._type_number("9999")
                    time.sleep(0.3)
                    deposited.add(name)
                    frame = self._wincap.get_screenshot()
            if len(deposited) == len(items):
                break
            if step < max_scroll_down:
                self.log(f"    스크롤 다운 {step+1}/{max_scroll_down}")
                self._iscroll("down")
                time.sleep(0.4)
        missing = [n for _, n in items if n not in deposited]
        self.log(f"    맡기기 결과: 성공 {sorted(deposited)}  미발견 {missing}")

    def _do_f9_return(self):
        """F9 → 마을 복귀 (F5×3 포함). _f11_to_zone / _scroll_return 공용."""
        self.log("[RETURN] F9 실행 → 3초 대기")
        self._ikey_force("f9")
        self._interruptible_sleep(3)
        if not self._running:
            return
        self.log("[RETURN] 바투 F5 × 3회 시작")
        for i in range(1, 4):
            if not self._running:
                return
            self._ikey_force("f5")
            self.log(f"[RETURN] F5 ({i}/3)")
            self._interruptible_sleep(3)
        self.log("[RETURN] 5초 대기")
        self._interruptible_sleep(5)

    def _f11_to_zone(self, max_retry: int = 5):
        """F11 순간이동 후 요정 숲 확인. 실패 시 F9 복귀 후 재시도."""
        for retry in range(max_retry):
            if not self._running:
                return
            self.log(f"[F11] 순간이동 시도 ({retry+1}/{max_retry})")
            self._ikey_force("f11")
            self._interruptible_sleep(2)
            if not self._running:
                return
            frame = self._wincap.get_screenshot()
            if frame is None or self._is_in_zone(frame):
                self.log("[F11] 요정 숲 확인 완료")
                return
            self.log("[F11] 요정 숲 아님 → F9 복귀 후 재시도")
            self._do_f9_return()
        self.log("[F11] 최대 재시도 초과 → 현재 위치에서 진행")

    def _scroll_return(self):
        max_retry = 5
        for retry in range(max_retry):
            if not self._running:
                return
            self._do_f9_return()
            if not self._running:
                return
            self._f11_to_zone()
            if self._running:
                self.log("[RETURN] 요정 숲 확인 → 패트롤 시작")
                return
        self.log("[RETURN] 최대 재시도 초과 → 현재 위치에서 패트롤 시작")

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
                'extra_npc_enabled': self.cfg.extra_npc_enabled,
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
            self._ikey("esc")
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
                        self._run_pickup_until_gone(pickup)
                    else:
                        self._pickup_release()
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
        self._pickup_release()  # 줍기 LMB 유지 중이면 리셋
        rh, rw = self._restart_tmpl.shape[:2]
        rx = restart_loc[0] + rw // 2
        ry = restart_loc[1] + rh // 2
        sx, sy = self._wincap.get_screen_position((rx, ry))

        while self._running:
            with _ilock():
                self._ensure_focus()
                move_to(sx, sy)
                time.sleep(0.1)
                mouse_down("left")
                time.sleep(0.03)
                mouse_up("left")
            self.log(f"[DEAD] 사망 감지 → Restart 클릭  ({rx},{ry})")
            time.sleep(5.0)
            chk = self._wincap.get_screenshot()
            if chk is None:
                continue
            still_dead, new_loc = self._is_dead(chk)
            if not still_dead:
                break
            self.log("[DEAD] Restart 버튼 아직 있음 → 재클릭")
            rh2, rw2 = self._restart_tmpl.shape[:2]
            rx = new_loc[0] + rw2 // 2
            ry = new_loc[1] + rh2 // 2
            sx, sy = self._wincap.get_screen_position((rx, ry))

        self.npc_pos = None
        self._f11_to_zone()
        self._last_npc_found_t = time.time()
        self._last_weight_check_t = time.time()
        self._set_state("PATROL")

    def _handle_revive_fail(self):
        with _ilock():
            if not self._ensure_focus():
                return
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
        self._f11_to_zone()
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
        try:
            self._main_loop_inner()
        except Exception as e:
            import traceback
            self.log(f"[오류] 봇 스레드 예외 발생 → 중지\n{traceback.format_exc()}")
            self._running = False

    def _main_loop_inner(self):
        self._last_npc_found_t = time.time()
        self._last_weight_check_t = 0.0
        self._last_stuck_check_t = 0.0
        self._last_zone_check_t = time.time()
        self._patrol_history = []
        self._patrol_no_move_count = 0
        self._dir_idx = random.randint(0, 7)
        self._patrol_steps = 0
        self._scan_pause_until = 0.0
        self._set_state("PATROL")
        self.log("봇 시작 (템플릿 매칭)  P=일시정지  Q=종료  F12=긴급종료")
        self.log("3초 후 시작...")
        self._interruptible_sleep(3.0)

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
                        'extra_npc_enabled': self.cfg.extra_npc_enabled,
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
                        self._ikey("esc", delay=0.3)
                        time.sleep(1.0)
                        self._handle_revive_fail()
                        continue
                    with _ilock():
                        if not self._ensure_focus():
                            continue
                        key_up("ctrl")
                        mouse_up("left")
                        self._pickup_lmb_held = False  # 대화창 처리로 LMB 해제됨 → 플래그 동기화
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

            # ── HP 초록 감지 → F8 ──
            self._check_hp_green_and_press(frame)

            # ── 무게 초과 ──
            if self.state in ("PATROL", "FIGHTING") and self._check_weight_over(frame):
                self._run_warehouse()
                self.npc_pos = None
                self._last_weight_check_t = time.time()
                self._set_state("PATROL")
                continue

            # ── 30초마다 요정 숲 체크 ──
            if (self._zone_tmpl is not None
                    and self.state in ("PATROL", "APPROACH", "FIGHTING")
                    and now - self._last_zone_check_t >= 30.0):
                self._last_zone_check_t = now
                if not self._is_in_zone(frame):
                    self.log("[ZONE] 요정 숲 이탈 감지 → F9 복귀")
                    self._scroll_return()
                    self.npc_pos = None
                    self._last_npc_found_t = time.time()
                    self._last_zone_check_t = time.time()
                    self._set_state("PATROL")
                    continue
                else:
                    self.log("[ZONE] 요정 숲 확인 OK")

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
        with _ilock():
            key_up("ctrl")
            mouse_up("left")
        self._pickup_lmb_held = False
        self.state = "IDLE"
        self.log("봇 중지됨")

    # ──────────────────────────────────────────
    # 상태별 로직
    # ──────────────────────────────────────────
    def _do_patrol(self, frame, now, elapsed):
        npc, pickup = self._find_npc()
        if pickup is not None:
            self._run_pickup_until_gone(pickup)
            return   # 사라질 때까지 줍고 나서 patrol 로직 진입 금지
        else:
            self._pickup_release()
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
                    self.log(f"[RETURN] {self.cfg.npc_not_found_timeout:.0f}초간 엔트 미발견 → F11 순간이동")
                    self._f11_to_zone()
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
                        self.log(f"[PICKUP] {self._last_pickup_name} 발견! 줍기  pos={pickup_chk}")
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
        # 픽업 최우선: APPROACH 중이라도 아이템 보이면 중단하고 줍기
        _, pickup = self._find_npc()
        if pickup is not None:
            self.log(f"[PICKUP] {self._last_pickup_name} 발견! 접근 중단 → 줍기  pos={pickup}")
            self._run_pickup_until_gone(pickup)
            return
        else:
            self._pickup_release()

        dlg_r = cv2.matchTemplate(frame, self._close_tmpl, cv2.TM_CCOEFF_NORMED)
        _, ds, _, _ = cv2.minMaxLoc(dlg_r)
        if ds >= 0.7:
            self._ikey("esc")
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
            self.log(f"[PICKUP] {self._last_pickup_name} 발견! 줍기  pos={pickup}")
            self._run_pickup_until_gone(pickup)
            return   # 사라질 때까지 줍고 나서 공격 로직 진입 금지
        else:
            self._pickup_release()
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

        # 아이템 줍기
        if pickup is not None:
            self.log(f"[PICKUP] {self._last_pickup_name} 발견! 공격 중단 → 줍기  pos={pickup}")
            with _ilock():
                key_up("ctrl")
                mouse_up("left")
            self._pickup_lmb_held = False  # 공격 LMB 해제와 함께 상태 리셋
            time.sleep(0.3)
            self._run_pickup_until_gone(pickup)
            if self.npc_pos is not None:
                self.log("[PICKUP] 줍기 완료 → 엔트 재공격")
                self._click_move(self.npc_pos)
                time.sleep(1.5)
                chk = self._wincap.get_screenshot()
                if self._is_dialog_open(chk):
                    self._ikey("esc")
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
