# Ent Bot - Lineage Classic 자동 사냥 봇

## 프로젝트 개요
리니지 클래식(Lineage Classic) 게임에서 "엔트" NPC를 자동으로 사냥하는 봇.
Python + OpenCV + EasyOCR + Interception 드라이버 기반.

## 핵심 구조
- `ent_bot_gui.py` — tkinter GUI (메인 실행 진입점: `python ent_bot_gui.py`)
- `ent_bot_engine.py` — 봇 엔진 (상태머신 기반 사냥 로직)
- `ent_bot_config.py` — 설정 관리 클래스 (BotConfig)
- `ent_config.json` — 런타임 설정값 (좌표, 타이밍 등)
- `ent_bot.py` — 단독 실행용 봇 (GUI 없는 버전)
- `capture_window.py` — 게임 창 캡처 (dxcam)
- `ocr_process.py` — OCR 처리
- `Interception/` — 키보드/마우스 입력 라이브러리
- `templates/` — 이미지 템플릿 (NPC, 아이템, UI 버튼)

## _template 파일
- `ent_bot_engine_template.py`, `ent_bot_gui_template.py` — 배포용 템플릿 버전. 수정 시 본체(`_template` 없는 파일)를 수정할 것.

## 주요 의존성
numpy, opencv-python, pywin32, keyboard, easyocr, dxcam, interception-python, Pillow

## 실행 방법
```
python ent_bot_gui.py
```

## 설정
`ent_config.json`에서 좌표, 타이밍, NPC 이름 등 조정.
게임 창 이름: "Lineage Classic"
