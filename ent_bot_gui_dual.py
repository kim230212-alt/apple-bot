"""
Ent Bot GUI — 듀얼 모드 (단일 프로세스)
────────────────────────────────────────
python ent_bot_gui_dual.py

1개 프로세스에서 두 봇을 실행.
SetForegroundWindow 가 같은 프로세스 내에서 호출되므로
Windows 포그라운드 잠금 거부 문제가 없음.
"""
from __future__ import annotations

import os
import sys
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext
import keyboard as kb_module

from ent_bot_config import BotConfig
from ent_bot_engine_template import BotEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from auto_login import (
        ALL_SERVERS,
        load_config as load_login_config,
        save_config as save_login_config,
    )
    _HAS_AUTO_LOGIN = True
except ImportError:
    _HAS_AUTO_LOGIN = False
    ALL_SERVERS = []


class BotPanel(ttk.LabelFrame):
    """단일 봇 제어 패널 (Frame 기반)"""

    def __init__(self, parent: tk.Widget, config_path: str, bot_name: str,
                 init_delay: float = 0.0, user_config_path: str | None = None):
        super().__init__(parent, text=bot_name)
        self._config_path = config_path
        self._user_config_path = user_config_path
        self.config = BotConfig(config_path, user_config_path)
        self.engine = BotEngine(self.config, log_callback=self._log_threadsafe)
        self._init_delay = init_delay

        self._build_toolbar()
        self._build_controls()
        self._build_log()

        self._init_async()
        self._poll_state()

    # ──────────────────────────────────────────
    # UI 빌드
    # ──────────────────────────────────────────
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=4, pady=(4, 0))

        self.start_btn = ttk.Button(bar, text="▶ 시작", command=self._on_start,
                                    state="disabled", width=8)
        self.start_btn.pack(side="left", padx=2)

        self.stop_btn = ttk.Button(bar, text="■ 정지", command=self._on_stop,
                                   state="disabled", width=8)
        self.stop_btn.pack(side="left", padx=2)

        self.pause_btn = ttk.Button(bar, text="⏸", command=self._on_pause,
                                    state="disabled", width=4)
        self.pause_btn.pack(side="left", padx=2)

        self.state_label = ttk.Label(bar, text="초기화 중...",
                                     font=("Consolas", 12, "bold"),
                                     foreground="#888888")
        self.state_label.pack(side="left", padx=8)

    def _build_controls(self):
        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=4, pady=2)

        self._clan_wh_var = tk.BooleanVar(value=self.config.use_clan_warehouse)
        ttk.Checkbutton(ctrl, text="혈맹창고", variable=self._clan_wh_var,
                        command=self._save_checkboxes).pack(side="left")

        self._personal_wh_var = tk.BooleanVar(value=self.config.use_personal_warehouse)
        ttk.Checkbutton(ctrl, text="일반창고", variable=self._personal_wh_var,
                        command=self._save_checkboxes).pack(side="left", padx=6)

        self._patrol_rand_var = tk.BooleanVar(value=self.config.patrol_random)
        ttk.Checkbutton(ctrl, text="랜덤순찰", variable=self._patrol_rand_var,
                        command=self._save_checkboxes).pack(side="left", padx=6)

        self._extra_npc_var = tk.BooleanVar(value=self.config.extra_npc_enabled)
        ttk.Checkbutton(ctrl, text=f"판공격", variable=self._extra_npc_var,
                        command=self._save_checkboxes).pack(side="left", padx=6)

        self.dev_btn = ttk.Button(ctrl, text="디바이스", command=self._on_kb_test, width=7)
        self.dev_btn.pack(side="right", padx=2)

        if _HAS_AUTO_LOGIN:
            self.login_btn = ttk.Button(ctrl, text="자동접속",
                                        command=self._on_auto_login, width=9)
            self.login_btn.pack(side="right")

    def _save_checkboxes(self):
        self.config.use_clan_warehouse      = self._clan_wh_var.get()
        self.config.use_personal_warehouse  = self._personal_wh_var.get()
        self.config.patrol_random           = self._patrol_rand_var.get()
        self.config.extra_npc_enabled       = self._extra_npc_var.get()
        self.config.save(self._user_config_path or self._config_path)

    def _build_log(self):
        self.log_text = scrolledtext.ScrolledText(
            self, height=32, state="disabled",
            font=("Consolas", 8), wrap="word"
        )
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    # ──────────────────────────────────────────
    # 로그
    # ──────────────────────────────────────────
    def _log_threadsafe(self, msg: str):
        self.after(0, self._append_log, msg)

    def _append_log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 800:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", f"{lines - 600}.0")
            self.log_text.configure(state="disabled")

    # ──────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────
    def _init_async(self):
        def _do():
            if self._init_delay > 0:
                time.sleep(self._init_delay)
            try:
                self.engine.initialize()
                self.after(0, self._on_init_done)
            except Exception as e:
                self.after(0, self._append_log, f"[오류] 초기화 실패: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def _on_init_done(self):
        self.start_btn.configure(state="normal")
        self._append_log("준비 완료 — [▶ 시작] 버튼을 누르세요")

    # ──────────────────────────────────────────
    # 버튼 핸들러
    # ──────────────────────────────────────────
    def _on_start(self):
        self.engine.start()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="normal")

    def _on_stop(self):
        self.engine.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.pause_btn.configure(text="⏸")

    def _on_pause(self):
        if self.engine.is_paused:
            self.engine.resume()
            self.pause_btn.configure(text="⏸")
        else:
            self.engine.pause()
            self.pause_btn.configure(text="▶ 재개")

    def _on_auto_login(self):
        if not _HAS_AUTO_LOGIN:
            return
        self.login_btn.configure(state="disabled")
        self._append_log("[자동접속] 시작...")

        def worker():
            success = False
            try:
                from auto_login import run_auto_login, load_config as _lc
                cfg = _lc()
                success = bool(run_auto_login(cfg, self._append_log, init_devices=False))
            except Exception as e:
                self._append_log(f"[자동접속] 오류: {e}")
            finally:
                self.after(0, lambda: self.login_btn.configure(state="normal"))
            if success:
                self._append_log("[자동접속] 완료 → 엔진 재초기화")
                self.after(0, self._init_async)

        threading.Thread(target=worker, daemon=True).start()

    def _on_kb_test(self):
        self.dev_btn.configure(state="disabled")
        self._append_log("[디바이스] keyboard_mouse_check.py 실행 중...")

        def worker():
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-X", "utf8", "keyboard_mouse_check.py"],
                    cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                proc.wait()
                self.config.load(self._config_path)
                kb = self.config.keyboard_device
                ms = self.config.mouse_device
                self.after(0, self._append_log, f"[디바이스] 갱신  KB={kb}  MS={ms}")
            except Exception as e:
                self.after(0, self._append_log, f"[디바이스] 오류: {e}")
            finally:
                self.after(0, lambda: self.dev_btn.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def emergency_stop(self):
        self.engine.stop()
        self.after(0, self._append_log, "[F12] 긴급 종료")
        self.after(100, self._on_stop)

    # ──────────────────────────────────────────
    # 상태 폴링
    # ──────────────────────────────────────────
    def _poll_state(self):
        st = self.engine.state
        colors = {
            "IDLE":     "#888888",
            "PATROL":   "#FFD700",
            "APPROACH": "#FFA500",
            "ATTACK":   "#FF4444",
            "FIGHTING": "#FF0000",
        }
        self.state_label.configure(
            text=st,
            foreground=colors.get(st, "#FFFFFF")
        )

        if not self.engine.is_running and self.stop_btn["state"] == "normal":
            self._on_stop()

        self.after(200, self._poll_state)


# ──────────────────────────────────────────────────────────────────────────────
class DualBotGUI:
    """두 BotPanel 을 나란히 배치하는 메인 GUI"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Ent Bot  DUAL  |  F12=전체 긴급종료")
        self.root.geometry("860x700")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        pane = ttk.Frame(root)
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        # BOT 1: 즉시 초기화
        self.panel1 = BotPanel(
            pane,
            config_path=os.path.join(BASE_DIR, "ent_config.json"),
            user_config_path=os.path.join(BASE_DIR, "user_config.json"),
            bot_name="BOT 1  (왼쪽 창)",
            init_delay=0.0,
        )
        self.panel1.pack(side="left", fill="both", expand=True, padx=(0, 2))

        # BOT 2: 3초 후 초기화 (auto_capture 경쟁 방지)
        self.panel2 = BotPanel(
            pane,
            config_path=os.path.join(BASE_DIR, "ent_config2.json"),
            user_config_path=os.path.join(BASE_DIR, "user_config2.json"),
            bot_name="BOT 2  (오른쪽 창)",
            init_delay=3.0,
        )
        self.panel2.pack(side="right", fill="both", expand=True, padx=(2, 0))

        kb_module.add_hotkey("f12", self._emergency_stop)

    def _emergency_stop(self):
        self.panel1.emergency_stop()
        self.panel2.emergency_stop()

    def _on_close(self):
        self.panel1.engine.stop()
        self.panel2.engine.stop()
        self.root.destroy()


# ──────────────────────────────────────────────────────────────────────────────
def main():
    import multiprocessing
    multiprocessing.freeze_support()
    root = tk.Tk()
    DualBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
