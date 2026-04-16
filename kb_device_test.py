"""
키보드 디바이스 진단
─────────────────────
send 성공/실패 확인 + 실제 디바이스 감지
"""
import time
import json
import os
from interception.inputs import _g_context
from interception.constants import FilterKeyFlag, KeyFlag
from interception.strokes import KeyStroke
from interception._keycodes import get_key_information
from interception import auto_capture_devices, set_devices, get_keyboard

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "ent_config.json")

print("=" * 50)
print("  키보드 디바이스 진단")
print("=" * 50)
print()

print("[1] 디바이스 감지 중... (마우스 움직여주세요)")
auto_capture_devices(keyboard=True, mouse=True, verbose=True)
print()

# 각 디바이스 핸들 상태 확인
print("[2] 키보드 디바이스 핸들 상태:")
for i in range(10):
    dev = _g_context.devices[i]
    hwid = dev.get_HWID()
    handle_ok = dev.handle not in (-1, 0, None)
    status = f"handle={'OK' if handle_ok else 'INVALID'}  HWID={hwid[:50] if hwid else 'None'}"
    print(f"  [{i}] {status}")
print()

# 각 디바이스로 send 테스트 (결과 확인)
print("[3] 각 디바이스 send 테스트 (Enter 키):")
enter_info = get_key_information('enter')
for i in range(10):
    dev = _g_context.devices[i]
    hwid = dev.get_HWID()
    if not hwid:
        continue
    try:
        stroke = KeyStroke(enter_info.scan_code, KeyFlag.KEY_DOWN)
        result = dev.send(stroke)
        stroke_up = KeyStroke(enter_info.scan_code, KeyFlag.KEY_UP)
        result_up = dev.send(stroke_up)
        print(f"  [{i}] send DOWN={result.succeeded}  UP={result_up.succeeded}")
    except Exception as e:
        print(f"  [{i}] send 오류: {e}")
print()

# 실제 키보드 캡처 (글로벌 컨텍스트 사용)
print("[4] 키보드 캡처 테스트")
print("    키보드 아무 키나 눌러주세요... (5초 대기)")
print()

# 필터 설정
_g_context.set_filter(_g_context.is_keyboard, FilterKeyFlag.FILTER_KEY_ALL)

detected = None
try:
    device = _g_context.await_input(timeout_milliseconds=5000)
    if device is not None:
        stroke = _g_context.devices[device].receive()
        if stroke is not None:
            _g_context.send(device, stroke)  # 키 통과
            hwid = _g_context.devices[device].get_HWID() or "?"
            print(f"    감지! 디바이스={device}  HWID={hwid[:50]}")
            detected = device
    else:
        print("    타임아웃 - 키 입력 감지 안 됨")
except Exception as e:
    print(f"    캡처 오류: {e}")
finally:
    # 필터 해제 (0 = 필터 없음)
    _g_context.set_filter(_g_context.is_keyboard, 0)

if detected is not None:
    cur = get_keyboard()
    if detected != cur:
        print(f"    auto_capture={cur} vs 실제={detected} → 불일치!")
    print()
    print("[5] 감지된 디바이스로 전송 테스트")
    print("    게임 창을 활성화하세요.")
    input("    준비되면 Enter...")
    print("    3초 후 'a' 키를 전송합니다 (메모장으로 테스트 추천)...")
    time.sleep(3.0)
    set_devices(keyboard=detected)
    a_info = get_key_information('a')
    stroke_d = KeyStroke(a_info.scan_code, KeyFlag.KEY_DOWN)
    stroke_u = KeyStroke(a_info.scan_code, KeyFlag.KEY_UP)
    r1 = _g_context.devices[detected].send(stroke_d)
    time.sleep(0.05)
    r2 = _g_context.devices[detected].send(stroke_u)
    print(f"    전송 완료! DOWN={r1.succeeded} UP={r2.succeeded}")
    print()
    result = input("'a'가 입력됐나요? (Y/N): ").strip().lower()
    if result == 'y':
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["keyboard_device"] = detected
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"\n[저장] keyboard_device = {detected}")
    else:
        print("\n드라이버 send는 성공하지만 입력이 안 되는 상태입니다.")
        print("Windows 보안 업데이트로 드라이버가 차단됐을 수 있습니다.")
        print("  → install.bat 관리자 실행 후 리부트")
else:
    print()
    print("키보드 캡처 실패!")
    print("드라이버가 키보드 이벤트를 가로채지 못하는 상태입니다.")
    print("  → install.bat 관리자 실행 후 리부트")

print("\n종료")
