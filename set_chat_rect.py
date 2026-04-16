"""
채팅 영역 지정 도구
───────────────────
게임 화면에서 채팅 영역을 드래그로 지정합니다.
드래그 후 좌표가 출력됩니다.
Q = 종료
"""
import cv2
from capture_window import WindowCapture

WINDOW = "Lineage Classic"
wincap = WindowCapture(WINDOW)

drag_start = None
drag_end = None
dragging = False
result_rect = None

def on_mouse(event, x, y, flags, param):
    global drag_start, drag_end, dragging, result_rect
    if event == cv2.EVENT_LBUTTONDOWN:
        drag_start = (x, y)
        drag_end = (x, y)
        dragging = True
    elif event == cv2.EVENT_MOUSEMOVE and dragging:
        drag_end = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and dragging:
        dragging = False
        drag_end = (x, y)
        x1 = min(drag_start[0], drag_end[0])
        y1 = min(drag_start[1], drag_end[1])
        x2 = max(drag_start[0], drag_end[0])
        y2 = max(drag_start[1], drag_end[1])
        if abs(x2 - x1) > 5 and abs(y2 - y1) > 5:
            result_rect = (x1, y1, x2, y2)
            print(f"\nCHAT_RECT = ({x1}, {y1}, {x2}, {y2})")
            print(f"이 값을 ent_bot.py의 CHAT_RECT에 넣으세요.\n")

cv2.namedWindow("set_chat_rect", cv2.WINDOW_NORMAL)
cv2.resizeWindow("set_chat_rect", 900, 650)
cv2.setMouseCallback("set_chat_rect", on_mouse)

print("채팅 영역을 드래그로 지정하세요. Q=종료\n")

while True:
    frame = wincap.get_screenshot()
    if frame is None:
        cv2.waitKey(100)
        continue
    dbg = frame.copy()

    if result_rect:
        x1, y1, x2, y2 = result_rect
        cv2.rectangle(dbg, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(dbg, f"CHAT_RECT = ({x1},{y1},{x2},{y2})", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    if dragging and drag_start and drag_end:
        x1 = min(drag_start[0], drag_end[0])
        y1 = min(drag_start[1], drag_end[1])
        x2 = max(drag_start[0], drag_end[0])
        y2 = max(drag_start[1], drag_end[1])
        cv2.rectangle(dbg, (x1, y1), (x2, y2), (0, 200, 255), 2)

    cv2.imshow("set_chat_rect", dbg)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
