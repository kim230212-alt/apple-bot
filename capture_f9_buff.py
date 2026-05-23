"""F9 세계수 복귀 버프 아이콘 캡처 도구

실행:
  python capture_f9_buff.py

조작:
  드래그 → 버프 아이콘 ROI 선택
  Enter  → 저장 (templates/f9_buff.png)
  R      → 다시 선택
  Q      → 종료
"""

import sys, os
import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "templates", "f9_buff.png")

sys.path.insert(0, BASE_DIR)
from capture_window import WindowCapture

wc = WindowCapture("Lineage Classic")

print("F9를 눌러 세계수 복귀 버프가 뜬 상태에서 실행하세요.")
print("버프 아이콘을 드래그로 선택 → Enter 저장 / R 재선택 / Q 종료\n")

while True:
    f = wc.get_screenshot()
    if f is None:
        print("캡처 실패")
        continue
    if f.ndim == 3 and f.shape[2] == 4:
        f = cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)

    cv2.putText(f, "버프 아이콘을 드래그 선택 후 Enter / Q=종료",
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
    cv2.imshow("capture_f9_buff", f)
    cv2.waitKey(1)

    roi = cv2.selectROI("capture_f9_buff", f, fromCenter=False, showCrosshair=True)
    x, y, w, h = roi
    if w == 0 or h == 0:
        print("선택 취소")
        continue

    crop = f[y:y+h, x:x+w]
    cv2.imshow("preview", crop)
    print(f"선택: ({x},{y}) {w}×{h}  →  Enter=저장  R=재선택")
    key = cv2.waitKey(0) & 0xFF
    if key == 13:  # Enter
        cv2.imwrite(OUT_PATH, crop)
        print(f"[저장] {OUT_PATH}")
        break
    elif key == ord("q"):
        break

cv2.destroyAllWindows()
print("종료")
