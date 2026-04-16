"""좌표 확인 도구 - 게임 화면 클릭하면 좌표 출력"""
import cv2
from capture_window import WindowCapture

wc = WindowCapture("Lineage Classic")

def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"클릭 좌표: ({x}, {y})")

cv2.namedWindow("coord", cv2.WINDOW_NORMAL)
cv2.resizeWindow("coord", 900, 650)
cv2.setMouseCallback("coord", on_mouse)

print("게임 화면이 표시됩니다. 원하는 위치를 클릭하세요.")
print("Q = 종료\n")

while True:
    f = wc.get_screenshot()
    cv2.putText(f, "Click to get coords / Q=quit", (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.imshow("coord", f)
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()
print("종료")
