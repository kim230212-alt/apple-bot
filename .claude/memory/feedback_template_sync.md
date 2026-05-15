---
name: 템플릿 버전만 수정
description: 엔진/GUI 수정 시 _template 파일만 수정, 비템플릿 파일은 건드리지 않음
type: feedback
originSessionId: fb75a470-d804-477e-91ee-17fbd6aac61b
---
이제부터 ent_bot_engine_template.py, ent_bot_gui_template.py만 수정할 것.

**Why:** 사용자가 템플릿 버전만 사용하므로 비템플릿 파일(ent_bot_engine.py, ent_bot_gui.py) 수정 불필요.

**How to apply:** 코드 수정 요청 시 _template.py 파일만 수정. 단, ent_bot_config.py, ent_config.json, auto_login.py 등 공용 파일은 예외.
