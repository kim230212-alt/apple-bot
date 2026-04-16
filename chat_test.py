"""
채팅 공격 메시지 감지 테스트
─────────────────────────────
게임에서 엔트를 공격한 상태로 실행하면
1) 템플릿 매칭 score 확인
2) 채팅 영역 변화 감지 확인
Q = 종료
"""
import os
import cv2
import numpy as np
import time
from capture_window import WindowCapture

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW = "Lineage Classic"

# 채팅 영역
CHAT_RECT = (220, 900, 520, 935)

# 템플릿
CHAT_ATK_PATH = os.path.join(BASE_DIR, "templates", "chat_attack.png")
chat_atk_tmpl = cv2.imread(CHAT_ATK_PATH, cv2.IMREAD_COLOR)
if chat_atk_tmpl is not None:
    print(f"템플릿 로딩 OK  {chat_atk_tmpl.shape[1]}x{chat_atk_tmpl.shape[0]}")
else:
    print(f"[경고] 템플릿 없음: {CHAT_ATK_PATH}")

wincap = WindowCapture(WINDOW)
print(f"창 감지 완료\n")

prev_chat = None
cv2.namedWindow("chat_test", cv2.WINDOW_NORMAL)
cv2.resizeWindow("chat_test", 800, 200)

while True:
    frame = wincap.get_screenshot()
    if frame is None or frame.size == 0:
        time.sleep(0.1)
        continue

    x1, y1, x2, y2 = CHAT_RECT
    chat_roi = frame[y1:y2, x1:x2]

    # 1) 템플릿 매칭
    tmpl_score = 0.0
    if chat_atk_tmpl is not None and chat_roi.size > 0:
        result = cv2.matchTemplate(chat_roi, chat_atk_tmpl, cv2.TM_CCOEFF_NORMED)
        _, tmpl_score, _, max_loc = cv2.minMaxLoc(result)

    # 2) 채팅 변화 감지
    changed = False
    diff_val = 0
    if prev_chat is not None and chat_roi.shape == prev_chat.shape:
        diff = cv2.absdiff(chat_roi, prev_chat)
        diff_val = int(np.sum(diff))
        changed = diff_val > 5000

    # 표시
    dbg = chat_roi.copy()
    color = (0, 255, 0) if changed else (0, 0, 255)
    cv2.putText(dbg, f"Template: {tmpl_score:.3f}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
    cv2.putText(dbg, f"Change: {diff_val}  {'YES' if changed else 'NO'}", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
    cv2.imshow("chat_test", dbg)

    prev_chat = chat_roi.copy()

    if cv2.waitKey(200) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
print("종료")
