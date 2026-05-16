"""
픽업 템플릿 캡처 툴 (범용)
──────────────────────────
드롭된 아이템 텍스트 위에 커서 올리고 F5 → 자동 번호로 pickup_NNN.png 저장.

단축키:
  F5  : 커서 위치 주변 캡처 → templates/pickup_NNN.png 저장
  F9  : 저장된 모든 pickup_*.png 로 매칭 테스트
  F12 : 종료

저장 후 콘솔에 아이템 이름 입력하면 주석으로 기록됩니다.
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

CAPTURE_W       = 80
CAPTURE_H       = 18
MATCH_THRESHOLD = 0.72
NMS_RADIUS      = 20


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
            result.append((os.path.basename(f), img))
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


def main():
    cfg    = BotConfig(CONFIG_PATH)
    wincap = WindowCapture(cfg.window_title)
    print(f"[창] '{cfg.window_title}'  {wincap.w}x{wincap.h}")

    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)

    req  = {"cap": False, "match": False, "quit": False}
    size = {"w": CAPTURE_W, "h": CAPTURE_H}

    kb_module.add_hotkey("f5",  lambda: req.update(cap=True))
    kb_module.add_hotkey("f9",  lambda: req.update(match=True))
    kb_module.add_hotkey("f12", lambda: req.update(quit=True))
    kb_module.add_hotkey("+",   lambda: (size.update(w=size["w"] + 5),
                                         print(f"  [크기] {size['w']}x{size['h']}")))
    kb_module.add_hotkey("-",   lambda: (size.update(w=max(20, size["w"] - 5)),
                                         print(f"  [크기] {size['w']}x{size['h']}")))

    print("\n=== 조작 ===")
    print("  F5  : 커서 위치 캡처 → pickup_NNN.png 저장")
    print(f"        캡처 크기: {size['w']}x{size['h']}  (+/- 로 너비 조절)")
    print("  F9  : 저장된 템플릿 전체 매칭 테스트")
    print("  F12 : 종료\n")
    print("사용법: 게임에서 아이템 드롭 → 텍스트 위 커서 → F5\n")

    PREVIEW_SCALE = 6   # 실시간 미리보기 확대 배율
    last_preview_t = 0

    while not req["quit"]:
        # ── 실시간 커서 위치 미리보기 ──
        now = time.time()
        if now - last_preview_t > 0.1:   # 10fps
            last_preview_t = now
            try:
                pt  = win32gui.GetCursorPos()
                pcx = pt[0] - wincap.offset_x
                pcy = pt[1] - wincap.offset_y
                pframe = wincap.get_screenshot()
                if pframe is not None:
                    if pframe.ndim == 3 and pframe.shape[2] == 4:
                        pframe = cv2.cvtColor(pframe, cv2.COLOR_BGRA2BGR)
                    cw, ch = size["w"], size["h"]
                    px1 = max(0, pcx - cw // 2)
                    py1 = max(0, pcy - ch // 2)
                    px2 = min(pframe.shape[1], px1 + cw)
                    py2 = min(pframe.shape[0], py1 + ch)
                    pcrop = pframe[py1:py2, px1:px2]
                    if pcrop.size > 0:
                        pview = cv2.resize(pcrop,
                                           (pcrop.shape[1] * PREVIEW_SCALE,
                                            pcrop.shape[0] * PREVIEW_SCALE),
                                           interpolation=cv2.INTER_NEAREST)
                        cv2.putText(pview, f"F5=저장  {cw}x{ch}  +/-조절",
                                    (4, pview.shape[0] - 4),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 100), 1)
                        cv2.imshow("실시간 미리보기", pview)
                        cv2.waitKey(1)
            except Exception:
                pass

        if req["cap"]:
            req["cap"] = False
            try:
                pt  = win32gui.GetCursorPos()
                cx  = pt[0] - wincap.offset_x
                cy  = pt[1] - wincap.offset_y
                frame = wincap.get_screenshot()
                if frame is None:
                    print("  [오류] 프레임 캡처 실패")
                    continue
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                cw, ch = size["w"], size["h"]
                x1 = max(0, cx - cw // 2)
                y1 = max(0, cy - ch // 2)
                x2 = min(frame.shape[1], x1 + cw)
                y2 = min(frame.shape[0], y1 + ch)
                crop  = frame[y1:y2, x1:x2]
                idx   = next_pickup_idx()
                fname = os.path.join(TEMPLATE_DIR, f"pickup_{idx:03d}.png")
                cv2.imwrite(fname, crop)

                # 미리보기 (4배 확대)
                preview = cv2.resize(crop, (crop.shape[1] * 4, crop.shape[0] * 4),
                                     interpolation=cv2.INTER_NEAREST)
                cv2.imshow("캡처 미리보기", preview)
                cv2.waitKey(1)

                # 디버그용 컬러 원본 저장
                dbg = os.path.join(DEBUG_DIR, f"pickup_{idx:03d}_preview.png")
                cv2.imwrite(dbg, crop)

                print(f"  [저장] {os.path.basename(fname)}  win=({cx},{cy})  {crop.shape[1]}x{crop.shape[0]}")

                # 아이템 이름 기록 (비동기 입력)
                def ask_name(n=idx):
                    name = input(f"  → pickup_{n:03d} 아이템 이름 (Enter 건너뜀): ").strip()
                    if name:
                        log = os.path.join(TEMPLATE_DIR, "pickup_labels.txt")
                        with open(log, "a", encoding="utf-8") as f:
                            f.write(f"pickup_{n:03d}.png = {name}\n")
                        print(f"  [기록] pickup_{n:03d}.png = {name}")
                threading.Thread(target=ask_name, daemon=True).start()

            except Exception as e:
                print(f"  [캡처 오류] {e}")

        if req["match"]:
            req["match"] = False
            templates = load_pickup_templates()
            print(f"\n[매칭] 템플릿 {len(templates)}개 로드")
            if not templates:
                print("  템플릿 없음 — F5로 먼저 캡처하세요")
            else:
                frame = wincap.get_screenshot()
                if frame is None:
                    print("  [오류] 프레임 캡처 실패")
                else:
                    if frame.ndim == 3 and frame.shape[2] == 4:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    hits = []
                    for tname, tmpl in templates:
                        if gray.shape[0] < tmpl.shape[0] or gray.shape[1] < tmpl.shape[1]:
                            continue
                        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
                        ys, xs = np.where(res >= MATCH_THRESHOLD)
                        for y, x in zip(ys, xs):
                            th, tw = tmpl.shape[:2]
                            hits.append((tname, float(res[y, x]),
                                         x + tw // 2, y + th // 2,
                                         (x, y, x + tw, y + th)))
                    hits = nms(hits)
                    print(f"  히트 {len(hits)}개 (threshold={MATCH_THRESHOLD})")
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

        time.sleep(0.05)

    cv2.destroyAllWindows()
    print("\n종료")


if __name__ == "__main__":
    main()
