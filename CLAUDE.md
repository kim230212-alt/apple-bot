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
- 창고 맡기기 시 스크롤 검색 기능 (초기 `_deposit_items` → `_scroll_to_bottom` + `_find_item_with_scroll`)
- 자동 로그인 GUI 연동 (엔진에서 제거, GUI에 "자동 접속" 버튼 추가)
- 2페이지 서버 버튼을 템플릿 매칭으로 변경

### 2026-04-22 작업 (2차)
- **자동 로그인 skip 버튼 추가** (서버 선택 ↔ 로그인 사이, 주 1회 업데이트 공지):
  - `templates/login/skip_btn.png` 신규 (skip.png에서 크롭)
  - `auto_login.py`: `tmpl_skip` 로드 + 서버 선택 완료 직후 [4.5/6] 블록 추가 (8초 타임아웃, 폴링 0.3s)
  - 없으면 조용히 통과, 있으면 1회 클릭 후 진행
- **다른 PC 크래시 수정** (`ent_bot_gui*.py`가 `self.config.deposit_items` 참조):
  - `ent_bot_config.py`에 `deposit_items` 추가 (6개 품목, 기본 전부 enabled)
  - `_PERSIST_KEYS`에 `"deposit_items"` 추가
  - 양쪽 엔진 `_deposit_items()`에서 `cfg.deposit_items` enabled 플래그로 필터링 (GUI 체크박스 ↔ 실제 동작 연동)
- **픽업 슬라이딩 anchor + 세션 간 지속** (왔다갔다 해결):
  - `_run_pickup_until_gone` `stick_radius` 60 → 100 (세션 내 드리프트 허용 확대)
  - 세션 내: 반경 내 감지 시 `ix,iy` 및 클릭 좌표 `sx,sy`를 감지 좌표로 슬라이드 → 같은 아이템이 카메라 이동으로 화면 흘러도 캐릭터가 계속 따라감
  - 세션 간: `_last_pickup_anchor`, `_last_pickup_anchor_t` 저장. 다음 세션이 3초 내 + 180px 이내면 이전 anchor 재사용 → 클러스터 픽업 시 반복 재걸음 방지
  - 양쪽 엔진 동시 수정
- **픽업 템플릿별 임계값** (`template_scanner.py`):
  - `PICKUP_THRESHOLDS` dict 추가 — 파일명별 threshold 오버라이드
  - `pickup_001.png` / `pickup_002.png` ("정령의 돌") → 0.85 (엄격: 화살/오크 아이템 등과 교차 매칭 방지)
  - `pickup_003.png` / `pickup_004.png` → 0.72 (기본값 유지)

### 2026-04-21 ~ 04-22 작업
- **픽업 템플릿 확장**: `pickup_003.png`(버섯포자의 즙), `pickup_004.png`(미스릴 원석) 추가
- **스캐너 개선** (`template_scanner.py`):
  - 픽업 매칭 시 "첫 매치"가 아니라 **모든 템플릿 중 최고 점수** 선택 (`best_score` 로직)
  - 결과에 `pickup_name`, `pickup_score` 포함 → 엔진 로그에 파일명 + 점수 표시
  - `PICKUP_THRESHOLD` 0.85 → 0.72 (낮춤 + 교차 오매칭 방지 위해 다시 소폭 상향)
- **창고 맡기기 재설계** (`_deposit_items` 양쪽 엔진):
  - 기존 "맨 아래→스크롤 업" 방식은 여러 아이템 검색 시 과거 탐색이 스크롤 위로 이동시켜 아래쪽 아이템 미발견 문제 발생
  - 새 방식: `_scroll_to_top` → 원패스로 아래 스크롤하며 **모든 후보를 매 스텝 동시 체크**
  - `_scroll_to_bottom` / `_find_item_with_scroll` 제거
  - 품목 추가: 버섯포자의 즙(`ent_mushroom.png`), 미스릴 원석(`ent_mithril.png`), 엔트의 껍질(`ent_bark.png`)
  - 신규 품목은 `required=False` 로 로드 → 파일 없어도 에러 안 남
- **`capture_templates.py` 모드 추가**: 5=`ent_mushroom.png`, 6=`ent_mithril.png`, 7=`ent_bark.png`
- **HP 초록 감지 → F8** (물약 자동 사용):
  - 좌표: `hp_pos=(552, 768)`, 체크 주기 `hp_check_interval=10.0s`, 쿨타임 `hp_f8_cooldown=3.0s`
  - 녹색 HSV 범위 `(40<=H<=85, S>100, V>80)`, 10×6 ROI 에서 비율 > 30% 시 F8 1회
  - `_check_hp_green_and_press` 메서드 추가, 메인 루프에서 상태 관계없이 호출
- **픽업 "사라질 때까지" 로직** (`_run_pickup_until_gone`):
  - 기존 LMB-hold 방식이 리니지 자동 픽업을 못 돌리는 경우 발견 → **반복 클릭** 으로 전환
  - 초기 좌표 고정 (`pos` 갱신 안 함), 비교도 `initial_pos` 기준 → 다중 아이템 상황에서 왔다갔다 제거
  - `stick_radius=60px`, `miss_confirm=4`, `max_duration=15s`, 로그에 클릭 횟수 표시
- **픽업 1순위 보장**: `_do_approach`에도 픽업 체크 추가 (엔트로 접근 중에도 아이템 보이면 중단하고 줍기)

### 미해결: 2페이지 버튼 클릭 안 됨 (이전부터)
- 템플릿 매칭은 정상 (신뢰도 1.0으로 위치 찾음)
- `grab_frame`(BitBlt)으로 찾은 좌표로 `click_at` 하면 클릭이 안 먹힘
- 원인 추정: `grab_frame`(BitBlt)과 `dxcam` 캡처 간 좌표 차이 가능성
- `test_page2_click.py`로 진단 필요
- "어레인"(1페이지) 서버 기준 고정 좌표는 정상 동작 확인됨

### 미해결: 엔트 NPC 감지 안 되는 것 같음 (2026-04-22 발견)
- 사용자 보고: 화면에 엔트가 보이는데 봇이 PATROL만 반복하고 APPROACH 전환 안 함
- `[TMPL] '엔트' 발견 → ...` 로그가 전혀 안 나옴
- 스캐너 NPC 매칭 코드(`template_scanner.py`의 NPC 블록)는 이번 수정에서 안 건드림
- `NPC_THRESHOLD = 0.70` 그대로
- 확인할 것:
  - 봇 시작 시 `[TMPL] NPC 템플릿 로드: npc_*.png` 개수 로그
  - 실제로 엔트가 화면 내 `ocr_scan_rect` 영역 안에 있는지
  - 스캐너 프로세스가 정상 기동됐는지 (`템플릿 스캐너 로딩 완료`)
