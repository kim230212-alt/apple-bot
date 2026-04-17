# Ent Bot - Lineage Classic 자동 사냥 봇

## 프로젝트 개요
리니지 클래식(Lineage Classic) 게임에서 "엔트" NPC를 자동으로 사냥하는 봇.
Python + OpenCV + EasyOCR + Interception 드라이버 기반.

## 두 가지 버전
- **CUDA(OCR) 버전**: `ent_bot_engine.py` + `ent_bot_gui.py` — EasyOCR로 NPC 인식 (GPU 필요)
- **템플릿 버전**: `ent_bot_engine_template.py` + `ent_bot_gui_template.py` — cv2.matchTemplate로 NPC 인식 (GPU 불필요)
- 수정 시 반드시 양쪽 버전 동시 수정할 것

## 핵심 구조
- `ent_bot_gui.py` / `ent_bot_gui_template.py` — tkinter GUI
- `ent_bot_engine.py` / `ent_bot_engine_template.py` — 봇 엔진 (상태머신 기반 사냥 로직)
- `ent_bot_config.py` — 설정 관리 클래스 (BotConfig)
- `ent_config.json` — 런타임 설정값 (좌표, 타이밍 등)
- `auto_login.py` — 자동 로그인 (런처→동의서→서버→로그인→캐릭터)
- `auto_login_config.json` — 자동 로그인 설정 (서버, 계정, 캐릭터)
- `capture_window.py` — 게임 창 캡처 (dxcam)
- `Interception/` — 키보드/마우스 입력 라이브러리 (scroll 함수 포함)
- `templates/` — 이미지 템플릿 (NPC, 아이템, UI 버튼)
- `templates/login/` — 로그인용 템플릿 (동의 버튼, OK 버튼, 페이지 버튼)

## 주요 의존성
numpy, opencv-python, pywin32, keyboard, easyocr, dxcam, interception-python, Pillow

## 실행 방법
```
python ent_bot_gui.py          # CUDA 버전
python ent_bot_gui_template.py # 템플릿 버전
```

## 설정
`ent_config.json`에서 좌표, 타이밍, NPC 이름 등 조정.
게임 창 이름: "Lineage Classic"

## 최근 작업 및 미해결 이슈

### 완료
- 창고 맡기기 시 스크롤 검색 기능 (`_deposit_items` → `_scroll_to_bottom` + `_find_item_with_scroll`)
- 자동 로그인 GUI 연동 (엔진에서 제거, GUI에 "자동 접속" 버튼 추가)
- 2페이지 서버 버튼을 템플릿 매칭으로 변경

### 미해결: 2페이지 버튼 클릭 안 됨
- 템플릿 매칭은 정상 (신뢰도 1.0으로 위치 찾음)
- `grab_frame`(BitBlt)으로 찾은 좌표로 `click_at` 하면 클릭이 안 먹힘
- 원인 추정: `grab_frame`(BitBlt)과 `dxcam` 캡처 간 좌표 차이 가능성
- `test_page2_click.py`로 두 캡처 방식의 좌표 차이 확인 필요
- 서버 리스트 화면에서 `python test_page2_click.py` 실행하면 진단 가능
- "어레인"(1페이지) 서버 기준 고정 좌표는 정상 동작 확인됨
