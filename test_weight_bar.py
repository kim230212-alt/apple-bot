"""
무게바 색상 테스트
- 게임 창 캡처 후 무게바 ROI HSV값 실시간 출력
- 'q' 종료, 's' 현재 값 스냅샷
"""
import cv2
import numpy as np
from capture_window import WindowCapture

WINDOW_NAME = "Lineage Classic"
WINDOW_INDEX = 0  # 0=왼쪽창, 1=오른쪽창

# 무게바 좌표 (coord_picker로 찍은 값)
BAR_X1, BAR_Y1 = 46, 855
BAR_X2, BAR_Y2 = 102, 876

wincap = WindowCapture(WINDOW_NAME, WINDOW_INDEX)

print("무게바 색상 테스트 시작")
print("'q' 종료 / 's' 스냅샷")
print(f"바 범위: ({BAR_X1},{BAR_Y1}) ~ ({BAR_X2},{BAR_Y2})")
print("-" * 50)

while True:
    frame = wincap.get_screenshot()
    bar_roi = frame[BAR_Y1:BAR_Y2, BAR_X1:BAR_X2]
    hsv = cv2.cvtColor(bar_roi, cv2.COLOR_BGR2HSV)

    # 색상별 픽셀 비율
    green_mask  = (hsv[:,:,0] >= 35) & (hsv[:,:,0] <= 85) & (hsv[:,:,1] > 80)
    yellow_mask = (hsv[:,:,0] >= 25) & (hsv[:,:,0] <= 35) & (hsv[:,:,1] > 80)
    orange_mask = (hsv[:,:,0] >= 10) & (hsv[:,:,0] <= 25) & (hsv[:,:,1] > 120) & (hsv[:,:,2] > 80)
    red_mask    = (hsv[:,:,0] <= 10) & (hsv[:,:,1] > 120) & (hsv[:,:,2] > 80)
    total = hsv.shape[0] * hsv.shape[1]

    g = np.sum(green_mask)  / total
    y = np.sum(yellow_mask) / total
    o = np.sum(orange_mask) / total
    r = np.sum(red_mask)    / total

    # 평균 HSV
    mean_h = int(np.mean(hsv[:,:,0]))
    mean_s = int(np.mean(hsv[:,:,1]))
    mean_v = int(np.mean(hsv[:,:,2]))

    print(f"\r초록={g:.3f}  노랑={y:.3f}  주황={o:.3f}  빨강={r:.3f}  |  평균HSV=({mean_h},{mean_s},{mean_v})    ", end="")

    # 시각화 창
    bar_big = cv2.resize(bar_roi, (bar_roi.shape[1]*6, bar_roi.shape[0]*6), interpolation=cv2.INTER_NEAREST)
    cv2.imshow("weight bar", bar_big)

    key = cv2.waitKey(200)
    if key == ord('q'):
        break
    if key == ord('s'):
        print(f"\n[스냅샷] 초록={g:.3f}  노랑={y:.3f}  주황={o:.3f}  빨강={r:.3f}  평균HSV=({mean_h},{mean_s},{mean_v})")

cv2.destroyAllWindows()
print("\n종료")
