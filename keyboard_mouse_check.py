"""
키보드 / 마우스 디바이스 확인 및 저장 도구
──────────────────────────────────────────
1. Interception 디바이스 목록 출력
2. auto_capture 로 키보드 / 마우스 감지
3. 각 키보드 후보에 F10 전송 → 사용자 확인
4. 마우스 클릭 테스트
5. 확인된 번호를 ent_config.json / ent_config2.json 에 저장
"""

import os
import json
import time
import win32gui

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# user_config 있으면 거기에 저장 (업데이트 시 보존), 없으면 ent_config에 저장
_CONFIG_PAIRS = [
    ("user_config.json",  "ent_config.json"),
    ("user_config2.json", "ent_config2.json"),
]
WINDOW_TITLE = "Lineage Classic"

# ── Interception import ───────────────────────────────────────
try:
    from interception import (
        auto_capture_devices, set_devices,
        key_down, key_up,
        get_keyboard, get_mouse,
        move_to, mouse_down, mouse_up,
    )
    from interception.inputs import _g_context as _icp_ctx
except ImportError as e:
    print(f"[오류] interception 모듈 로드 실패: {e}")
    print("  → interception-python 설치 및 드라이버 설치 확인")
    input("\n엔터로 종료")
    raise SystemExit(1)


# ── 게임 창 찾기 ──────────────────────────────────────────────
def find_game_windows():
    found = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and WINDOW_TITLE in win32gui.GetWindowText(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            found.append((rect[0], hwnd))
        return True
    win32gui.EnumWindows(cb, None)
    found.sort()
    return [hwnd for _, hwnd in found]


# ── 디바이스 HWID 출력 ────────────────────────────────────────
def print_devices():
    print("=" * 60)
    print("  Interception 디바이스 목록")
    print("=" * 60)
    kb_list, ms_list = [], []
    for i in range(20):
        try:
            dev = _icp_ctx.devices[i]
            hwid = dev.get_HWID() or ""
            if not hwid:
                continue
            valid = dev.handle not in (-1, 0, None)
            kind = "KB " if i < 10 else "MS "
            tag = "유효" if valid else "무효"
            print(f"  [{i:2d}] {kind} [{tag}]  {hwid[:65]}")
            if valid:
                if i < 10:
                    kb_list.append(i)
                else:
                    ms_list.append(i)
        except Exception:
            pass
    print()
    return kb_list, ms_list


# ── 키보드 테스트 ─────────────────────────────────────────────
def test_keyboard(game_hwnd, kb_candidates):
    print("-" * 60)
    print("  [키보드 테스트]")
    print("  각 디바이스로 F10 키를 전송합니다.")
    print("  게임에서 두루마리 창이 뜨면 'y', 아니면 'n' 입력")
    print("-" * 60)

    for idx in kb_candidates:
        set_devices(keyboard=idx)
        print(f"\n  디바이스 [{idx}] — 3초 후 F10 전송...")
        time.sleep(3.0)
        key_down("f10")
        time.sleep(0.1)
        key_up("f10")
        ans = input("  두루마리(또는 인벤) 창이 떴나요? (y/n): ").strip().lower()
        if ans == "y":
            print(f"  ✓ 키보드 디바이스 [{idx}] 확인!")
            return idx
        else:
            print(f"  ✗ [{idx}] 동작 안 함")

    # 후보 없으면 수동 입력
    print("\n  자동 감지된 후보 중 동작하는 디바이스가 없습니다.")
    raw = input("  직접 디바이스 번호 입력 (모르면 엔터 스킵): ").strip()
    if raw.isdigit():
        return int(raw)
    return None


# ── 마우스 테스트 ─────────────────────────────────────────────
def test_mouse(game_hwnd, ms_device):
    print("\n" + "-" * 60)
    print("  [마우스 테스트]")
    if ms_device is not None:
        set_devices(mouse=ms_device)

    rect = win32gui.GetClientRect(game_hwnd)
    pt   = win32gui.ClientToScreen(game_hwnd, (0, 0))
    cx   = pt[0] + (rect[2] - rect[0]) // 2
    cy   = pt[1] + (rect[3] - rect[1]) // 2

    print(f"  3초 후 게임 창 중앙 ({cx}, {cy}) 에 마우스 클릭 전송...")
    time.sleep(3.0)
    try:
        move_to(cx, cy)
        time.sleep(0.05)
        mouse_down("left")
        time.sleep(0.05)
        mouse_up("left")
        print("  클릭 전송 완료")
    except Exception as e:
        print(f"  [오류] {e}")
        return False

    ans = input("  게임 화면에서 마우스 클릭이 반응했나요? (y/n): ").strip().lower()
    return ans == "y"


# ── config 저장 ───────────────────────────────────────────────
def save_to_configs(kb_device, ms_device):
    print()
    for user_fname, base_fname in _CONFIG_PAIRS:
        # user_config 우선, 없으면 ent_config 사용
        user_path = os.path.join(BASE_DIR, user_fname)
        base_path = os.path.join(BASE_DIR, base_fname)
        if os.path.exists(user_path):
            path, fname = user_path, user_fname
        elif os.path.exists(base_path):
            path, fname = base_path, base_fname
        else:
            continue

        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

        changed = False
        if kb_device is not None:
            cfg["keyboard_device"] = kb_device
            changed = True
        if ms_device is not None:
            cfg["mouse_device"] = ms_device
            changed = True

        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(f"  저장 완료: {fname}  KB={kb_device}  MS={ms_device}")


# ── 메인 ──────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("   Lineage Classic 키보드/마우스 디바이스 확인 도구")
    print("=" * 60 + "\n")

    # 1. 디바이스 목록
    kb_list, ms_list = print_devices()

    # 2. 게임 창 확인
    hwnds = find_game_windows()
    if not hwnds:
        print(f"[주의] '{WINDOW_TITLE}' 창을 찾지 못했습니다.")
        print("  게임을 실행한 후 다시 시도하세요.")
        print("  키보드 테스트는 게임 창 없이는 정확하지 않습니다.\n")
        game_hwnd = None
    else:
        game_hwnd = hwnds[0]
        titles = [win32gui.GetWindowText(h) for h in hwnds]
        print(f"게임 창 감지: {titles}")
        print(f"  테스트에 사용할 창: hwnd={game_hwnd}\n")

    # 3. auto_capture 로 초기 감지
    print("Interception auto_capture 실행 중...")
    print("  (마우스를 조금 움직여 주세요)\n")
    auto_capture_devices(keyboard=True, mouse=True, verbose=True)
    time.sleep(0.5)

    detected_kb = get_keyboard()
    detected_ms = get_mouse()
    print(f"\n  auto_capture 결과:  KB={detected_kb}  MS={detected_ms}\n")

    # 4. 키보드 후보 구성 (auto_capture 결과 우선, 나머지 kb_list 보충)
    kb_candidates = []
    if detected_kb is not None and detected_kb not in kb_candidates:
        kb_candidates.append(detected_kb)
    for k in kb_list:
        if k not in kb_candidates:
            kb_candidates.append(k)

    # 5. 키보드 테스트
    final_kb = None
    if game_hwnd:
        print("키보드 테스트를 시작합니다.")
        print("게임 창을 마우스로 클릭해서 활성화해 두세요.\n")
        input("준비되면 엔터...")
        final_kb = test_keyboard(game_hwnd, kb_candidates)
    else:
        raw = input("게임 창 없음 — KB 디바이스 번호를 직접 입력 (스킵: 엔터): ").strip()
        if raw.isdigit():
            final_kb = int(raw)

    # 6. 마우스 테스트
    final_ms = detected_ms
    ms_ok = False
    if game_hwnd:
        ms_ok = test_mouse(game_hwnd, detected_ms)
        if not ms_ok:
            print("  마우스 동작 안 함 — MS 디바이스 번호를 직접 입력")
            raw = input("  MS 번호 (스킵: 엔터): ").strip()
            if raw.isdigit():
                final_ms = int(raw)
    else:
        raw = input("MS 디바이스 번호 직접 입력 (스킵: 엔터): ").strip()
        if raw.isdigit():
            final_ms = int(raw)

    # 7. 결과 출력
    print("\n" + "=" * 60)
    print("  결과 요약")
    print("=" * 60)
    print(f"  키보드 디바이스: {final_kb}  {'✓' if final_kb is not None else '?'}")
    print(f"  마우스  디바이스: {final_ms}  {'✓' if ms_ok else '?'}")

    # 8. 저장 여부
    if final_kb is not None or final_ms is not None:
        ans = input("\nent_config.json / ent_config2.json 에 저장할까요? (y/n): ").strip().lower()
        if ans == "y":
            save_to_configs(final_kb, final_ms)

    print("\n완료.")
    input("엔터로 종료")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("\n" + "=" * 60)
        print("[오류 발생]")
        traceback.print_exc()
        print("=" * 60)
        input("\n엔터로 종료")
