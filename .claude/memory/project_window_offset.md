---
name: 게임 창 오프셋 및 좌표 변환
description: 게임 창 오프셋과 pyautogui → 게임 창 좌표 변환 방법
type: project
originSessionId: fb75a470-d804-477e-91ee-17fbd6aac61b
---
게임 창 오프셋: **(27, 63)** (로그: `창 감지 완료 (27, 63)`)

pyautogui 스크린 좌표 → ent_config.json 게임 창 좌표 변환:
- x = 스크린_x - 27
- y = 스크린_y - 63

**Why:** `_click_move`는 게임 창 기준 좌표를 받아 `get_screen_position`으로 변환. pyautogui는 절대 스크린 좌표를 반환하므로 반드시 오프셋을 빼야 함.

**How to apply:** 사용자가 pyautogui로 좌표를 알려주면 항상 오프셋을 빼서 변환 후 config에 저장.
