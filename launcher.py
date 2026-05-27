"""
Ent Bot Launcher
- PC별 라이선스 만료일 체크 (NAS licenses.json)
- 오프라인 3일 유예
- 업데이트 체크 + 앱 실행
"""
import os
import sys
import json
import uuid
import base64
import shutil
import zipfile
import datetime
import subprocess
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
def _get_base_dir() -> str:
    # PyInstaller onefile: sys._MEIPASS 존재 + sys.executable = 실제 exe 경로
    if hasattr(sys, "_MEIPASS"):
        return os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()

BASE_DIR = _get_base_dir()

APP_DIR      = os.path.join(BASE_DIR, "app")
CONFIG_FILE  = os.path.join(BASE_DIR, "launcher_config.json")
VERSION_FILE = os.path.join(BASE_DIR, "version.txt")
LICENSE_CACHE= os.path.join(BASE_DIR, ".lic")
APP_ENTRY    = os.path.join(APP_DIR, "ent_bot_gui_dual.py")
UPDATE_ZIP   = os.path.join(BASE_DIR, "_update_tmp.zip")

KEEP_USER_FILES = {"ent_config.json", "ent_config2.json", "auto_login_config.json"}
OFFLINE_GRACE_DAYS = 3

# ---------------------------------------------------------------------------
# Machine ID
# ---------------------------------------------------------------------------
def get_machine_id() -> str:
    """MAC 주소 기반 고유 ID (12자리 hex)"""
    mac = uuid.getnode()
    return format(mac, "012x")

# ---------------------------------------------------------------------------
# 라이선스 캐시 (단순 XOR + base64)
# ---------------------------------------------------------------------------
def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def _mid_key() -> bytes:
    return get_machine_id().encode()

def save_license_cache(expire: str, last_check: str):
    payload = json.dumps({"expire": expire, "last_check": last_check}).encode()
    encoded = base64.b64encode(_xor_bytes(payload, _mid_key()))
    with open(LICENSE_CACHE, "wb") as f:
        f.write(encoded)

def load_license_cache() -> dict | None:
    if not os.path.exists(LICENSE_CACHE):
        return None
    try:
        raw = base64.b64decode(open(LICENSE_CACHE, "rb").read())
        return json.loads(_xor_bytes(raw, _mid_key()).decode())
    except Exception:
        return None

# ---------------------------------------------------------------------------
# 라이선스 체크
# ---------------------------------------------------------------------------
class LicenseResult:
    OK      = "ok"
    EXPIRED = "expired"
    UNKNOWN = "unknown"   # 등록 안 된 PC
    OFFLINE = "offline"   # 서버 연결 불가 + 유예 기간 내
    BLOCKED = "blocked"   # 서버 연결 불가 + 유예 기간 초과

def check_license(nas_url: str, auth) -> tuple[str, str]:
    """
    Returns (LicenseResult, expire_date_or_message)
    """
    mid = get_machine_id()
    today = datetime.date.today()

    # ── 서버에서 체크 ──────────────────────────────────────────────────
    try:
        r = requests.get(f"{nas_url}/licenses.json", auth=auth, timeout=8)
        r.raise_for_status()
        licenses: dict = r.json()

        expire_str = licenses.get(mid) or licenses.get("*")
        if not expire_str:
            return LicenseResult.UNKNOWN, mid

        expire = datetime.date.fromisoformat(expire_str)
        if today > expire:
            return LicenseResult.EXPIRED, expire_str

        # 유효 → 캐시 저장
        save_license_cache(expire_str, today.isoformat())
        return LicenseResult.OK, expire_str

    except requests.exceptions.ConnectionError:
        pass
    except Exception as e:
        pass

    # ── 오프라인: 캐시로 유예 ────────────────────────────────────────
    cache = load_license_cache()
    if cache:
        expire_str  = cache.get("expire", "")
        last_check  = cache.get("last_check", "")
        try:
            expire     = datetime.date.fromisoformat(expire_str)
            last_dt    = datetime.date.fromisoformat(last_check)
            grace_left = OFFLINE_GRACE_DAYS - (today - last_dt).days

            if today > expire:
                return LicenseResult.EXPIRED, expire_str
            if grace_left >= 0:
                return LicenseResult.OFFLINE, expire_str
        except Exception:
            pass

    return LicenseResult.BLOCKED, ""

# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_current_version() -> str:
    if os.path.exists(VERSION_FILE):
        return open(VERSION_FILE, encoding="utf-8").read().strip()
    return "0.0.0"

def save_version(ver: str):
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(ver)

def find_python() -> str | None:
    candidates = []
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p and "WindowsApps" not in p:
            candidates.append(p)
    for user_dir in [os.environ.get("LOCALAPPDATA", "")]:
        base = os.path.join(user_dir, "Programs", "Python")
        if os.path.isdir(base):
            for sub in sorted(os.listdir(base), reverse=True):
                exe = os.path.join(base, sub, "python.exe")
                if os.path.isfile(exe):
                    candidates.append(exe)
    for ver in ("312", "311", "310", "39", "38"):
        for root in ("C:/Python", "D:/Python"):
            exe = f"{root}{ver}/python.exe"
            if os.path.isfile(exe):
                candidates.append(exe)
    return candidates[0] if candidates else None

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def elevate_if_needed():
    if not is_admin():
        exe  = sys.executable
        args = " ".join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
        sys.exit(0)

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class LauncherApp:
    def __init__(self):
        self.cfg = load_config()
        self._updating    = False
        self._licensed    = False
        self._expire_str  = ""

        self.root = tk.Tk()
        self.root.title("Ent Bot Launcher")
        self.root.geometry("480x400")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e1e")
        try:
            self.root.iconbitmap(os.path.join(BASE_DIR, "web_icon.ico"))
        except Exception:
            pass

        self._build_ui()
        self.root.after(400, self._start_full_check)

    # ------------------------------------------------------------------
    def _build_ui(self):
        BG, FG = "#1e1e1e", "#e0e0e0"
        EBGR   = "#2d2d2d"

        tk.Label(self.root, text="Ent Bot Launcher",
                 font=("맑은 고딕", 14, "bold"), bg=BG, fg="#76c7f0").pack(pady=(14, 2))

        # ── Machine ID ──────────────────────────────────────────────
        mid_frame = tk.Frame(self.root, bg=BG)
        mid_frame.pack(fill="x", padx=14)
        tk.Label(mid_frame, text="PC ID:", bg=BG, fg="#888",
                 font=("Consolas", 8)).pack(side="left")
        mid_val = tk.Label(mid_frame, text=get_machine_id(),
                           bg=BG, fg="#aaaaaa", font=("Consolas", 8))
        mid_val.pack(side="left", padx=4)
        tk.Button(mid_frame, text="복사", bg="#333", fg=FG, relief="flat",
                  font=("맑은 고딕", 7),
                  command=lambda: self._copy_to_clipboard(get_machine_id())
                  ).pack(side="left")

        # ── 라이선스 상태 ──────────────────────────────────────────
        lic_frame = tk.Frame(self.root, bg=BG)
        lic_frame.pack(fill="x", padx=14, pady=2)
        tk.Label(lic_frame, text="라이선스:", bg=BG, fg=FG,
                 font=("맑은 고딕", 9)).pack(side="left")
        self.lbl_lic = tk.Label(lic_frame, text="확인 중...",
                                bg=BG, fg="#ffcc44", font=("맑은 고딕", 9, "bold"))
        self.lbl_lic.pack(side="left", padx=6)

        # ── 버전 ────────────────────────────────────────────────────
        ver_frame = tk.Frame(self.root, bg=BG)
        ver_frame.pack(fill="x", padx=14)
        tk.Label(ver_frame, text="현재 버전:", bg=BG, fg=FG,
                 font=("맑은 고딕", 9)).pack(side="left")
        self.lbl_ver = tk.Label(ver_frame, text=get_current_version(),
                                bg=BG, fg="#aaffaa", font=("맑은 고딕", 9, "bold"))
        self.lbl_ver.pack(side="left", padx=4)
        self.lbl_remote_ver = tk.Label(ver_frame, text="",
                                       bg=BG, fg="#ffcc44", font=("맑은 고딕", 9))
        self.lbl_remote_ver.pack(side="left", padx=4)

        # ── NAS URL ─────────────────────────────────────────────────
        nas_frame = tk.Frame(self.root, bg=BG)
        nas_frame.pack(fill="x", padx=14)
        tk.Label(nas_frame, text="NAS:", bg=BG, fg="#555",
                 font=("맑은 고딕", 8)).pack(side="left")
        tk.Label(nas_frame, text=self.cfg.get("nas_url", "(미설정)"),
                 bg=BG, fg="#555", font=("맑은 고딕", 8)).pack(side="left", padx=4)

        # ── 진행 바 ─────────────────────────────────────────────────
        self.progress = ttk.Progressbar(self.root, length=450, mode="indeterminate")
        self.progress.pack(padx=14, pady=6)

        # ── 상태 ────────────────────────────────────────────────────
        self.lbl_status = tk.Label(self.root, text="시작 중...",
                                   bg=BG, fg="#888", font=("맑은 고딕", 9))
        self.lbl_status.pack()

        # ── 로그 ────────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=6)
        self.txt_log = tk.Text(log_frame, height=9, bg=EBGR, fg=FG,
                               font=("Consolas", 9), state="disabled",
                               relief="flat", bd=0)
        sb = tk.Scrollbar(log_frame, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ── 버튼 ────────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(pady=8)
        self.btn_update = tk.Button(btn_frame, text="업데이트 확인", width=14,
                                    bg="#444", fg=FG, relief="flat",
                                    command=self._start_full_check)
        self.btn_update.pack(side="left", padx=6)
        self.btn_launch = tk.Button(btn_frame, text="▶ 실행", width=14,
                                    bg="#2e7d32", fg="white", relief="flat",
                                    font=("맑은 고딕", 10, "bold"),
                                    state="disabled",
                                    command=self._launch_app)
        self.btn_launch.pack(side="left", padx=6)

    # ------------------------------------------------------------------
    def _copy_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def _log(self, msg: str):
        def _do():
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", msg + "\n")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
        self.root.after(0, _do)

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self.lbl_status.config(text=msg))

    def _set_busy(self, busy: bool):
        self.root.after(0, lambda: self.btn_update.config(
            state="disabled" if busy else "normal"))
        if busy:
            self.root.after(0, self.progress.start)
        else:
            self.root.after(0, self.progress.stop)

    def _set_launch_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        bg    = "#2e7d32" if enabled else "#444"
        self.root.after(0, lambda: self.btn_launch.config(state=state, bg=bg))

    # ------------------------------------------------------------------
    def _start_full_check(self):
        if self._updating:
            return
        self._updating = True
        threading.Thread(target=self._full_check, daemon=True).start()

    def _full_check(self):
        self._set_busy(True)
        self._set_launch_enabled(False)

        nas_url  = self.cfg.get("nas_url", "").rstrip("/")
        username = self.cfg.get("username", "")
        password = self.cfg.get("password", "")
        auth     = (username, password) if username else None

        if not nas_url:
            self._log("[오류] launcher_config.json에 nas_url이 없습니다.")
            self._set_status("설정 필요")
            self._set_busy(False)
            self._updating = False
            return

        # ── 1. 라이선스 체크 ────────────────────────────────────────
        self._set_status("라이선스 확인 중...")
        result, expire = check_license(nas_url, auth)
        self._update_license_ui(result, expire)

        if result in (LicenseResult.BLOCKED, LicenseResult.UNKNOWN, LicenseResult.EXPIRED):
            self._set_busy(False)
            self._updating = False
            return

        # ── 2. 업데이트 체크 ────────────────────────────────────────
        self._set_status("버전 확인 중...")
        try:
            r = requests.get(f"{nas_url}/version.json", auth=auth, timeout=10)
            r.raise_for_status()
            info = r.json()

            remote_ver  = info["version"]
            current_ver = get_current_version()
            self.root.after(0, lambda: self.lbl_remote_ver.config(
                text=f"→ 최신: {remote_ver}"))

            if remote_ver == current_ver:
                self._log(f"최신 버전입니다 ({current_ver})")
                self._set_status("최신 버전")
            else:
                self._log(f"업데이트: {current_ver} → {remote_ver}")
                self._download_and_apply(nas_url, auth, info)

        except requests.exceptions.ConnectionError:
            self._log("[경고] NAS 연결 불가. 오프라인으로 계속합니다.")
            self._set_status("오프라인")
        except Exception as e:
            self._log(f"[오류] {e}")
            self._set_status("오류")

        self._set_launch_enabled(self._licensed)
        self._set_busy(False)
        self._updating = False

    def _update_license_ui(self, result: str, expire: str):
        today = datetime.date.today()

        if result == LicenseResult.OK:
            expire_dt  = datetime.date.fromisoformat(expire)
            days_left  = (expire_dt - today).days
            text       = f"유효 (만료: {expire}, {days_left}일 남음)"
            color      = "#aaffaa"
            self._licensed = True
            self._log(f"[라이선스] {text}")

        elif result == LicenseResult.OFFLINE:
            cache      = load_license_cache()
            last_check = cache.get("last_check", "") if cache else ""
            last_dt    = datetime.date.fromisoformat(last_check) if last_check else today
            grace_left = OFFLINE_GRACE_DAYS - (today - last_dt).days
            text       = f"오프라인 유예 ({grace_left}일 남음, 만료: {expire})"
            color      = "#ffcc44"
            self._licensed = True
            self._log(f"[라이선스] {text}")

        elif result == LicenseResult.EXPIRED:
            text       = f"만료됨 ({expire})"
            color      = "#ff5555"
            self._licensed = False
            self._log(f"[라이선스] 사용 기간이 만료되었습니다 ({expire})")
            self.root.after(0, lambda: messagebox.showerror(
                "라이선스 만료",
                f"사용 기간이 만료되었습니다.\n\n만료일: {expire}\n\n"
                "관리자에게 문의하세요."))

        elif result == LicenseResult.UNKNOWN:
            text       = "등록되지 않은 PC"
            color      = "#ff5555"
            self._licensed = False
            self._log(f"[라이선스] 등록되지 않은 PC — ID: {expire}")
            self.root.after(0, lambda: messagebox.showerror(
                "미등록 PC",
                f"이 PC는 등록되어 있지 않습니다.\n\n"
                f"PC ID: {get_machine_id()}\n\n"
                "위 ID를 관리자에게 전달하세요."))

        else:  # BLOCKED
            text       = f"서버 연결 불가 (유예 기간 초과)"
            color      = "#ff5555"
            self._licensed = False
            self._log(f"[라이선스] 오프라인 유예 기간({OFFLINE_GRACE_DAYS}일) 초과")
            self.root.after(0, lambda: messagebox.showerror(
                "연결 필요",
                f"라이선스 확인을 위해 인터넷 연결이 필요합니다.\n\n"
                f"마지막 확인 후 {OFFLINE_GRACE_DAYS}일이 초과되었습니다."))

        self.root.after(0, lambda: self.lbl_lic.config(text=text, fg=color))
        self._set_status("라이선스: " + text)

    # ------------------------------------------------------------------
    def _download_and_apply(self, nas_url: str, auth, info: dict):
        filename = info["file"]
        self._set_status("다운로드 중...")
        self._log(f"다운로드: {filename}")

        try:
            r = requests.get(f"{nas_url}/{filename}", auth=auth,
                             stream=True, timeout=120)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(UPDATE_ZIP, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 100)
                        self._set_status(f"다운로드 중... {pct}%")

            self._set_status("압축 해제 중...")
            self._log("압축 해제 중...")
            with zipfile.ZipFile(UPDATE_ZIP) as z:
                for member in z.namelist():
                    fname = os.path.basename(member)
                    dest  = os.path.join(BASE_DIR, member)
                    if fname in KEEP_USER_FILES and os.path.exists(dest):
                        self._log(f"  [스킵] {member}")
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if not member.endswith("/"):
                        with z.open(member) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            os.remove(UPDATE_ZIP)
            save_version(info["version"])
            self.root.after(0, lambda: self.lbl_ver.config(text=info["version"]))
            self._log(f"업데이트 완료: {info['version']}")
            self._set_status("업데이트 완료")

        except Exception as e:
            if os.path.exists(UPDATE_ZIP):
                os.remove(UPDATE_ZIP)
            raise e

    # ------------------------------------------------------------------
    def _launch_app(self):
        if not self._licensed:
            messagebox.showerror("라이선스 오류", "유효한 라이선스가 없습니다.")
            return
        python = find_python()
        if not python:
            messagebox.showerror("Python 없음",
                "Python을 찾을 수 없습니다.\n"
                "install_deps.bat을 먼저 실행하세요.")
            return
        if not os.path.exists(APP_ENTRY):
            messagebox.showerror("앱 없음",
                f"앱 파일이 없습니다.\n먼저 업데이트를 실행하세요.")
            return

        self._log(f"실행: {APP_ENTRY}")
        subprocess.Popen([python, APP_ENTRY], cwd=APP_DIR,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.root.after(800, self.root.destroy)

    # ------------------------------------------------------------------
    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    elevate_if_needed()
    app = LauncherApp()
    app.run()
