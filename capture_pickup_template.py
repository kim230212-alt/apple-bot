"""
픽업 템플릿 캡처 툴 (박스 선택)
──────────────────────────────────
F5  : 게임 화면 캡처 → 드래그로 영역 선택 → Enter 저장 / ESC 취소
F9  : 저장된 모든 pickup_*.png 로 매칭 테스트
F12 : 종료

selectROI 조작:
  드래그   : 박스 그리기
  Enter    : 선택 영역 저장
  ESC/Space: 취소
"""
import os
import sys
import time
import glob
import threading
import cv2
import numpy as np
import win32gui
import keyboard as kb_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_window import WindowCapture
from ent_bot_config import BotConfig

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
DEBUG_DIR    = os.path.join(BASE_DIR, "debug_pickup_template")
CONFIG_PATH  = os.path.join(BASE_DIR, "ent_config.json")

MATCH_THRESHOLD  = 0.72
MATCH_THRESHOLDS = {
    "pickup_012.png": 0.80,   # 마력의 돌 — 화살 오매칭 방지
}
NMS_RADIUS       = 50
BINARY_THRESHOLD = 128   # 흰 텍스트 추출 임계값


def next_pickup_idx():
    idx = 0
    for f in glob.glob(os.path.join(TEMPLATE_DIR, "pickup_*.png")):
        name = os.path.splitext(os.path.basename(f))[0].replace("pickup_", "")
        if name.isdigit():
            idx = max(idx, int(name))
    return idx + 1


def load_pickup_templates():
    result = []
    for f in sorted(glob.glob(os.path.join(TEMPLATE_DIR, "pickup_*.png"))):
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            _, binary = cv2.threshold(img, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
            result.append((os.path.basename(f), binary))
    return result


def nms(hits, radius=NMS_RADIUS):
    hits.sort(key=lambda h: -h[1])
    final = []
    r2 = radius ** 2
    for h in hits:
        cx, cy = h[2], h[3]
        if any((cx - f[2]) ** 2 + (cy - f[3]) ** 2 < r2 for f in final):
            continue
        final.append(h)
    return final


def do_capture(wincap):
    frame = wincap.get_screenshot()
    if frame is None:
        print("  [오류] 프레임 캡처 실패")
        return
    if frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    # 절반 크기로 축소해서 선택창 표시 (큰 화면 대응)
    scale = 0.75
    h, w = frame.shape[:2]
    disp = cv2.resize(frame, (int(w * scale), int(h * scale)))

    print("  [선택] 드래그로 박스 그리고 Enter=저장 / ESC=취소")
    cv2.namedWindow("영역 선택 (Enter=저장 ESC=취소)", cv2.WINDOW_NORMAL)
    rx, ry, rw, rh = cv2.selectROI(
        "영역 선택 (Enter=저장 ESC=취소)",
        disp,
        showCrosshair=False,
        fromCenter=False,
    )
    cv2.destroyWindow("영역 선택 (Enter=저장 ESC=취소)")

    if rw == 0 or rh == 0:
        print("  [취소] 선택 없음")
        return

    # 원본 좌표로 역변환
    ox = int(rx / scale)
    oy = int(ry / scale)
    ow = int(rw / scale)
    oh = int(rh / scale)
    crop = frame[oy:oy + oh, ox:ox + ow]

    idx   = next_pickup_idx()
    fname = os.path.join(TEMPLATE_DIR, f"pickup_{idx:03d}.png")
    cv2.imwrite(fname, crop)

    # 미리보기 (4배 확대)
    ph, pw = crop.shape[:2]
    preview = cv2.resize(crop, (pw * 4, ph * 4), interpolation=cv2.INTER_NEAREST)
    cv2.imshow("캡처 미리보기", preview)
    cv2.waitKey(1)

    dbg = os.path.join(DEBUG_DIR, f"pickup_{idx:03d}_preview.png")
    cv2.imwrite(dbg, crop)

    print(f"  [저장] {os.path.basename(fname)}  게임좌표=({ox},{oy})  {ow}x{oh}px")

    def ask_name(n=idx):
        name = input(f"  → pickup_{n:03d} 아이템 이름 (Enter 건너뜀): ").strip()
        if name:
            log = os.path.join(TEMPLATE_DIR, "pickup_labels.txt")
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"pickup_{n:03d}.png = {name}\n")
            print(f"  [기록] pickup_{n:03d}.png = {name}")
    threading.Thread(target=ask_name, daemon=True).start()


def do_match(wincap, scan_rect=None):
    templates = load_pickup_templates()
    print(f"\n[매칭] 템플릿 {len(templates)}개 로드")
    if not templates:
        print("  템플릿 없음 — F5로 먼저 캡처하세요")
        return

    frame = wincap.get_screenshot()
    if frame is None:
        print("  [오류] 프레임 캡처 실패")
        return
    if frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    # ROI 적용 (엔진과 동일한 ocr_scan_rect 범위만 탐색)
    if scan_rect is not None:
        sx1, sy1, sx2, sy2 = scan_rect
        print(f"  [ROI] x={sx1}~{sx2}  y={sy1}~{sy2}")
    else:
        sx1, sy1, sx2, sy2 = 0, 0, frame.shape[1], frame.shape[0]

    roi = frame[sy1:sy2, sx1:sx2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, gray = cv2.threshold(gray, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
    hits = []
    for tname, tmpl in templates:
        if gray.shape[0] < tmpl.shape[0] or gray.shape[1] < tmpl.shape[1]:
            continue
        thr = MATCH_THRESHOLDS.get(tname, MATCH_THRESHOLD)
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        _, best_val, _, best_loc = cv2.minMaxLoc(res)
        if best_val < thr:
            print(f"  [미달] {tname}  최고점수={best_val:.3f}  임계값={thr:.2f}")
            continue
        ys, xs = np.where(res >= thr)
        for y, x in zip(ys, xs):
            th, tw = tmpl.shape[:2]
            hits.append((tname, float(res[y, x]),
                         x + tw // 2 + sx1, y + th // 2 + sy1,
                         (x + sx1, y + sy1, x + tw + sx1, y + th + sy1)))
    hits = nms(hits)
    print(f"  히트 {len(hits)}개 (threshold={MATCH_THRESHOLD}, 개별 오버라이드 적용)")
    vis = frame.copy()
    for (tname, score, mcx, mcy, bb) in hits:
        x1, y1, x2, y2 = bb
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 100), 2)
        cv2.putText(vis, f"{tname}:{score:.2f}", (x1, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 100), 1)
        print(f"    {tname}  score={score:.3f}  @({mcx},{mcy})")
    ts = time.strftime("%H%M%S")
    dbg = os.path.join(DEBUG_DIR, f"{ts}_match.png")
    cv2.imwrite(dbg, vis)
    cv2.imshow("매칭 결과", cv2.resize(vis, (vis.shape[1] // 2, vis.shape[0] // 2)))
    cv2.waitKey(1)
    print(f"  [디버그] {os.path.basename(dbg)}")


def main():
    cfg    = BotConfig(CONFIG_PATH)
    wincap = WindowCapture(cfg.window_title)
    print(f"[창] '{cfg.window_title}'  {wincap.w}x{wincap.h}")

    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)

    req = {"cap": False, "match": False, "quit": False}

    kb_module.add_hotkey("f5",  lambda: req.update(cap=True))
    kb_module.add_hotkey("f9",  lambda: req.update(match=True))
    kb_module.add_hotkey("f12", lambda: req.update(quit=True))

    print("\n=== 조작 ===")
    print("  F5  : 게임 화면 캡처 → 드래그로 영역 선택 → Enter 저장")
    print("  F9  : 저장된 템플릿 전체 매칭 테스트")
    print("  F12 : 종료\n")
    print("사용법: 게임에서 아이템 드롭 확인 → F5 → 텍스트 위 박스 드래그 → Enter\n")

    while not req["quit"]:
        if req["cap"]:
            req["cap"] = False
            try:
                do_capture(wincap)
            except Exception as e:
                print(f"  [캡처 오류] {e}")

        if req["match"]:
            req["match"] = False
            try:
                do_match(wincap, scan_rect=tuple(cfg.ocr_scan_rect))
            except Exception as e:
                print(f"  [매칭 오류] {e}")

        cv2.waitKey(50)

    cv2.destroyAllWindows()
    print("\n종료")


if __name__ == "__main__":
    main()
