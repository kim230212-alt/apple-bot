"""
템플릿 매칭 스캐너 — OCR 없이 cv2.matchTemplate 사용
──────────────────────────────────────────────────────
ocr_process.py 드롭인 대체. 동일 인터페이스(frame_q/result_q).

templates/npc_*.png    → NPC 감지 (엔트 이름 텍스트)
templates/pickup_*.png → 아이템 감지 (정령의돌 텍스트)

GPU/CPU 환경 동일 인식률, OCR 대비 10~50배 빠름.
"""
import os
import time
import glob

# ── 매칭 임계값 (0.0~1.0, 높을수록 엄격) ──
NPC_THRESHOLD       = 0.70
EXTRA_NPC_THRESHOLD = 0.80   # 추가 NPC(판 등) — 오매칭 방지를 위해 엄격하게
PICKUP_THRESHOLD    = 0.72   # 기본값 (템플릿별 오버라이드 없을 때)

# 픽업 이진화 임계값 — 이 밝기 이상 픽셀만 흰색(255)으로, 나머지는 검정(0)
# 아이템 이름은 흰 텍스트라 배경 종류에 무관하게 안정적으로 추출됨
BINARY_THRESHOLD = 128

# 템플릿별 임계값 오버라이드
PICKUP_THRESHOLDS = {
    "pickup_012.png": 0.80,   # 마력의 돌 — 화살 오매칭 방지
}


def template_process_fn(stop_evt, frame_q, result_q, ready_evt):
    """템플릿 매칭 워커 — 별도 프로세스에서 실행 (GIL 완전 회피)"""
    import cv2
    import numpy as np

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TMPL_DIR = os.path.join(BASE_DIR, "templates")

    # ── NPC 템플릿 로드 (npc_*.png) ──
    npc_templates = []
    for f in sorted(glob.glob(os.path.join(TMPL_DIR, "npc_*.png"))):
        tmpl = cv2.imread(f, cv2.IMREAD_COLOR)
        if tmpl is not None:
            gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            h, w = tmpl.shape[:2]
            name = os.path.basename(f)
            npc_templates.append((gray, h, w, name))
            print(f"[TMPL] NPC 템플릿 로드: {name}  {w}x{h}")

    # ── 줍기 템플릿 로드 (pickup_*.png) — 이진화 전처리 적용 ──
    pickup_templates = []
    for f in sorted(glob.glob(os.path.join(TMPL_DIR, "pickup_*.png"))):
        tmpl = cv2.imread(f, cv2.IMREAD_COLOR)
        if tmpl is not None:
            gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
            h, w = binary.shape[:2]
            name = os.path.basename(f)
            pickup_templates.append((binary, h, w, name))
            print(f"[TMPL] PICKUP 템플릿 로드: {name}  {w}x{h}")

    # ── 추가 NPC 템플릿 로드 (extra_npc_*.png) ──
    extra_npc_templates = []
    for f in sorted(glob.glob(os.path.join(TMPL_DIR, "extra_npc_*.png"))):
        tmpl = cv2.imread(f, cv2.IMREAD_COLOR)
        if tmpl is not None:
            gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            h, w = tmpl.shape[:2]
            name = os.path.basename(f)
            extra_npc_templates.append((gray, h, w, name))
            print(f"[TMPL] EXTRA NPC 템플릿 로드: {name}  {w}x{h}")

    if not npc_templates:
        print("[TMPL] NPC 템플릿 없음! templates/npc_*.png 파일 필요")
        print("[TMPL] capture_npc_template.py 로 캡처하세요")
    if not pickup_templates:
        print("[TMPL] PICKUP 템플릿 없음 (선택사항)")

    ready_evt.set()

    while not stop_evt.is_set():
        # 큐에서 최신 프레임만 꺼냄 (오래된 것 버림)
        data = None
        try:
            while True:
                data = frame_q.get_nowait()
        except Exception:
            pass
        if data is None:
            try:
                data = frame_q.get(timeout=0.1)
            except Exception:
                continue

        frame = data['frame']
        state = data['state']
        fight_npc_pos = data['fight_npc_pos']
        ocr_scan_rect = data['ocr_scan_rect']
        player_pos = data['player_pos']
        npc_pos = data['npc_pos']
        focus_half = data['focus_half']
        extra_npc_enabled = data.get('extra_npc_enabled', False)

        fh, fw = frame.shape[:2]

        # 스캔 영역 결정 (ocr_process와 동일 로직)
        focus_mode = False
        if state in ("FIGHTING", "ATTACK") and fight_npc_pos is not None:
            fcx, fcy = fight_npc_pos
            sx1 = max(0, fcx - focus_half)
            sy1 = max(0, fcy - focus_half - 80)
            sx2 = min(fw, fcx + focus_half)
            sy2 = min(fh, fcy + focus_half)
            focus_mode = True
        else:
            sx1, sy1, sx2, sy2 = ocr_scan_rect

        game_frame = frame[sy1:sy2, sx1:sx2]
        if game_frame.size == 0:
            continue

        game_gray = cv2.cvtColor(game_frame, cv2.COLOR_BGR2GRAY)

        candidates = []
        pickup_pos = None
        pickup_name = None
        debug_results = []

        # ── NPC 템플릿 매칭 ──
        for tmpl_gray, th, tw, name in npc_templates:
            if game_gray.shape[0] < th or game_gray.shape[1] < tw:
                continue

            result = cv2.matchTemplate(game_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)

            # 최고 점수 항상 로그 (진단용)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            print(f"[TMPL] NPC 최고점수={max_val:.3f} (임계값={NPC_THRESHOLD})", flush=True)

            locs = np.where(result >= NPC_THRESHOLD)

            for pt in zip(*locs[::-1]):  # (x, y) 순서
                x1, y1 = int(pt[0]), int(pt[1])
                score = float(result[y1, x1])

                # 단어 경계 검사
                if x1 >= 5:
                    left_strip = game_gray[y1:y1+th, x1-5:x1]
                    if left_strip.size > 0 and np.std(left_strip.astype(np.float32)) > 50:
                        print(f"[TMPL] 경계 검사 탈락 score={score:.3f} x={x1}", flush=True)
                        continue

                debug_results.append(
                    (x1 + sx1, y1 + sy1,
                     x1 + tw + sx1, y1 + th + sy1,
                     name, score)
                )
                cx = x1 + tw // 2 + sx1
                cy = y1 + th + 60 + sy1
                candidates.append((cx, cy, score))

        # NMS: 중복 제거 (가까운 매칭 중 최고 점수만 유지)
        candidates = _nms(candidates, min_dist=40)

        # ── 줍기 템플릿 매칭 — 이진화 후 매칭, 모든 템플릿 중 최고 점수 선택 ──
        _, game_binary = cv2.threshold(game_gray, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
        best_score = -1.0
        for tmpl_gray, th, tw, name in pickup_templates:
            if game_binary.shape[0] < th or game_binary.shape[1] < tw:
                continue

            thresh = PICKUP_THRESHOLDS.get(name, PICKUP_THRESHOLD)
            result = cv2.matchTemplate(game_binary, tmpl_gray, cv2.TM_CCOEFF_NORMED)
            locs = np.where(result >= thresh)

            for pt in zip(*locs[::-1]):
                x1, y1 = int(pt[0]), int(pt[1])
                score = float(result[y1, x1])
                debug_results.append(
                    (x1 + sx1, y1 + sy1,
                     x1 + tw + sx1, y1 + th + sy1,
                     name, score)
                )
                cx = x1 + tw // 2 + sx1
                cy = y1 + th // 2 + sy1
                if cx < 300:  # UI 영역 제외
                    continue
                if score > best_score:
                    best_score = score
                    pickup_pos = (cx, cy)
                    pickup_name = name

        # ── 추가 NPC 템플릿 매칭 (extra_npc_*.png) ──
        extra_npc_found = None
        extra_npc_score = 0.0
        if extra_npc_enabled and extra_npc_templates:
            extra_candidates = []
            for tmpl_gray, th, tw, name in extra_npc_templates:
                if game_gray.shape[0] < th or game_gray.shape[1] < tw:
                    continue
                result = cv2.matchTemplate(game_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                print(f"[TMPL] EXTRA NPC 최고점수={max_val:.3f} (임계값={EXTRA_NPC_THRESHOLD})", flush=True)
                locs = np.where(result >= EXTRA_NPC_THRESHOLD)
                for pt in zip(*locs[::-1]):
                    x1, y1 = int(pt[0]), int(pt[1])
                    score = float(result[y1, x1])
                    cx = x1 + tw // 2 + sx1
                    cy = y1 + th + 60 + sy1
                    extra_candidates.append((cx, cy, score))
            extra_candidates = _nms(extra_candidates, min_dist=40)
            if extra_candidates:
                ref = fight_npc_pos if (state in ("FIGHTING", "ATTACK") and fight_npc_pos) else (npc_pos or player_pos)
                extra_candidates.sort(key=lambda c: abs(c[0] - ref[0]) + abs(c[1] - ref[1]))
                extra_npc_found = (extra_candidates[0][0], extra_candidates[0][1])
                extra_npc_score = extra_candidates[0][2]

        # 가장 가까운 NPC 선택 (ocr_process와 동일 로직)
        npc_found = None
        if candidates:
            if state == "FIGHTING" and fight_npc_pos is not None:
                ref = fight_npc_pos
            elif npc_pos is not None:
                ref = npc_pos
            else:
                ref = player_pos
            candidates.sort(
                key=lambda c: abs(c[0] - ref[0]) + abs(c[1] - ref[1])
            )
            npc_found = (candidates[0][0], candidates[0][1])

        result_q.put({
            'npc': npc_found,
            'extra_npc': extra_npc_found,
            'extra_npc_score': extra_npc_score if extra_npc_found is not None else 0.0,
            'pickup': pickup_pos,
            'pickup_name': pickup_name,
            'pickup_score': best_score if pickup_pos is not None else 0.0,
            'debug_results': debug_results,
        })

        # 템플릿 매칭은 OCR보다 훨씬 빠름 → 짧은 인터벌
        time.sleep(0.05 if focus_mode else 0.15)


def _nms(candidates, min_dist=40):
    """단순 NMS: min_dist 이내 중복 제거 (높은 점수 우선)"""
    if len(candidates) <= 1:
        return candidates
    sorted_c = sorted(candidates, key=lambda c: c[2], reverse=True)
    keep = []
    for c in sorted_c:
        if not any(abs(c[0] - k[0]) + abs(c[1] - k[1]) < min_dist for k in keep):
            keep.append(c)
    return keep
