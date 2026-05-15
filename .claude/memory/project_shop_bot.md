---
name: shop_bot 작업 내역
description: C:\shop 폴더의 shop_bot.py, shop_step3.py 주요 수정 내역 및 구조
type: project
originSessionId: 0fef196b-ccb7-47f6-a313-995286f10300
---
## 파일 구조 (C:\shop)
- `shop_bot.py` — 통합 봇 (상점 개설 → 물품 등록 → 모니터링 → 창고 보충 무한루프)
- `shop_step3.py` — 혈맹창고 인출 단독 실행 스크립트
- `shop_config.json` — 런타임 설정 (아이템, 가격, 모니터 주기 등)
- `templates/ent_stem.png` — 인벤토리용 엔트의줄기 아이콘 (품질 낮음, 재캡처 권장)
- `templates/wh_ent_stem.png` — 창고용 엔트의줄기 아이콘 (정상, score=0.989)
- `templates/warehouse_keeper.png` — 창고지기 NPC 라벨 템플릿

## 주요 수정 내역

### 창고지기 NPC 감지 (shop_bot.py, shop_step3.py)
- `NPC_THRESHOLD`: 0.78 → 0.45 (마을마다 조명 다름, 그레이스케일 매칭으로 변경)
- `npc_tmpl_gray` 추가, `cv2.matchTemplate(gray, npc_tmpl_gray, ...)` 로 전환
- **Why**: 4개 마을에서 threshold 0.78 기준 1개 마을 미감지 → 0.45로 낮추면 전 마을 정상

### 마우스 커서 가림 방지 (shop_bot.py, shop_step3.py)
- 아이템 스캔 전 `move_to(SAFE_MOUSE_POS)` + 0.15s 대기 추가
- `SAFE_MOUSE_POS = (500, 600)` — 인벤/창고 리스트 ROI 밖 오른쪽
- **Why**: 마우스가 아이템 아이콘 위에 있으면 score 0.605 → 0.312 수준으로 떨어져 미감지

### 인벤 아이템 미감지 시 창고 자동 보충 (shop_bot.py)
- `phase_register_items()` 수정: 못 찾은 아이템은 `return False` 대신 스킵
- 스킵된 아이템 → `last_sold.txt`에 기록 → 사이클 말미 창고 단계에서 자동 보충
- `run_one_cycle()`: 등록된 아이템 0개이면 상점 취소 후 창고 직행
- **Why**: `ent_stem.png` 템플릿 품질 낮아 score=0.312, 한 아이템 실패 시 전체 사이클 실패 방지

### 모니터링 주기 (shop_config.json)
- `monitor_poll_sec`: 60.0 → 5.0
- **Why**: 60초 폴링이면 miss_frames=3 기준 최대 3분 후 감지 → 5초로 낮춰 15초 이내 감지

## 좌표 정보
- `INVENTORY_RECT = (940, 0, 1280, 500)` — 인벤토리 스캔 영역
- `WH_ITEM_LIST_ROI = (0, 60, 290, 530)` — 혈맹창고 리스트 영역
- `WAREHOUSE_MENU_POS = (77, 345)` — "혈맹창고 물건 찾는다" 메뉴 클릭 위치
- `WH_OK_POS = (294, 553)` — 혈맹창고 수량 입력 OK

## 미해결
- `templates/ent_stem.png` 품질 낮음 (score 낮게 나옴) → `python test_inv_item.py` 실행 후 엔트의줄기 위에서 S키로 재캡처 권장
- `last_sold.txt` 에 현재 `엔트의열매`, `엔트의줄기` 기록됨 (창고 보충 대기 중)

**How to apply**: C:\shop 관련 작업 시 위 수정 내역 참고. 좌표 수정 시 반드시 coord_picker.py 사용.
