"""
ent_bot GUI
───────────
tkinter 기반 봇 제어 인터페이스.
  python ent_bot_gui.py
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import cv2
import numpy as np
from PIL import Image, ImageTk
import keyboard as kb_module

from ent_bot_config import BotConfig
from ent_bot_engine import BotEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 자동 로그인 설정
try:
    from auto_login import ALL_SERVERS, load_config as load_login_config, save_config as save_login_config
    _HAS_AUTO_LOGIN = True
except ImportError:
    _HAS_AUTO_LOGIN = False
    ALL_SERVERS = []
CONFIG_PATH = os.path.join(BASE_DIR, "ent_config.json")


class BotGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Ent Bot")
        self.root.geometry("1100x750")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 설정 & 엔진
        self.config = BotConfig(CONFIG_PATH)
        self.engine = BotEngine(self.config, log_callback=self._log_threadsafe)

        # UI 빌드
        self._build_toolbar()
        self._build_main()
        self._build_log()

        # 글로벌 핫키
        kb_module.add_hotkey("f12", self._emergency_stop)

        # 비동기 초기화
        self._init_async()

        # 주기적 업데이트
        self._poll_state()
        self._poll_debug()

    # ──────────────────────────────────────────
    # UI 빌드
    # ──────────────────────────────────────────
    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(8, 0))

        self.start_btn = ttk.Button(bar, text="▶ 시작", command=self._on_start, state="disabled")
        self.start_btn.pack(side="left", padx=2)

        self.stop_btn = ttk.Button(bar, text="■ 정지", command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=2)

        self.pause_btn = ttk.Button(bar, text="⏸ 일시정지", command=self._on_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)

        self.state_label = ttk.Label(bar, text="IDLE", font=("Consolas", 14, "bold"),
                                     foreground="#FFD700")
        self.state_label.pack(side="left", padx=8)

        if _HAS_AUTO_LOGIN:
            self.login_btn = ttk.Button(bar, text="자동 접속", command=self._on_auto_login)
            self.login_btn.pack(side="left", padx=2)

        ttk.Label(bar, text="F12=긴급종료", foreground="gray").pack(side="right")

    def _build_main(self):
        pane = ttk.PanedWindow(self.root, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=4)

        # 왼쪽: 설정
        self._build_settings(pane)

        # 오른쪽: 디버그 뷰
        debug_frame = ttk.LabelFrame(pane, text="디버그 뷰")
        self.debug_label = ttk.Label(debug_frame, anchor="center")
        self.debug_label.pack(fill="both", expand=True, padx=2, pady=2)
        pane.add(debug_frame, weight=3)

    def _build_settings(self, parent):
        sf = ttk.LabelFrame(parent, text="설정")
        parent.add(sf, weight=1)

        # 스크롤 가능 프레임
        canvas = tk.Canvas(sf, highlightthickness=0, width=240)
        scrollbar = ttk.Scrollbar(sf, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 설정 항목
        settings = [
            ("── OCR ──", None),
            ("OCR 간격 (초):", "ocr_interval"),
            ("NPC 이름:", "npc_name"),
            ("줍기 키워드:", "pickup_keyword"),
            ("줍기 신뢰도:", "pickup_conf"),
            ("── 순찰 ──", None),
            ("순찰 거리 (px):", "patrol_dist"),
            ("순찰 거리UP (px):", "patrol_dist_up"),
            ("방향 전환 횟수:", "max_patrol_steps"),
            ("이동 대기 (초):", "move_wait_sec"),
            ("스캔 간격 (초):", "scan_interval"),
            ("── 전투 ──", None),
            ("공격 간격 (초):", "attack_interval"),
            ("NPC 사라짐 (초):", "npc_gone_timeout"),
            ("드래그 거리 (px):", "drag_dist"),
            ("재공격 실패 MAX:", "reattack_fail_max"),
            ("접근 실패 MAX:", "approach_fail_max"),
            ("사거리 (px):", "close_enough"),
            ("공격확인 (초):", "atk_confirm_timeout"),
            ("── 모션 감지 ──", None),
            ("영역 크기 (px):", "motion_size"),
            ("임계값:", "motion_threshold"),
            ("── 타이밍 ──", None),
            ("접근 대기 (초):", "approach_wait_sec"),
            ("두루마리 대기 (초):", "scroll_wait"),
            ("미발견 복귀 (초):", "npc_not_found_timeout"),
            ("무게 체크 (초):", "weight_check_interval"),
            ("── 갇힘 감지 ──", None),
            ("기록 수:", "stuck_history_size"),
            ("반경 (px):", "stuck_radius"),
            ("체크 간격 (초):", "stuck_check_interval"),
            ("이동불가 횟수:", "stuck_no_move_max"),
            ("── 디바이스 ──", None),
            ("키보드 디바이스:", "keyboard_device"),
            ("마우스 디바이스:", "mouse_device"),
        ]

        self._setting_vars = {}
        self._check_vars = {}
        row = 0

        # ── 체크박스 (최상단) ──
        clan_wh_var = tk.BooleanVar(value=self.config.use_clan_warehouse)
        self._check_vars["use_clan_warehouse"] = clan_wh_var
        clan_wh_check = ttk.Checkbutton(inner, text="혈맹 창고 사용", variable=clan_wh_var,
                                         command=self._on_clan_warehouse_toggle)
        clan_wh_check.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 2))
        row += 1

        patrol_rand_var = tk.BooleanVar(value=self.config.patrol_random)
        self._check_vars["patrol_random"] = patrol_rand_var
        patrol_rand_check = ttk.Checkbutton(inner, text="랜덤 순찰", variable=patrol_rand_var,
                                             command=self._on_checkbox_toggle)
        patrol_rand_check.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 8))
        row += 1

        # ── 자동 로그인 설정 ──
        if _HAS_AUTO_LOGIN:
            login_cfg = load_login_config()

            ttk.Label(inner, text="── 자동 로그인 ──", font=("", 9, "bold")).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 2))
            row += 1

            auto_login_var = tk.BooleanVar(value=login_cfg.get("auto_login", True))
            self._auto_login_var = auto_login_var
            ttk.Checkbutton(inner, text="게임 미실행 시 자동 접속", variable=auto_login_var).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 2))
            row += 1

            ttk.Label(inner, text="서버:").grid(row=row, column=0, sticky="w", padx=4, pady=1)
            self._login_server_var = tk.StringVar(value=login_cfg.get("server", ""))
            server_combo = ttk.Combobox(inner, textvariable=self._login_server_var,
                                        values=ALL_SERVERS, width=10, state="readonly")
            server_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=1)
            row += 1

            ttk.Label(inner, text="캐릭터:").grid(row=row, column=0, sticky="w", padx=4, pady=1)
            self._login_char_var = tk.IntVar(value=login_cfg.get("character", 1))
            char_frame = ttk.Frame(inner)
            char_frame.grid(row=row, column=1, sticky="w", padx=4, pady=1)
            for i in range(1, 4):
                ttk.Radiobutton(char_frame, text=str(i), variable=self._login_char_var,
                                value=i).pack(side="left")
            row += 1

            ttk.Separator(inner, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
            row += 1

        for label_text, key in settings:
            if key is None:
                ttk.Label(inner, text=label_text, font=("", 9, "bold")).grid(
                    row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 2)
                )
                row += 1
                continue
            ttk.Label(inner, text=label_text).grid(row=row, column=0, sticky="w", padx=4, pady=1)
            val = getattr(self.config, key, "")
            var = tk.StringVar(value="" if val is None else str(val))
            entry = ttk.Entry(inner, textvariable=var, width=12)
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=1)
            self._setting_vars[key] = var
            row += 1

        # 저장 버튼
        btn_frame = ttk.Frame(inner)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text="적용 & 저장", command=self._apply_settings).pack(fill="x")

    def _build_log(self):
        lf = ttk.LabelFrame(self.root, text="로그")
        lf.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.log_text = scrolledtext.ScrolledText(
            lf, height=8, state="disabled", font=("Consolas", 9), wrap="word"
        )
        self.log_text.pack(fill="both", expand=True, padx=2, pady=2)

    # ──────────────────────────────────────────
    # 로그
    # ──────────────────────────────────────────
    def _log_threadsafe(self, msg: str):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        # 1000줄 초과 시 정리
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 1000:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", f"{lines - 800}.0")
            self.log_text.configure(state="disabled")

    # ──────────────────────────────────────────
    # 초기화 (비동기)
    # ──────────────────────────────────────────
    def _init_async(self):
        def _do():
            try:
                self.engine.initialize()
                self.root.after(0, self._on_init_done)
            except Exception as e:
                self.root.after(0, self._append_log, f"[오류] 초기화 실패: {e}")

        t = threading.Thread(target=_do, daemon=True)
        t.start()

    def _on_init_done(self):
        self.start_btn.configure(state="normal")
        self._append_log("준비 완료 — [시작] 버튼을 누르세요")

    # ──────────────────────────────────────────
    # 버튼 핸들러
    # ──────────────────────────────────────────
    def _on_auto_login(self):
        """자동 접속 버튼 — 설정 저장 후 별도 스레드에서 실행"""
        self._apply_settings()  # 현재 GUI 설정 저장
        self.login_btn.configure(state="disabled")
        self._append_log("[자동접속] 시작...")

        def worker():
            try:
                from auto_login import run_auto_login, load_config as load_login_config
                cfg = load_login_config()
                run_auto_login(cfg, self._append_log)
            except Exception as e:
                self._append_log(f"[자동접속] 오류: {e}")
            finally:
                self.root.after(0, lambda: self.login_btn.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

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
        self.pause_btn.configure(text="⏸ 일시정지")

    def _on_pause(self):
        if self.engine.is_paused:
            self.engine.resume()
            self.pause_btn.configure(text="⏸ 일시정지")
        else:
            self.engine.pause()
            self.pause_btn.configure(text="▶ 재개")

    def _emergency_stop(self):
        """F12 긴급 종료"""
        from interception import key_up, mouse_up
        try:
            key_up("ctrl")
            mouse_up("left")
        except Exception:
            pass
        self.engine.stop()
        self.root.after(0, self._append_log, "[F12] 긴급 종료")
        self.root.after(100, self._on_stop)

    # ──────────────────────────────────────────
    # 체크박스 토글 (즉시 적용 & 저장)
    # ──────────────────────────────────────────
    def _on_clan_warehouse_toggle(self):
        enabled = self._check_vars["use_clan_warehouse"].get()
        self.config.use_clan_warehouse = enabled
        self.config.save(CONFIG_PATH)
        label = "혈맹 창고" if enabled else "개인 창고"
        self._append_log(f"[설정] {label} 모드 → 저장 완료")

    def _on_checkbox_toggle(self):
        for key, var in self._check_vars.items():
            setattr(self.config, key, var.get())
        self.config.save(CONFIG_PATH)
        self._append_log("[설정] 체크박스 변경 → 저장 완료")

    # ──────────────────────────────────────────
    # 설정 적용
    # ──────────────────────────────────────────
    def _apply_settings(self):
        for key, var in self._setting_vars.items():
            raw = var.get().strip()
            if not raw or raw.lower() == "none":
                setattr(self.config, key, None)
                continue
            cur = getattr(self.config, key, None)
            try:
                if isinstance(cur, tuple):
                    # "(854, 342)" → (854, 342)
                    parts = raw.strip("() ").split(",")
                    setattr(self.config, key, tuple(int(p.strip()) for p in parts))
                elif isinstance(cur, float):
                    setattr(self.config, key, float(raw))
                elif isinstance(cur, int):
                    setattr(self.config, key, int(raw))
                else:
                    setattr(self.config, key, raw)
            except ValueError:
                self._append_log(f"[설정] '{key}' 값 오류: {raw}")
                return

        # 체크박스 설정 적용
        for key, var in self._check_vars.items():
            setattr(self.config, key, var.get())

        # 디바이스 변경 즉시 적용
        kb = self.config.keyboard_device
        ms = self.config.mouse_device
        if kb is not None or ms is not None:
            from interception import set_devices
            try:
                set_devices(keyboard=kb, mouse=ms)
                self._append_log(f"[설정] 디바이스 변경  KB={kb}  Mouse={ms}")
            except Exception as e:
                self._append_log(f"[설정] 디바이스 변경 실패: {e}")

        self.config.save(CONFIG_PATH)

        # 자동 로그인 설정도 저장
        if _HAS_AUTO_LOGIN and hasattr(self, '_login_server_var'):
            login_cfg = load_login_config()
            login_cfg["server"] = self._login_server_var.get()
            login_cfg["character"] = self._login_char_var.get()
            login_cfg["auto_login"] = self._auto_login_var.get()
            save_login_config(login_cfg)

        self._append_log("[설정] 저장 완료")

    # ──────────────────────────────────────────
    # 주기적 업데이트
    # ──────────────────────────────────────────
    def _poll_state(self):
        st = self.engine.state
        self.state_label.configure(text=st)
        # 상태별 색상
        colors = {
            "IDLE": "#888888", "PATROL": "#FFD700", "APPROACH": "#FFA500",
            "ATTACK": "#FF4444", "FIGHTING": "#FF0000",
        }
        self.state_label.configure(foreground=colors.get(st, "#FFFFFF"))

        # 봇이 멈추면 버튼 상태 갱신
        if not self.engine.is_running and self.stop_btn["state"] == "normal":
            self._on_stop()

        self.root.after(200, self._poll_state)

    def _poll_debug(self):
        frame = self.engine.last_debug_frame
        if frame is not None:
            try:
                h, w = frame.shape[:2]
                # 디버그 라벨 크기에 맞게 리사이즈
                lw = self.debug_label.winfo_width()
                lh = self.debug_label.winfo_height()
                if lw > 10 and lh > 10:
                    scale = min(lw / w, lh / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    resized = cv2.resize(frame, (new_w, new_h))
                else:
                    resized = cv2.resize(frame, (640, 480))
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                photo = ImageTk.PhotoImage(img)
                self.debug_label.configure(image=photo)
                self.debug_label._photo = photo
            except Exception:
                pass
        self.root.after(100, self._poll_debug)

    # ──────────────────────────────────────────
    # 종료
    # ──────────────────────────────────────────
    def _on_close(self):
        self.engine.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = BotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
