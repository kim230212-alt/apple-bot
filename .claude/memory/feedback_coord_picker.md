---
name: 좌표 찍기 도구 사용 규칙
description: 게임 좌표 확인 시 반드시 coord_picker.py로 Lineage Classic 창을 인식하여 게임 창 기준 좌표를 사용해야 함
type: feedback
originSessionId: 1db39315-9028-4415-b0cf-c88d131cafa7
---
게임 좌표를 찍거나 확인할 때는 반드시 `coord_picker.py`를 실행해서 Lineage Classic 창을 인식한 뒤 게임 창 기준 좌표를 사용할 것.

**Why:** 사용자가 명시적으로 요구. 절대 스크린 좌표(pyautogui 등)가 아닌 게임 창 내부 기준 좌표만 유효함.

**How to apply:** 좌표 관련 작업 시 coord_picker.py 실행을 먼저 안내하거나, 좌표를 직접 계산할 때 WindowCapture 기반 게임 창 좌표 기준으로 처리.
