"""
라이선스 관리 도구
──────────────────
licenses.json 항목을 GUI로 추가/수정/삭제 후 NAS에 업로드.

실행: python license_manager.py
"""
import os, sys, json, datetime
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import Calendar

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

def _base_dir():
    # PyInstaller onefile: sys.executable = 실제 exe 위치
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR     = _base_dir()
CONFIG_FILE  = os.path.join(BASE_DIR, "launcher_config.json")
LOCAL_LIC    = os.path.join(BASE_DIR, "nas_update", "licenses.json")

BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
RED    = "#f38ba8"
GREEN  = "#a6e3a1"
ENTRY_BG = "#313244"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def parse_entry(entry):
    """{"expire":..,"name":..} 또는 "YYYY-MM-DD" → (expire_str, name)"""
    if isinstance(entry, dict):
        return entry.get("expire", ""), entry.get("name", "")
    return (entry or ""), ""

def build_entry(expire, name):
    if name.strip():
        return {"expire": expire, "name": name.strip()}
    return expire

class LicenseManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("라이선스 관리")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.geometry("700x480")

        self.cfg = load_config()
        self.nas_url  = self.cfg.get("nas_url", "").rstrip("/")
        self.username = self.cfg.get("username", "")
        self.password = self.cfg.get("password", "")
        self.data: dict = {}   # mac → raw entry

        self._build_ui()
        self._load_from_local()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # NAS 연결 설정
        nas_frame = tk.LabelFrame(self, text="NAS 연결 설정", bg=BG, fg=ACCENT,
                                  font=("Consolas", 9))
        nas_frame.pack(fill="x", padx=8, pady=(6, 2))

        row = tk.Frame(nas_frame, bg=BG)
        row.pack(fill="x", pady=4)

        def lbl(text):
            tk.Label(row, text=text, bg=BG, fg="#888",
                     font=("Consolas", 9)).pack(side="left", padx=(8, 2))

        lbl("URL:")
        self.e_nas_url = tk.Entry(row, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                  width=28, font=("Consolas", 9))
        self.e_nas_url.insert(0, self.nas_url)
        self.e_nas_url.pack(side="left", padx=2)

        lbl("계정:")
        self.e_nas_user = tk.Entry(row, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                   width=9, font=("Consolas", 9))
        self.e_nas_user.insert(0, self.username)
        self.e_nas_user.pack(side="left", padx=2)

        lbl("비밀번호:")
        self.e_nas_pass = tk.Entry(row, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                   width=9, font=("Consolas", 9), show="*")
        self.e_nas_pass.insert(0, self.password)
        self.e_nas_pass.pack(side="left", padx=2)

        lbl("DSM포트:")
        self.e_dsm_port = tk.Entry(row, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                   width=6, font=("Consolas", 9))
        self.e_dsm_port.insert(0, str(self.cfg.get("nas_dsm_port", 5000)))
        self.e_dsm_port.pack(side="left", padx=2)

        lbl("NAS 파일경로:")
        self.e_nas_path = tk.Entry(row, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                   width=22, font=("Consolas", 9))
        self.e_nas_path.insert(0, self.cfg.get("nas_file_path", "/web/update/licenses.json"))
        self.e_nas_path.pack(side="left", padx=2)

        tk.Button(row, text="저장", command=self._save_nas_config,
                  bg=ENTRY_BG, fg=FG, relief="flat", padx=6).pack(side="left", padx=6)

        # 상단 툴바
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=4)

        tk.Button(top, text="NAS에서 불러오기", command=self._fetch_from_nas,
                  bg=ACCENT, fg=BG, relief="flat", padx=8).pack(side="left", padx=2)
        tk.Button(top, text="NAS에 업로드", command=self._upload_to_nas,
                  bg=GREEN, fg=BG, relief="flat", padx=8).pack(side="left", padx=2)

        self.status_var = tk.StringVar(value="로컬 파일 로드 완료")
        tk.Label(top, textvariable=self.status_var, bg=BG, fg="#888",
                 font=("Consolas", 9)).pack(side="right", padx=4)

        # 테이블
        tbl_frame = tk.Frame(self, bg=BG)
        tbl_frame.pack(fill="both", expand=True, padx=8, pady=2)

        cols = ("mac", "name", "expire", "status")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=14)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=ENTRY_BG, foreground=FG,
                        fieldbackground=ENTRY_BG, rowheight=24)
        style.configure("Treeview.Heading", background="#313244", foreground=ACCENT)

        self.tree.heading("mac",    text="MAC 주소")
        self.tree.heading("name",   text="PC 이름")
        self.tree.heading("expire", text="만료일")
        self.tree.heading("status", text="상태")
        self.tree.column("mac",    width=160, anchor="w")
        self.tree.column("name",   width=150, anchor="w")
        self.tree.column("expire", width=110, anchor="center")
        self.tree.column("status", width=100, anchor="center")

        sb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 입력 폼
        form = tk.LabelFrame(self, text="항목 추가/수정", bg=BG, fg=ACCENT,
                             font=("Consolas", 9))
        form.pack(fill="x", padx=8, pady=4)

        def lbl(parent, text):
            tk.Label(parent, text=text, bg=BG, fg="#888",
                     font=("Consolas", 9)).pack(side="left", padx=(8,2))

        row1 = tk.Frame(form, bg=BG)
        row1.pack(fill="x", pady=4)
        lbl(row1, "MAC:")
        self.e_mac = tk.Entry(row1, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                              width=18, font=("Consolas", 10))
        self.e_mac.pack(side="left", padx=2)
        lbl(row1, "PC 이름:")
        self.e_name = tk.Entry(row1, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                               width=16, font=("Consolas", 10))
        self.e_name.pack(side="left", padx=2)
        lbl(row1, "만료일:")
        self.e_expire = tk.Entry(row1, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                 width=13, font=("Consolas", 10), cursor="hand2")
        self.e_expire.pack(side="left", padx=2)
        self.e_expire.bind("<Button-1>", self._open_calendar)

        row2 = tk.Frame(form, bg=BG)
        row2.pack(fill="x", pady=(0, 6))
        tk.Button(row2, text="저장", command=self._save_entry,
                  bg=ACCENT, fg=BG, relief="flat", padx=10).pack(side="left", padx=8)
        tk.Button(row2, text="삭제", command=self._delete_entry,
                  bg=RED, fg=BG, relief="flat", padx=10).pack(side="left", padx=2)
        tk.Button(row2, text="초기화", command=self._clear_form,
                  bg=ENTRY_BG, fg=FG, relief="flat", padx=10).pack(side="left", padx=2)

    def _open_calendar(self, event=None):
        top = tk.Toplevel(self)
        top.title("날짜 선택")
        top.configure(bg=BG)
        top.resizable(False, False)
        top.grab_set()

        # 현재 입력값으로 초기 날짜 설정
        try:
            init = datetime.date.fromisoformat(self.e_expire.get().strip())
        except Exception:
            init = datetime.date.today()

        cal = Calendar(top, selectmode="day", year=init.year, month=init.month,
                       day=init.day, date_pattern="yyyy-mm-dd",
                       background=ENTRY_BG, foreground=FG,
                       headersbackground="#313244", headersforeground=ACCENT,
                       selectbackground=ACCENT, selectforeground=BG,
                       weekendbackground=ENTRY_BG, weekendforeground=FG,
                       othermonthbackground=BG, othermonthforeground="#555")
        cal.pack(padx=10, pady=10)

        def on_select():
            self.e_expire.delete(0, "end")
            self.e_expire.insert(0, cal.get_date())
            top.destroy()

        tk.Button(top, text="선택", command=on_select,
                  bg=ACCENT, fg=BG, relief="flat", padx=20, pady=4).pack(pady=(0, 10))

    # ── 데이터 ────────────────────────────────────────────────────────────
    def _load_from_local(self):
        if os.path.exists(LOCAL_LIC):
            with open(LOCAL_LIC, encoding="utf-8") as f:
                self.data = json.load(f)
            self._refresh_tree()
            self.status_var.set(f"로컬 로드: {LOCAL_LIC}")
        else:
            self.status_var.set("로컬 파일 없음 — NAS에서 불러오기 시도")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        today = datetime.date.today()
        for mac, entry in self.data.items():
            if mac == "*":
                continue
            expire_str, name = parse_entry(entry)
            try:
                exp = datetime.date.fromisoformat(expire_str)
                days = (exp - today).days
                status = f"D-{days}" if days >= 0 else f"만료({-days}일)"
                tag = "ok" if days >= 0 else "expired"
            except Exception:
                status = "?"
                tag = ""
            self.tree.insert("", "end", iid=mac,
                             values=(mac, name, expire_str, status), tags=(tag,))
        self.tree.tag_configure("ok",      foreground=GREEN)
        self.tree.tag_configure("expired", foreground=RED)

    def _on_select(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        mac = sel[0]
        expire_str, name = parse_entry(self.data.get(mac, ""))
        self._clear_form()
        self.e_mac.insert(0, mac)
        self.e_name.insert(0, name)
        self.e_expire.insert(0, expire_str)

    def _clear_form(self):
        self.e_mac.delete(0, "end")
        self.e_name.delete(0, "end")
        self.e_expire.delete(0, "end")

    def _save_entry(self):
        mac    = self.e_mac.get().strip().lower().replace(":", "").replace("-", "")
        name   = self.e_name.get().strip()
        expire = self.e_expire.get().strip()
        if not mac or not expire:
            messagebox.showwarning("입력 오류", "MAC 주소와 만료일은 필수입니다.")
            return
        try:
            datetime.date.fromisoformat(expire)
        except ValueError:
            messagebox.showerror("형식 오류", "만료일은 YYYY-MM-DD 형식이어야 합니다.")
            return
        self.data[mac] = build_entry(expire, name)
        self._refresh_tree()
        self._clear_form()
        self.status_var.set(f"저장됨: {mac}")

    def _delete_entry(self):
        mac = self.e_mac.get().strip().lower().replace(":", "").replace("-", "")
        if not mac or mac not in self.data:
            messagebox.showwarning("삭제 오류", "선택된 항목이 없습니다.")
            return
        if messagebox.askyesno("삭제 확인", f"{mac} 를 삭제하시겠습니까?"):
            del self.data[mac]
            self._refresh_tree()
            self._clear_form()
            self.status_var.set(f"삭제됨: {mac}")

    # ── NAS ───────────────────────────────────────────────────────────────
    def _auth(self):
        user = self.e_nas_user.get().strip()
        pw   = self.e_nas_pass.get().strip()
        return (user, pw) if user else None

    def _nas_url(self):
        return self.e_nas_url.get().strip().rstrip("/")

    def _save_nas_config(self):
        self.cfg["nas_url"]       = self._nas_url()
        self.cfg["username"]      = self.e_nas_user.get().strip()
        self.cfg["password"]      = self.e_nas_pass.get().strip()
        self.cfg["nas_dsm_port"]  = int(self.e_dsm_port.get().strip() or 5000)
        self.cfg["nas_file_path"] = self.e_nas_path.get().strip()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=4)
        self.status_var.set("NAS 설정 저장 완료")

    def _fetch_url(self):
        """nas_file_path 에서 HTTP 다운로드 URL 자동 생성.
        /web/update/licenses.json → http://host/update/licenses.json"""
        from urllib.parse import urlparse
        nas_path = self.e_nas_path.get().strip()
        for prefix in ("/web", "/volume1/web", "/volume2/web"):
            if nas_path.startswith(prefix):
                nas_path = nas_path[len(prefix):]
                break
        p = urlparse(self._nas_url())
        return f"{p.scheme}://{p.hostname}{nas_path}"

    def _fetch_from_nas(self):
        if not self._nas_url():
            messagebox.showerror("오류", "NAS URL을 입력해주세요.")
            return
        fetch_url = self._fetch_url()
        try:
            r = requests.get(fetch_url, auth=self._auth(), timeout=8)
            r.raise_for_status()
            self.data = r.json()
            self._refresh_tree()
            self.status_var.set(f"NAS 불러오기 완료: {fetch_url}")
        except Exception as e:
            messagebox.showerror("NAS 오류", f"URL: {fetch_url}\n\n{e}")

    def _save_local(self):
        os.makedirs(os.path.dirname(LOCAL_LIC), exist_ok=True)
        with open(LOCAL_LIC, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        self.status_var.set(f"로컬 저장 완료: {LOCAL_LIC}")

    def _nas_base_url(self):
        """Synology DSM API base URL (DSM 포트 사용)"""
        from urllib.parse import urlparse, urlunparse
        p = urlparse(self._nas_url())
        port = int(self.e_dsm_port.get().strip() or 5000)
        netloc = f"{p.hostname}:{port}"
        scheme = "https" if port == 5001 else "http"
        return urlunparse((scheme, netloc, "", "", "", ""))

    def _upload_to_nas(self):
        if not self._nas_url():
            messagebox.showerror("오류", "NAS URL을 입력해주세요.")
            return
        nas_path = self.e_nas_path.get().strip()
        if not nas_path:
            messagebox.showerror("오류", "NAS 파일 경로를 입력해주세요.\n예) /web/update/licenses.json")
            return
        if not messagebox.askyesno("업로드 확인", f"NAS의 {nas_path} 를 덮어씁니다. 계속하시겠습니까?"):
            return
        try:
            base   = self._nas_base_url()
            user   = self.e_nas_user.get().strip()
            pw     = self.e_nas_pass.get().strip()

            # 1) 로그인 → SID 획득
            login_r = requests.get(
                f"{base}/webapi/auth.cgi",
                params={"api": "SYNO.API.Auth", "method": "login", "version": "3",
                        "account": user, "passwd": pw,
                        "session": "FileStation", "format": "sid"},
                timeout=8,
            )
            if login_r.status_code != 200:
                raise Exception(f"[로그인] HTTP {login_r.status_code}\n{login_r.text[:200]}")
            login_data = login_r.json()
            if not login_data.get("success"):
                err = login_data.get("error", {})
                raise Exception(f"[로그인] 실패 — code={err.get('code')} (102=계정오류, 403=차단, 407=OTP필요)\n{login_data}")
            sid = login_data["data"]["sid"]

            # 2) 파일 업로드 (File Station API)
            folder   = "/".join(nas_path.rstrip("/").split("/")[:-1]) or "/"
            filename = nas_path.rstrip("/").split("/")[-1]
            content  = json.dumps(self.data, ensure_ascii=False, indent=4).encode("utf-8")
            upload_r = requests.post(
                f"{base}/webapi/entry.cgi",
                params={"api": "SYNO.FileStation.Upload", "method": "upload",
                        "version": "2", "_sid": sid},
                data={"path": folder, "create_parents": "true", "overwrite": "true"},
                files={"file": (filename, content, "application/json")},
                timeout=15,
            )
            if upload_r.status_code != 200:
                raise Exception(f"[업로드] HTTP {upload_r.status_code}\n{upload_r.text[:200]}")
            result = upload_r.json()

            # 3) 로그아웃
            requests.get(f"{base}/webapi/auth.cgi",
                         params={"api": "SYNO.API.Auth", "method": "logout",
                                 "version": "1", "_sid": sid}, timeout=5)

            if not result.get("success"):
                err = result.get("error", {})
                raise Exception(f"[업로드] 실패 — code={err.get('code')}\npath={folder}\n{result}")

            self.status_var.set("NAS 업로드 완료")
            messagebox.showinfo("완료", f"NAS에 업로드했습니다.\n{nas_path}")
        except Exception as e:
            messagebox.showerror("업로드 오류", str(e))


if __name__ == "__main__":
    app = LicenseManager()
    app.mainloop()
