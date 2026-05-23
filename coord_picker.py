"""좌표 확인 도구 - 게임 화면 클릭하면 좌표 + BGR 출력"""
import cv2
import numpy as np
from capture_window import WindowCapture

wc = WindowCapture("Lineage Classic")
last_frame = [None]

def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        f = last_frame[0]
        if f is not None:
            fh, fw = f.shape[:2]
            if 0 <= x < fw and 0 <= y < fh:
                b, g, r = int(f[y, x][0]), int(f[y, x][1]), int(f[y, x][2])
                print(f"좌표: ({x}, {y})  BGR=({b},{g},{r})  RGB=({r},{g},{b})")
            else:
                print(f"좌표: ({x}, {y})  (범위 밖)")
        else:
            print(f"좌표: ({x}, {y})")

cv2.namedWindow("coord", cv2.WINDOW_NORMAL)
cv2.resizeWindow("coord", 900, 650)
cv2.setMouseCallback("coord", on_mouse)

print("게임 화면이 표시됩니다. 원하는 위치를 클릭하면 좌표와 BGR 값이 출력됩니다.")
print("MP 바 위를 클릭해서 색상 확인  |  Q = 종료\n")

while True:
    f = wc.get_screenshot()
    if f is not None:
        if f.ndim == 3 and f.shape[2] == 4:
            f = cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)
        last_frame[0] = f.copy()
        cv2.putText(f, "Click=좌표+BGR확인 / Q=종료", (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imshow("coord", f)
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()
print("종료")
