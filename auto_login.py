"""
리니지 클래식 자동 접속
- GUI: 서버, 계정, 비밀번호, 캐릭터 슬롯 설정
- 자동: 런처 실행 → 동의서 → 서버 → 계정 → 캐릭터 → 접속
"""
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import subprocess
import time
import threading
import ctypes
import cv2
import numpy as np
import win32gui

# ─── 상수 ──────────────────────────────────────────────
CONFIG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_login_config.json")
LAUNCHER_CMD = r'"C:\Program Files (x86)\NCSOFT\Purple\PurpleLauncher.exe" --game-id L1C_KR_L_GA_PURPLE'
WINDOW_NAME  = "Lineage Classic"
TMPL_THRESHOLD = 0.7   # 템플릿 매칭 최소 신뢰도
TMPL_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "login")

# 서버 목록 (페이지별)
SERVERS_PAGE1 = [
    "대포르츄", "켄라우헬", "갈리언", "이살토레",
    "조우", "하딘", "케레니스", "오웬",
    "크리스티", "아론", "가드리아", "군터",
    "아스테어", "듀크데월", "발센", "어레인",
    "게스틀", "세바스찬",
]
SERVERS_PAGE2 = [
    "대전", "아인하자드", "파이그리오", "에바",
    "사이하", "마프른", "린텔", "하이네", "로엔그린",
]
ALL_SERVERS = SERVERS_PAGE1 + SERVERS_PAGE2

# ─── 고정 좌표 (스크린샷 1282x1006 기준, 타이틀바 ~32px 제외) ───
# 비율로 저장하여 다른 해상도에서도 대응
# 서버 격자: 좌측 열 x≈0.431, 우측 열 x≈0.579
# 첫 행 y≈0.301, 행 간격 ≈0.028
_SRV_LX = 0.431    # 좌측 열 x 비율
_SRV_RX = 0.579    # 우측 열 x 비율
_SRV_Y0 = 0.291    # 첫 행 y 비율 (보정)
_SRV_DY = 0.0276   # 행 간격 비율 (보정)
_PAGE2_X = 0.496   # 페이지2 버튼 x 비율
_PAGE2_Y = 0.570   # 페이지2 버튼 y 비율

# 서버 → (페이지, 열, 행) 매핑
SERVER_GRID = {}
for i, name in enumerate(SERVERS_PAGE1):
    col = i % 2       # 0=좌, 1=우
    row = i // 2       # 0~8
    SERVER_GRID[name] = (1, col, row)
for i, name in enumerate(SERVERS_PAGE2):
    col = i % 2
    row = i // 2
    SERVER_GRID[name] = (2, col, row)

# Account/Password 화면 고정 좌표 비율
_ACC_FIELD_X  = 0.733   # Account 입력 필드 x
_ACC_FIELD_Y  = 0.462   # Account 입력 필드 y
_PW_FIELD_X   = 0.733   # Password 입력 필드 x
_PW_FIELD_Y   = 0.522   # Password 입력 필드 y
_OK_LOGIN_X   = 0.798   # ok 버튼 x (로그인 화면)
_OK_LOGIN_Y   = 0.758   # ok 버튼 y

# 캐릭터 슬롯 위치 비율 (캐릭터 선택 화면)
_CHAR_SLOTS = {
    1: (0.30, 0.33),    # 1번째 캐릭터 (왼쪽)
    2: (0.45, 0.33),    # 2번째 캐릭터 (중앙)
    3: (0.60, 0.33),    # 3번째 캐릭터 (오른쪽)
}

# DPI 인식
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


# ─── 설정 저장/로드 ───────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"server": "", "account": "", "password": "", "character": 1}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ─── 유틸 ─────────────────────────────────────────────
def find_window(name, timeout=120):
    """창 이름에 name이 포함된 윈도우가 나타날 때까지 대기"""
    start = time.time()
    while time.time() - start < timeout:
        found = None
        def cb(hwnd, _):
            nonlocal found
            if win32gui.IsWindowVisible(hwnd) and name in win32gui.GetWindowText(hwnd):
                found = hwnd
                return False
            return True
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass
        if found:
            return found
        time.sleep(2)
    return None


def grab_frame(hwnd):
    """윈도우 캡처 (BitBlt 방식, dxcam 없이 간단하게)"""
    import win32ui, win32con
    client = win32gui.GetClientRect(hwnd)
    w = client[2] - client[0]
    h = client[3] - client[1]
    if w <= 0 or h <= 0:
        return None

    pt = win32gui.ClientToScreen(hwnd, (0, 0))
    wr = win32gui.GetWindowRect(hwnd)
    cx = pt[0] - wr[0]
    cy = pt[1] - wr[1]

    wDC = win32gui.GetWindowDC(hwnd)
    dcObj = win32ui.CreateDCFromHandle(wDC)
    cDC = dcObj.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dcObj, w, h)
    cDC.SelectObject(bmp)
    cDC.BitBlt((0, 0), (w, h), dcObj, (cx, cy), win32con.SRCCOPY)
    arr = bmp.GetBitmapBits(True)
    img = np.frombuffer(arr, dtype="uint8").reshape(h, w, 4)
    cDC.DeleteDC()
    dcObj.DeleteDC()
    win32gui.ReleaseDC(hwnd, wDC)
    win32gui.DeleteObject(bmp.GetHandle())
    return np.ascontiguousarray(img[..., :3])


def screen_pos(hwnd, win_pos):
    """윈도우 내 좌표 → 화면 절대 좌표"""
    pt = win32gui.ClientToScreen(hwnd, (0, 0))
    return (win_pos[0] + pt[0], win_pos[1] + pt[1])


# ─── 자동 접속 로직 ───────────────────────────────────
def run_auto_login(cfg, log_fn):
    """자동 접속 전체 흐름"""
    from interception import (
        auto_capture_devices, set_devices,
        key_down, key_up, press,
        move_to, mouse_down, mouse_up,
    )

    def focus_game(hwnd):
        """게임 창을 포커스로 가져오기"""
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.3)

    def save_debug(frame, name):
        """디버그 프레임 저장"""
        path = f"C:/BOT/debug_{name}.png"
        cv2.imwrite(path, frame)
        log_fn(f"    [debug] 저장: {path}")

    def click_at(hwnd, win_pos, delay=0.1):
        focus_game(hwnd)
        sx, sy = screen_pos(hwnd, win_pos)
        log_fn(f"    [click] win=({win_pos[0]},{win_pos[1]}) → screen=({sx},{sy})")
        move_to(sx, sy)
        time.sleep(delay)
        mouse_down("left")
        time.sleep(0.05)
        mouse_up("left")
        time.sleep(0.3)

    def wait_screen_change(hwnd, before_frame, timeout=10):
        """화면이 변할 때까지 대기. True=변함, False=타임아웃"""
        start = time.time()
        while time.time() - start < timeout:
            after = grab_frame(hwnd)
            if after is None:
                time.sleep(0.5)
                continue
            diff = cv2.absdiff(before_frame, after)
            diff_mean = np.mean(diff)
            if diff_mean > 15:  # 화면이 충분히 바뀜
                log_fn(f"    [화면 전환 감지] diff={diff_mean:.1f}")
                return True
            time.sleep(0.5)
        log_fn(f"    [화면 전환 없음] 타임아웃 {timeout}초")
        return False

    def type_text(text):
        for ch in text:
            press(ch)
            time.sleep(0.05)

    # 템플릿 이미지 로드
    tmpl_agree = cv2.imread(f"{TMPL_DIR}/agree_btn.png")
    tmpl_ok    = cv2.imread(f"{TMPL_DIR}/ok_btn.png")
    tmpl_ok_login = cv2.imread(f"{TMPL_DIR}/ok_login_btn.png")

    def tmpl_find(frame, tmpl):
        """프레임에서 템플릿을 찾아 중심 (cx, cy, 신뢰도) 반환. 없으면 None."""
        if tmpl is None or frame is None:
            return None
        result = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= TMPL_THRESHOLD:
            cx = max_loc[0] + tmpl.shape[1] // 2
            cy = max_loc[1] + tmpl.shape[0] // 2
            return (cx, cy, max_val)
        return None

    def wait_and_click_tmpl(hwnd, tmpl, label, timeout=60):
        """화면에서 템플릿이 나타날 때까지 대기 후 클릭"""
        start = time.time()
        while time.time() - start < timeout:
            frame = grab_frame(hwnd)
            if frame is None:
                time.sleep(1)
                continue
            match = tmpl_find(frame, tmpl)
            if match:
                cx, cy, conf = match
                log_fn(f"  [{label}] 발견 (신뢰도={conf:.3f}) → 클릭 ({cx},{cy})")
                click_at(hwnd, (cx, cy))
                return True
            time.sleep(1.5)
        log_fn(f"  [{label}] 못 찾음 (타임아웃 {timeout}초)")
        return False

    def wait_for_tmpl(hwnd, tmpl, label, timeout=60):
        """화면에서 템플릿이 나타날 때까지 대기 (클릭 없음)"""
        start = time.time()
        while time.time() - start < timeout:
            frame = grab_frame(hwnd)
            if frame is None:
                time.sleep(1)
                continue
            match = tmpl_find(frame, tmpl)
            if match:
                return match
            time.sleep(1.5)
        return None

    def get_client_size(hwnd):
        """클라이언트 영역 크기"""
        r = win32gui.GetClientRect(hwnd)
        return (r[2] - r[0], r[3] - r[1])

    def ratio_pos(hwnd, rx, ry):
        """비율 좌표 → 윈도우 내 픽셀 좌표"""
        w, h = get_client_size(hwnd)
        return (int(w * rx), int(h * ry))

    def get_server_pos(hwnd, server_name):
        """서버 이름 → (page, 클릭 좌표)"""
        if server_name not in SERVER_GRID:
            return None, None
        page, col, row = SERVER_GRID[server_name]
        x_ratio = _SRV_RX if col == 1 else _SRV_LX
        y_ratio = _SRV_Y0 + row * _SRV_DY
        return page, ratio_pos(hwnd, x_ratio, y_ratio)

    # ── 시작 ──
    log_fn("=== 자동 접속 시작 ===")

    # 1. 런처 실행
    log_fn("[1/6] 런처 실행 중...")
    subprocess.Popen(LAUNCHER_CMD, shell=True)

    # 2. 게임 창 대기
    log_fn("[2/6] 게임 창 대기 중...")
    hwnd = find_window(WINDOW_NAME, timeout=120)
    if not hwnd:
        log_fn("게임 창을 찾을 수 없습니다. 종료.")
        return False
    log_fn(f"  게임 창 감지 (hwnd={hwnd})")
    w, h = get_client_size(hwnd)
    log_fn(f"  클라이언트 영역: {w}x{h}")

    # 디바이스 초기화
    log_fn("  디바이스 초기화...")
    auto_capture_devices(keyboard=True, mouse=True, verbose=True)
    set_devices(keyboard=0)

    # 템플릿 확인
    if tmpl_agree is None or tmpl_ok is None:
        log_fn(f"  템플릿 파일 없음! {TMPL_DIR}/ 확인 필요")
        return False
    log_fn("  템플릿 로드 완료")

    # 충분히 로딩될 때까지 대기
    time.sleep(5)

    # 3. 이용자 동의서 — 템플릿 매칭
    log_fn("[3/6] 이용자 동의서 대기...")

    # 단계 A: "동의합니다" 버튼이 나타날 때까지 대기
    log_fn("  동의서 화면 로딩 대기...")
    found_pos = None
    for wait in range(60):  # 최대 120초
        frame = grab_frame(hwnd)
        if frame is None:
            time.sleep(2)
            continue
        match = tmpl_find(frame, tmpl_agree)
        if match:
            found_pos = (match[0], match[1])
            save_debug(frame, "agree_found")
            log_fn(f"  '동의합니다' 발견! ({match[0]},{match[1]}) 신뢰도={match[2]:.3f}")
            break
        if wait % 5 == 0:
            save_debug(frame, f"agree_wait_{wait}")
            log_fn(f"  아직 로딩 중... ({wait*2}초)")
        time.sleep(2)

    if not found_pos:
        log_fn("동의서 화면이 나타나지 않았습니다 (120초 타임아웃). 종료.")
        return False

    # 단계 B: 클릭 → 사라질 때까지 재시도
    for attempt in range(5):
        log_fn(f"  클릭 시도 {attempt+1}/5")
        click_at(hwnd, found_pos)
        time.sleep(3)

        # 버튼이 사라졌는지 확인
        after = grab_frame(hwnd)
        if after is not None:
            check = tmpl_find(after, tmpl_agree)
            if not check:
                log_fn("  동의서 클릭 성공!")
                break
        log_fn(f"  아직 동의서 화면 → 재시도")
    else:
        log_fn("동의서 클릭 5회 실패. 종료.")
        return False
    time.sleep(2)

    # 4. 서버 리스트 — 고정 좌표 사용
    server = cfg["server"]
    log_fn(f"[4/6] 서버 선택: {server}")

    # 서버 리스트 화면 대기 (3초 추가 대기)
    time.sleep(3)

    # 디버그: 서버 리스트 화면 저장
    srv_frame = grab_frame(hwnd)
    if srv_frame is not None:
        save_debug(srv_frame, "server_list")

    page, srv_pos = get_server_pos(hwnd, server)
    if srv_pos is None:
        log_fn(f"  서버 '{server}'가 목록에 없습니다.")
        return False

    # 서버가 2페이지면 페이지 전환
    if page == 2:
        log_fn("  2페이지로 이동...")
        p2_pos = ratio_pos(hwnd, _PAGE2_X, _PAGE2_Y)
        click_at(hwnd, p2_pos)
        time.sleep(2)
        # 2페이지 화면 저장
        srv_frame2 = grab_frame(hwnd)
        if srv_frame2 is not None:
            save_debug(srv_frame2, "server_list_p2")

    log_fn(f"  서버 '{server}' 좌표: ({srv_pos[0]},{srv_pos[1]})")
    click_at(hwnd, srv_pos)
    time.sleep(1)

    # 서버 클릭 후 화면 확인
    after_srv = grab_frame(hwnd)
    if after_srv is not None:
        save_debug(after_srv, "after_server_click")
    log_fn("  서버 선택 완료")
    time.sleep(3)

    # 5. Account / Password
    log_fn("[5/6] 로그인 화면...")

    # Account 화면이 뜰 때까지 대기 (ok 버튼 템플릿으로 감지)
    login_ok_tmpl = tmpl_ok_login if tmpl_ok_login is not None else tmpl_ok
    wait_for_tmpl(hwnd, login_ok_tmpl, "ok(로그인)", timeout=30)
    time.sleep(1)

    # 계정/비번이 설정되어 있으면 입력, 아니면 기존 저장값 사용
    if cfg.get("account") and cfg.get("password"):
        log_fn("  계정/비밀번호 입력...")
        # Account 입력 필드 클릭
        acc_pos = ratio_pos(hwnd, _ACC_FIELD_X, _ACC_FIELD_Y)
        click_at(hwnd, acc_pos)
        time.sleep(0.3)
        key_down("ctrl"); time.sleep(0.05); press("a"); time.sleep(0.05); key_up("ctrl")
        time.sleep(0.2)
        type_text(cfg["account"])
        time.sleep(0.3)

        # Password 입력 필드 클릭
        pw_pos = ratio_pos(hwnd, _PW_FIELD_X, _PW_FIELD_Y)
        click_at(hwnd, pw_pos)
        time.sleep(0.3)
        key_down("ctrl"); time.sleep(0.05); press("a"); time.sleep(0.05); key_up("ctrl")
        time.sleep(0.2)
        type_text(cfg["password"])
        time.sleep(0.5)
    else:
        log_fn("  계정/비번 저장됨 → 바로 ok")

    # ok 클릭
    ok_pos = ratio_pos(hwnd, _OK_LOGIN_X, _OK_LOGIN_Y)
    log_fn(f"  ok 클릭 ({ok_pos[0]},{ok_pos[1]})")
    click_at(hwnd, ok_pos)
    log_fn("  로그인 완료")
    time.sleep(5)

    # 6. 캐릭터 선택 — 슬롯 직접 클릭 → ok
    char_slot = cfg.get("character", 1)
    log_fn(f"[6/6] 캐릭터 {char_slot}번째 선택...")

    # 캐릭터 화면 대기
    time.sleep(3)

    # 디버그: 캐릭터 선택 화면 저장
    char_frame = grab_frame(hwnd)
    if char_frame is not None:
        save_debug(char_frame, "character_select")

    # 캐릭터 슬롯 클릭
    slot_ratio = _CHAR_SLOTS.get(char_slot, _CHAR_SLOTS[1])
    char_pos = ratio_pos(hwnd, slot_ratio[0], slot_ratio[1])
    log_fn(f"  캐릭터 {char_slot}번 슬롯 클릭 ({char_pos[0]},{char_pos[1]})")
    click_at(hwnd, char_pos)
    time.sleep(2)

    # ok 클릭 (템플릿 매칭)
    if not wait_and_click_tmpl(hwnd, tmpl_ok, "ok(캐릭터)", timeout=15):
        press("return")
    log_fn("  캐릭터 선택 완료")
    time.sleep(3)

    log_fn("=== 접속 완료! ===")
    return True


# ─── 외부 연동용 API ──────────────────────────────────
def is_game_running():
    """게임 창이 존재하는지 확인 (대기 없이 즉시)"""
    return find_window(WINDOW_NAME, timeout=3) is not None


def check_and_login(log_fn=None):
    """게임이 안 켜져 있으면 자동 로그인. 이미 켜져 있으면 스킵.
    log_fn: 로그 콜백 (없으면 print 사용)
    반환: True=게임 준비됨, False=실패
    """
    if log_fn is None:
        log_fn = print

    # 이미 게임이 켜져 있는지 확인
    hwnd = find_window(WINDOW_NAME, timeout=3)
    if hwnd:
        log_fn("[자동접속] 게임 이미 실행 중 → 스킵")
        return True

    # 설정 로드
    cfg = load_config()
    if not cfg.get("server"):
        log_fn("[자동접속] auto_login_config.json에 서버 미설정 → 스킵")
        return False

    log_fn("[자동접속] 게임 미실행 → 자동 로그인 시작")
    return run_auto_login(cfg, log_fn)


# ─── GUI ───────────────────────────────────────────────
class AutoLoginGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("리니지 클래식 자동 접속")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        cfg = load_config()

        # ── 설정 프레임 ──
        frame = ttk.LabelFrame(self.root, text="접속 설정", padding=10)
        frame.pack(padx=10, pady=10, fill="both")

        # 서버
        ttk.Label(frame, text="서버:").grid(row=0, column=0, sticky="w", pady=4)
        self.server_var = tk.StringVar(value=cfg.get("server", ""))
        self.server_combo = ttk.Combobox(
            frame, textvariable=self.server_var,
            values=ALL_SERVERS, width=22, state="readonly"
        )
        self.server_combo.grid(row=0, column=1, columnspan=3, sticky="w", pady=4)

        # 계정
        ttk.Label(frame, text="계정:").grid(row=1, column=0, sticky="w", pady=4)
        self.account_var = tk.StringVar(value=cfg.get("account", ""))
        ttk.Entry(frame, textvariable=self.account_var, width=25).grid(
            row=1, column=1, columnspan=3, sticky="w", pady=4
        )

        # 비밀번호
        ttk.Label(frame, text="비밀번호:").grid(row=2, column=0, sticky="w", pady=4)
        self.password_var = tk.StringVar(value=cfg.get("password", ""))
        ttk.Entry(frame, textvariable=self.password_var, show="*", width=25).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=4
        )

        # 캐릭터
        ttk.Label(frame, text="캐릭터:").grid(row=3, column=0, sticky="w", pady=4)
        self.char_var = tk.IntVar(value=cfg.get("character", 1))
        for i in range(1, 4):
            ttk.Radiobutton(
                frame, text=f"{i}번째", variable=self.char_var, value=i
            ).grid(row=3, column=i, pady=4)

        # ── 버튼 프레임 ──
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=(0, 5))

        self.start_btn = ttk.Button(btn_frame, text="접속 시작", command=self.start)
        self.start_btn.pack(side="left", padx=5)

        ttk.Button(btn_frame, text="설정 저장", command=self.save).pack(side="left", padx=5)

        # ── 로그 ──
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=5)
        log_frame.pack(padx=10, pady=(0, 10), fill="both")

        self.log_text = tk.Text(log_frame, height=10, width=45, state="disabled",
                                font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.root.mainloop()

    def log(self, msg):
        """로그 추가 (스레드 안전)"""
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    def save(self):
        cfg = {
            "server": self.server_var.get(),
            "account": self.account_var.get(),
            "password": self.password_var.get(),
            "character": self.char_var.get(),
        }
        save_config(cfg)
        self.log("설정 저장 완료")

    def start(self):
        # 유효성 검사
        if not self.server_var.get():
            messagebox.showwarning("경고", "서버를 선택해주세요")
            return
        # 계정/비번 비어있으면 게임 저장값 사용 (입력 안 함)

        self.save()
        cfg = load_config()

        self.start_btn.config(state="disabled")
        self.log("접속 준비 중...")

        # GUI 최소화 (게임 클릭 방해 방지)
        self.root.iconify()

        def worker():
            try:
                run_auto_login(cfg, self.log)
            except Exception as e:
                self.log(f"오류: {e}")
            finally:
                self.root.after(0, lambda: (
                    self.root.deiconify(),
                    self.start_btn.config(state="normal"),
                ))

        t = threading.Thread(target=worker, daemon=True)
        t.start()


# ─── 실행 ──────────────────────────────────────────────
if __name__ == "__main__":
    AutoLoginGUI()
