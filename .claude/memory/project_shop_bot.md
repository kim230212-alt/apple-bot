---
name: shop_bot 작업 내역
description: C:\shop 폴더의 shop_bot.py 구조, 주요 수정 내역, 좌표/템플릿 정보
type: project
originSessionId: 0fef196b-ccb7-47f6-a313-995286f10300
---
## 파일 구조 (C:\shop)
- `shop_bot.py` — 통합 봇 (상점 개설 → 물품 등록 → 모니터링 → 창고 보충 무한루프)
- `shop_step3.py` — 혈맹창고 인출 단독 실행 스크립트
- `shop_config.json` — 런타임 설정 (아이템, 가격, 모니터 주기 등)
- `CLAUDE.md` — 프로젝트 상세 문서 (로직/좌표/템플릿 전체 정리)

## 주요 수정 내역

### 창고지기 NPC 감지
- `NPC_THRESHOLD`: 0.78 → 0.45 (마을마다 조명 다름, 그레이스케일 매칭으로 변경)
- **Why**: 4개 마을에서 threshold 0.78 기준 1개 마을 미감지

### 마우스 커서 가림 방지
- 아이템 스캔 전 `move_to(SAFE_MOUSE_POS=(500,600))` + 0.15s 대기
- **Why**: 마우스가 아이콘 위에 있으면 score 0.605 → 0.312 수준으로 떨어져 미감지

### 인벤 아이템 미감지 시 창고 자동 보충
- 못 찾은 아이템 → 스킵 후 `last_sold.txt`에 보충 예약 (사이클 말미에 창고 보충)
- 등록 아이템 0개이면 상점 취소 후 창고 직행
- **Why**: `ent_stem.png` 품질 낮아 score=0.312, 한 아이템 실패 시 전체 사이클 실패 방지

### 모니터링 주기
- `monitor_poll_sec`: 60.0 → 5.0
- **Why**: 60초 폴링이면 miss_frames=3 기준 최대 3분 후 감지 → 5초로 낮춰 15초 이내 감지

## 좌표 정보
- `INVENTORY_RECT = (940, 0, 1280, 500)` — 인벤토리 스캔 영역
- `WH_ITEM_LIST_ROI = (0, 60, 290, 530)` — 혈맹창고 리스트 영역
- `WAREHOUSE_MENU_POS = (77, 345)` — "혈맹창고 물건 찾는다" 메뉴 클릭 위치
- `WH_OK_POS = (294, 553)` — 혈맹창고 수량 입력 OK
- `SAFE_MOUSE_POS = (500, 600)` — 캡처 전 마우스 대피

## 미해결
- `templates/ent_stem.png` 품질 낮음 → `python test_inv_item.py` 후 S키로 재캡처 권장

**How to apply**: C:\shop 관련 작업 시 위 수정 내역 참고. 좌표 수정 시 반드시 coord_checker.py 사용.
