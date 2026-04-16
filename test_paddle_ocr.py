"""PaddleOCR 엔트 인식 테스트 — 감지 임계값 & 전처리 비교"""
import ssl
import logging
import cv2
import numpy as np

ssl._create_default_https_context = ssl._create_unverified_context
logging.getLogger("ppocr").setLevel(logging.WARNING)

from paddleocr import PaddleOCR
from capture_window import WindowCapture

# OCR scan 영역 (ent_bot_config 기본값)
OCR_RECT = (10, 53, 1272, 696)
NPC_NAME = "엔트"

# 게임 창 캡처
print("게임 창 캡처 중...")
wincap = WindowCapture("Lineage Classic")
frame = wincap.get_screenshot()
if frame is None or frame.size == 0:
    print("[오류] 스크린샷 실패")
    exit(1)
print(f"캡처 완료: {frame.shape[1]}x{frame.shape[0]}")

sx1, sy1, sx2, sy2 = OCR_RECT
game_frame = frame[sy1:sy2, sx1:sx2]
print(f"OCR 영역: ({sx1},{sy1}) ~ ({sx2},{sy2})  크기={game_frame.shape[1]}x{game_frame.shape[0]}")

# 원본 저장
cv2.imwrite("test_ocr_original.png", game_frame)

# ── 전처리 변형들 ──
preprocess = {}
# 1) 원본
preprocess["원본"] = game_frame

# 2) 그레이스케일 + CLAHE (대비 강화)
gray = cv2.cvtColor(game_frame, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)
preprocess["CLAHE"] = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

# 3) 밝기/대비 증가
bright = cv2.convertScaleAbs(game_frame, alpha=2.0, beta=50)
preprocess["밝기x2"] = bright

# 4) 반전 (흰 배경 + 검은 글씨)
inverted = cv2.bitwise_not(game_frame)
preprocess["반전"] = inverted

# ── 테스트: 낮은 임계값 ──
print("\nPaddleOCR 로딩 중 (det_db_box_thresh=0.3) ...")
ocr = PaddleOCR(
    lang="korean",
    use_angle_cls=False,
    det_db_box_thresh=0.3,
    det_db_thresh=0.2,
    drop_score=0.3,
    show_log=False,
)
print("PaddleOCR 로딩 완료\n")

for name, img in preprocess.items():
    print(f"===== [{name}] =====")
    result = ocr.ocr(img, cls=False)
    if result and result[0]:
        for i, line in enumerate(result[0]):
            text = line[1][0]
            conf = line[1][1]
            text_clean = text.strip().replace(" ", "")
            match = "  ★ 엔트!" if NPC_NAME in text_clean else ""
            print(f"  [{i:2d}] '{text}'  conf={conf:.3f}{match}")
    else:
        print("  (인식 결과 없음)")

    # 디버그 이미지 저장
    dbg = img.copy()
    if result and result[0]:
        for line in result[0]:
            bbox = line[0]
            text = line[1][0]
            conf = line[1][1]
            x1 = int(min(bbox[0][0], bbox[3][0]))
            y1 = int(min(bbox[0][1], bbox[1][1]))
            x2 = int(max(bbox[1][0], bbox[2][0]))
            y2 = int(max(bbox[2][1], bbox[3][1]))
            color = (0, 0, 255) if NPC_NAME in text.strip().replace(" ", "") else (0, 255, 0)
            cv2.rectangle(dbg, (x1, y1), (x2, y2), color, 2)
            cv2.putText(dbg, f"{text} {conf:.2f}", (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    cv2.imwrite(f"test_ocr_{name}.png", dbg)
    print()

print("디버그 이미지 저장 완료 (test_ocr_*.png)")
