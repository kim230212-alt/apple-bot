"""
/위치 입력 테스트
─────────────────
게임 채팅창에 /위치 명령을 입력합니다.
Enter 누르면 실행, Q = 종료
"""
import time
import subprocess
from interception import auto_capture_devices, press, key_down, key_up, set_devices

print("디바이스 감지 중... (마우스 움직여주세요)")
auto_capture_devices(keyboard=True, mouse=True, verbose=True)
print()

def type_location_cmd():
    """/위치 입력 — 한글 키 직접 타이핑"""
    # Enter로 채팅 열기
    press('enter')
    time.sleep(0.3)
    # "/" 입력 (영문 모드)
    press('/')
    time.sleep(0.2)
    # 한/영 전환 (한글 모드로)
    press('hangul')
    time.sleep(0.2)
    # 위 = ㅇ(d) + ㅜ(n) + ㅣ(l)
    press('d')
    time.sleep(0.05)
    press('n')
    time.sleep(0.05)
    press('l')
    time.sleep(0.1)
    # 치 = ㅊ(c) + ㅣ(l)
    press('c')
    time.sleep(0.05)
    press('l')
    time.sleep(0.2)
    # 한/영 전환 (영문 모드로 복귀)
    press('hangul')
    time.sleep(0.1)
    # Enter로 전송
    press('enter')
    time.sleep(0.5)
    print("[OK] /위치 입력 완료")

print("게임 창을 활성화한 후 Enter를 누르세요.")
print("Q = 종료\n")

while True:
    cmd = input("Enter=실행, Q=종료: ").strip().lower()
    if cmd == 'q':
        break
    print("3초 후 실행...")
    time.sleep(3.0)
    type_location_cmd()

print("종료")
