"""
ent_bot 설정 관리
─────────────────
모든 설정 상수를 BotConfig 클래스로 관리.
ent_config.json에서 로드/저장.
"""
from __future__ import annotations
import os
import json


class BotConfig:
    """봇 설정 — 런타임 조정 가능, JSON 저장/로드"""

    def __init__(self, config_path: str | None = None):
        # ── 기본값 ──────────────────────────────────
        self.window_title = "Lineage Classic"

        # OCR
        self.npc_name = "엔트"
        self.pickup_keyword = "정령의돌"
        self.pickup_exclude = ["판매", "관매", "전수", "마법", "마볍", "정령마"]
        self.pickup_conf = 0.4
        self.ocr_interval = 0.5
        self.ocr_scan_rect = (10, 53, 1272, 696)

        # 순찰
        self.patrol_dist = 500
        self.patrol_dist_up = 200
        self.max_patrol_steps = 5
        self.patrol_random = False
        self.grid_spacing = 120
        self.patrol_zone = (297, 44, 1609, 767)

        # 엔트 미발견 복귀
        self.npc_not_found_timeout = 300.0

        # 두루마리
        self.scroll_key = "f10"
        self.scroll_click = (49, 118)
        self.scroll_wait = 5.0

        # 무게
        self.weight_pos = (55, 866)
        self.weight_bar = [46, 855, 102, 876]   # [x1, y1, x2, y2] 바 전체 범위
        self.weight_threshold = 0.5             # 창고 이동 기준 (0.0~1.0)
        self.weight_check_interval = 30.0

        # HP 초록 감지 → F8 (물약)
        self.hp_pos = (552, 768)
        self.hp_check_interval = 10.0
        self.hp_f8_cooldown = 3.0

        # MP 풀 감지 (복귀 후 대기)
        self.mp_full_pos = (962, 833)
        self.mp_wait_timeout = 120

        # 창고
        self.warehouse_scroll_click = (82, 230)
        self.warehouse_npc_click = (854, 342)
        self.warehouse_deposit_click = (82, 230)
        self.warehouse_ok_click = (288, 555)
        self.warehouse_item_threshold = 0.7

        # 창고 맡길 아이템 (GUI 체크박스로 토글)
        self.deposit_items = [
            {"name": "엔트의 열매",     "enabled": True},
            {"name": "엔트의 줄기",     "enabled": True},
            {"name": "정령의 돌",       "enabled": True},
            {"name": "버섯포자의 즙",   "enabled": True},
            {"name": "미스릴 원석",     "enabled": True},
            {"name": "엔트의 껍질",     "enabled": True},
            {"name": "판의 갈기털",     "enabled": True},
        ]

        # 혈맹 창고
        self.use_clan_warehouse  = False
        self.use_personal_warehouse = False
        self.clan_warehouse_scroll_click = (54, 282)
        self.clan_warehouse_npc_click = (714, 318)
        self.clan_warehouse_deposit_click = (65, 323)
        self.clan_warehouse_ok_click = (288, 555)

        # 추가 공격 대상 (옵션)
        self.extra_npc_enabled = False
        self.extra_npc_name = "판"

        # 타이밍
        self.move_wait_sec = 2.0
        self.approach_wait_sec = 1.5
        self.dialog_wait_sec = 0.3
        self.after_esc_sec = 0.15
        self.attack_interval = 0.2
        self.npc_gone_timeout = 1.5
        self.scan_interval = 0.05

        # 플레이어
        self.player_pos = (636, 340)

        # 공격 판정
        self.atk_check_delay = 0.5
        self.atk_fail_threshold = 3
        self.chat_atk_threshold = 0.7
        self.atk_confirm_timeout = 2.5
        self.atk_msg_timeout = 10.0
        self.reattack_fail_max = 3
        self.escape_retry_max = 3
        self.approach_fail_max = 3
        self.close_enough = 80

        # 모션 감지
        self.motion_size = 30
        self.motion_threshold = 10.0

        # 드래그
        self.drag_dist = 80

        # 채팅 영역
        self.chat_rect = (220, 900, 520, 935)

        # 갇힘 감지
        self.stuck_history_size = 10
        self.stuck_radius = 150
        self.stuck_check_interval = 60.0
        self.stuck_no_move_max = 8          # 연속 이동불가 N회 → 두루마리 복귀

        # 디바이스 오버라이드
        self.keyboard_device = None
        self.mouse_device = None

        # 멀티 인스턴스: 같은 이름 창이 여러 개일 때 몇 번째 창을 쓸지 (X좌표 정렬)
        # 0 = 왼쪽(기본), 1 = 오른쪽
        self.window_index = 0

        # ── 로드 ──────────────────────────────────
        self._path = config_path
        if config_path and os.path.exists(config_path):
            self.load(config_path)

    # JSON에서 저장/로드할 키 목록
    _PERSIST_KEYS = [
        "patrol_zone", "keyboard_device", "mouse_device",
        "ocr_interval", "patrol_dist", "patrol_dist_up", "max_patrol_steps",
        "patrol_random",
        "motion_size", "motion_threshold", "move_wait_sec",
        "approach_wait_sec", "attack_interval", "npc_gone_timeout",
        "scan_interval", "npc_not_found_timeout", "weight_check_interval",
        "drag_dist", "atk_confirm_timeout", "reattack_fail_max",
        "escape_retry_max", "approach_fail_max", "close_enough",
        "scroll_key", "scroll_click", "scroll_wait",
        "weight_pos", "weight_bar", "weight_threshold",
        "hp_pos", "hp_check_interval", "hp_f8_cooldown",
        "mp_full_pos", "mp_wait_timeout",
        "player_pos", "chat_rect", "ocr_scan_rect",
        "npc_name", "pickup_keyword", "pickup_conf",
        "warehouse_npc_click", "warehouse_deposit_click",
        "warehouse_ok_click", "warehouse_scroll_click",
        "warehouse_item_threshold",
        "deposit_items",
        "use_clan_warehouse", "use_personal_warehouse",
        "clan_warehouse_scroll_click", "clan_warehouse_npc_click",
        "clan_warehouse_deposit_click", "clan_warehouse_ok_click",
        "stuck_history_size", "stuck_radius", "stuck_check_interval",
        "stuck_no_move_max",
        "window_index",
        "extra_npc_enabled", "extra_npc_name",
    ]

    def load(self, path: str):
        """JSON 파일에서 설정 로드 (존재하는 키만 덮어쓰기)"""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for key, val in data.items():
            if hasattr(self, key):
                cur = getattr(self, key)
                # tuple 타입이면 tuple로 변환
                if isinstance(cur, tuple) and isinstance(val, list):
                    val = tuple(val)
                # 문자열로 된 숫자를 변환
                if isinstance(val, str):
                    try:
                        val = int(val)
                    except ValueError:
                        try:
                            val = float(val)
                        except ValueError:
                            pass
                setattr(self, key, val)
        self._path = path

    def save(self, path: str | None = None):
        """현재 설정을 JSON 파일에 저장"""
        path = path or self._path
        if not path:
            return
        data = {}
        for key in self._PERSIST_KEYS:
            val = getattr(self, key, None)
            if val is None:
                continue
            # tuple → list (JSON 호환)
            if isinstance(val, tuple):
                val = list(val)
            data[key] = val
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
