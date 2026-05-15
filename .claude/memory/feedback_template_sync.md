---
name: 템플릿 버전만 수정
description: ent_bot_engine.py (CUDA) 절대 수정 금지, template 버전만 수정
type: feedback
originSessionId: 0fef196b-ccb7-47f6-a313-995286f10300
---
`ent_bot_engine_template.py`, `ent_bot_gui_template.py`만 수정할 것. `ent_bot_engine.py`, `ent_bot_gui.py`는 절대 수정 금지.

**Why:** 사용자가 CUDA 버전은 더 이상 사용하지 않음. 2026-05-15 명시적으로 지시.

**How to apply:** 어떤 기능 추가/수정이든 _template.py 파일만 변경. ent_bot_config.py, ent_config.json, auto_login.py 등 공용 파일은 예외.
