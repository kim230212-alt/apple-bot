"""
OCR 서브프로세스 — PaddleOCR GIL-free 실행
───────────────────────────────────────────
메인 프로세스의 키보드/마우스 입력이 OCR에 의해
블로킹되지 않도록 별도 프로세스에서 실행.
"""
import os
import ssl
import time
import logging


def ocr_process_fn(stop_evt, frame_q, result_q, ready_evt):
    """PaddleOCR 워커 — 별도 프로세스에서 실행 (GIL 완전 회피)"""
    ssl._create_default_https_context = ssl._create_unverified_context
    logging.getLogger("ppocr").setLevel(logging.WARNING)

    from paddleocr import PaddleOCR

    try:
        ocr = PaddleOCR(
            lang="korean", use_angle_cls=False,
            det_db_box_thresh=0.3, det_db_thresh=0.2,
            drop_score=0.3, show_log=False,
        )
    except Exception:
        try:
            ocr = PaddleOCR(
                lang="korean", det_db_box_thresh=0.3,
                det_db_thresh=0.2, drop_score=0.3, show_log=False,
            )
        except Exception:
            ocr = PaddleOCR(show_log=False)

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
        npc_name = data['npc_name']
        pickup_conf = data['pickup_conf']
        pickup_exclude = data['pickup_exclude']
        pickup_keyword = data.get('pickup_keyword', ['정령'])  # 하위 호환
        player_pos = data['player_pos']
        npc_pos = data['npc_pos']
        focus_half = data['focus_half']
        ocr_interval = data['ocr_interval']

        fh, fw = frame.shape[:2]

        # 스캔 영역 결정
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

        try:
            ocr_result = ocr.ocr(game_frame, cls=False)
        except Exception:
            continue

        candidates = []
        pickup_pos = None
        debug_results = []

        if ocr_result and ocr_result[0]:
            for line in ocr_result[0]:
                bbox = line[0]
                text = line[1][0]
                conf = line[1][1]

                x1 = int(min(bbox[0][0], bbox[3][0]))
                y1 = int(min(bbox[0][1], bbox[1][1]))
                x2 = int(max(bbox[1][0], bbox[2][0]))
                y2 = int(max(bbox[2][1], bbox[3][1]))
                debug_results.append(
                    (x1 + sx1, y1 + sy1, x2 + sx1, y2 + sy1, text, conf)
                )
                text_clean = text.strip().replace(" ", "")

                if npc_name in text_clean:
                    cx = (x1 + x2) // 2 + sx1
                    cy = y2 + 60 + sy1
                    candidates.append((cx, cy, conf))

                if (
                    any(kw in text_clean for kw in pickup_keyword)
                    and not any(ex in text_clean for ex in pickup_exclude)
                    and conf >= pickup_conf
                    and pickup_pos is None
                ):
                    cx = (x1 + x2) // 2 + sx1
                    cy = (y1 + y2) // 2 + sy1
                    pickup_pos = (cx, cy)

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
            cx, cy, conf = candidates[0]
            npc_found = (cx, cy)

        result_q.put({
            'npc': npc_found,
            'pickup': pickup_pos,
            'debug_results': debug_results,
        })

        time.sleep(0.15 if focus_mode else ocr_interval)
