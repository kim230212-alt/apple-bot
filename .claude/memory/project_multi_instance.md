---
name: 멀티 인스턴스 작업 현황
description: 봇 2개 동시 실행 — 듀얼 단일 프로세스 방식 구현 완료 및 포커스 리스 시스템
type: project
originSessionId: 0fef196b-ccb7-47f6-a313-995286f10300
---
두 봇을 단일 프로세스(ent_bot_gui_dual.py)로 실행하는 방식으로 전환 완료 (2026-05-15).

**Why:** 크로스 프로세스 SetForegroundWindow 차단 문제 해결을 위해 단일 프로세스로 통합.

**실행 방법:**
```
run_dual.bat   # 관리자 권한 자동 상승 → ent_bot_gui_dual.py 실행
```
- Bot 1: `ent_config.json`, `window_index=0`, `init_delay=0.0`
- Bot 2: `ent_config2.json`, `window_index=1`, `init_delay=3.0`

**핵심 구현:**
- `ent_bot_gui_dual.py` — BotPanel × 2 좌우 배치, F12 긴급종료
- `input_lock.py` — Win32 Named Mutex (입력 직렬화)
- `capture_window.py` — dxcam output별 threading.Lock (DXGI_ERROR 방지)
- `ent_bot_engine_template.py` 주요 추가:
  - `initialize()`: ForegroundLockTimeout=0, 디바이스 캐시(auto_capture 경쟁 방지)
  - `_ensure_focus()`: AttachThreadInput + 30ms×3회 재시도
  - `_main_loop` 예외 래퍼: traceback 로그 후 정지
  - **포커스 리스 시스템**: `_focus_lease_hwnd` 전역 변수
    - `_acquire_focus_lease()` / `_release_focus_lease()` — `_run_warehouse()` 진입/종료 시 호출
    - `_wait_for_lease(timeout=120s)` — `_ikey/_ipress/_iscroll/_click_move` 락 획득 전 호출
    - 효과: Bot 2 창고 중 Bot 1 입력이 조용히 실패하지 않고 리스 해제까지 대기
  - `_ikey_force(max_wait=5s)` — `_scroll_return`의 F9/F5/F11 전용 (포커스 재시도 강화)
  - `_scroll_return`: 최대 5회 재시도 + F11 후 대기 3초 + zone 임계값 0.70

**키보드 device 주의:**
- `keyboard_device: 0` (topviewer 가상 키보드) — 정상 작동 확인, 건드리지 말 것
- auto_capture_devices가 device 6 (Logitech 마우스 인터페이스)을 키보드로 오감지함

**2026-05-16 추가:**
- 판 NPC 추가 공격 옵션: `extra_npc_enabled/extra_npc_name` (config), `extra_npc_*.png` (scanner), 듀얼 GUI "판공격" 체크박스
- F11/F9 복귀 개선: `_do_f9_return()` 분리, `_f11_to_zone()` 실패 시 F9 복귀 후 재시도

**How to apply:** 듀얼 관련 수정은 `ent_bot_engine_template.py`만 수정 (CUDA 버전은 듀얼 미사용).
