"""
Ctrl+Q 입력 테스트
──────────────────
사망 상태에서 Ctrl+Q가 동작하는지 테스트합니다.
Enter 누르면 3초 후 실행, Q = 종료
"""
import time
from interception import auto_capture_devices, press, key_down, key_up, set_devices

print("디바이스 감지 중... (마우스 움직여주세요)")
auto_capture_devices(keyboard=True, mouse=True, verbose=True)
print()

def test_ctrl_q():
    print("[1] key_down('ctrl') + key_down('q') 홀드 방식")
    key_down('ctrl')
    time.sleep(0.3)
    key_down('q')
    time.sleep(0.5)
    key_up('q')
    time.sleep(0.2)
    key_up('ctrl')
    print("    완료\n")

def test_ctrl_q2():
    print("[2] key_down('ctrl') + press('q') 방식")
    key_down('ctrl')
    time.sleep(0.3)
    press('q')
    time.sleep(0.3)
    key_up('ctrl')
    print("    완료\n")

def test_esc_then_ctrl_q():
    print("[3] ESC 먼저 → Ctrl+Q 홀드")
    key_down('esc')
    time.sleep(0.3)
    key_up('esc')
    time.sleep(1.0)
    key_down('ctrl')
    time.sleep(0.3)
    key_down('q')
    time.sleep(0.5)
    key_up('q')
    time.sleep(0.2)
    key_up('ctrl')
    print("    완료\n")

print("게임 사망 상태에서 테스트하세요.")
print("1 = 홀드 방식")
print("2 = press 방식")
print("3 = ESC → Ctrl+Q")
print("Q = 종료\n")

while True:
    cmd = input("번호 입력: ").strip().lower()
    if cmd == 'q':
        break
    print("3초 후 실행...")
    time.sleep(3.0)
    if cmd == '1':
        test_ctrl_q()
    elif cmd == '2':
        test_ctrl_q2()
    elif cmd == '3':
        test_esc_then_ctrl_q()
    else:
        print("1, 2, 3 중 선택\n")

print("종료")
