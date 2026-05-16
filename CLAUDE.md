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
python ent_bot_gui.py          # CUDA 버전 (단일)
python ent_bot_gui_template.py # 템플릿 버전 (단일)
python ent_bot_gui_dual.py     # 듀얼 버전 (두 창 동시, 단일 프로세스)
run_dual.bat                   # 듀얼 버전 관리자 권한 자동 실행
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

### 2026-05-15 작업 — 듀얼 봇 (단일 프로세스)

#### 신규 파일
- **`ent_bot_gui_dual.py`**: 단일 프로세스에서 두 봇 동시 실행 GUI
  - `BotPanel(ttk.LabelFrame)`: 봇 1개 제어 패널 (시작/정지/일시정지, 로그, 혈맹창고/랜덤순찰 체크박스, 자동접속 버튼)
  - `DualBotGUI`: 두 패널 좌우 배치, 860×700 창
  - Bot 1: `ent_config.json`, `init_delay=0.0` / Bot 2: `ent_config2.json`, `init_delay=3.0` (auto_capture 경쟁 방지)
  - F12 전체 긴급종료 핫키
- **`run_dual.bat`**: UAC 관리자 권한 자동 상승 후 `ent_bot_gui_dual.py` 실행
- **`ent_config2.json`**: Bot 2 설정 파일 (`window_index=1`, `keyboard_device=0`, `mouse_device=13`)

#### `ent_bot_engine_template.py` 수정 (듀얼 지원)
- **Windows 포그라운드 잠금 비활성화**: `initialize()`에서 `SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0)` 호출
- **디바이스 캐시**: `keyboard_device` + `mouse_device` 둘 다 JSON에 있으면 `auto_capture_devices` 생략 (두 봇 동시 시작 시 경쟁 방지)
- **`_ensure_focus()`**: `AttachThreadInput + SetForegroundWindow` + 30ms×3회 재시도, `GetForegroundWindow()` 검증
- **`_main_loop` 예외 래퍼**: 봇 스레드 예외 시 traceback 로그 후 정지 (무음 죽음 방지)

#### `capture_window.py` 수정
- **dxcam 스레드 안전**: 모듈 레벨 `_dxcam_locks: dict[int, threading.Lock]`
  - 같은 `output_idx` 카메라를 두 스레드가 동시에 `grab()` 하면 `DXGI_ERROR_INVALID_CALL` 발생 → output별 Lock으로 직렬화

#### 포커스 리스 시스템 (`ent_bot_engine_template.py`)
- **배경**: Bot 2 스크롤이 Bot 1 창고 작업 중인 창에 들어가는 문제 (포커스 레이스 컨디션)
- **`_focus_lease_hwnd`**: 모듈 레벨 전역 변수 (0=독점 없음, 비-0=해당 hwnd 독점 중)
- **`_acquire_focus_lease()`**: 창고 등 장기 작업 시작 시 호출 → 타 엔진 포커스 전환 차단
- **`_release_focus_lease()`**: 작업 완료 또는 `stop()` 시 해제
- **`_run_warehouse()`**: `_acquire_focus_lease()` / `finally: _release_focus_lease()` 래핑
- **`_wait_for_lease(timeout=120s)`**: 다른 엔진이 리스 보유 중이면 락 밖에서 최대 120초 대기 후 진행. `_ikey`, `_ipress`, `_iscroll`, `_click_move` 모두 락 획득 전에 호출
  - 대기 시작 시 `"[대기] 다른 봇 창고 작업 중 — 포커스 리스 해제 대기"` 로그

#### `_scroll_return` 수정
- **`_ikey_force(key, max_wait=5s)`**: 포커스 확립 실패 시 0.3초 간격으로 최대 5초 재시도. F9/F11 등 반드시 눌려야 하는 키 전용 (기존 `_ikey`는 90ms 후 조용히 실패)
- **F9, F5, F11** → `_ikey_force` 사용
- **최대 재시도 5회** 추가 → 무한루프 방지, 초과 시 현재 위치에서 패트롤 시작
- **F11 후 대기 1초 → 3초** (텔레포트 로딩 시간 확보)
- **zone 임계값 0.821 → 0.70** (실제 score 0.51~0.59 측정됨, 조정 필요 시 `_is_in_zone` 참고)

### 2026-05-16 작업

#### 판 NPC 추가 공격 옵션 (`extra_npc_enabled`)
- `ent_bot_config.py`: `extra_npc_enabled=False`, `extra_npc_name="판"` 추가, `_PERSIST_KEYS` 등록
- `template_scanner.py`: `extra_npc_*.png` 별도 로드, `extra_npc_enabled` 플래그 수신, 결과에 `extra_npc` 포함
- `ent_bot_engine_template.py`: `_find_npc()`에서 primary NPC 없을 때 extra_npc fallback
- `ent_bot_gui_template.py`: "추가 공격 (판)" 체크박스 추가
- `ent_bot_gui_dual.py`: "판공격" 체크박스 추가
- `ent_config.json`, `ent_config2.json`: `extra_npc_enabled: true` 추가
- 템플릿 파일: `templates/extra_npc_001.png` (판 NPC 이름 텍스트 캡처)

#### F11/F9 복귀 로직 개선 (`ent_bot_engine_template.py`)
- **`_do_f9_return()`** 신규: F9 → 3초 → F5×3 → 5초 공용 복귀 시퀀스
- **`_f11_to_zone()`**: F11 후 요정 숲 아니면 `_do_f9_return()` 호출 후 재시도 (기존: F11만 반복)
- **`_scroll_return()`**: `_do_f9_return()` + `_f11_to_zone()` 조합으로 단순화 (순환 없음)
- 사망(`_handle_death`) / 부활 실패(`_handle_revive_fail`) 모두 `_f11_to_zone()` 호출이므로 자동 적용

### 2026-05-17 작업

#### 듀얼 모드 키보드 device 유효성 검증
- **문제**: config에 저장된 `keyboard_device=0`이 다른 컴퓨터에서 다른 장치 번호일 수 있음
  - 단일 봇은 동작하는데 듀얼 실행 시 키보드 안 되는 현상 (일부 PC)
- **수정** (`ent_bot_engine_template.py`, `ent_bot_engine.py` 양쪽):
  - `_kb_valid(k)`: device handle 유효성 검사 함수 추가
  - `initialize()`: 캐시된 KB device가 유효하면 그대로 사용, 유효하지 않으면 `_device_detect_lock` 잡고 `auto_capture_devices` 재감지
  - 재감지 후 config에 저장 → 다음 실행부터 올바른 번호 사용
- **`_device_detect_lock`**: 모듈 레벨 `threading.Lock()` — 듀얼 모드에서 두 봇이 동시에 auto_capture 호출하는 race condition 방지

#### 픽업 템플릿 캡처 툴 범용화 (`capture_pickup_template.py`)
- 기존: 미스릴/버섯포자 2종 고정 (F5/F6)
- 변경: 아이템 종류 제한 없이 **F5 → pickup_NNN.png 자동 번호 저장**
- 저장 후 콘솔에 이름 입력 → `templates/pickup_labels.txt` 기록
- `+`/`-` 키로 캡처 너비 실시간 조절 (기본 80×18px)
- **실시간 미리보기 창**: 커서 위치 ROI를 6배 확대로 10fps 표시 → 텍스트 잘림 전에 확인 가능
- F9 매칭 테스트 + 결과 오버레이 이미지 표시

#### 픽업 anchor 슬라이딩 시각화 테스트 (`test_pickup_anchor.py`)
- **문제**: 픽업 주우러 가다가 캐릭터가 우회하는 현상
  - 원인: 슬라이딩 anchor — 캐릭터 이동 시 카메라 따라 이동 → 아이템 화면 좌표 변화 → anchor 업데이트 → 매 클릭마다 방향 재조정 → 직선이 아닌 우회 경로
- **테스트 스크립트**: 실제 클릭 없이 시각화만
  - 노란선: anchor 이동 경로
  - 초록 박스: stick_radius 내 유효 감지
  - 빨간 박스: radius 밖 무효 감지 (miss 카운트)
  - 파란 원: 현재 anchor + stick_radius 범위
  - `q`=종료, `s`=스냅샷, `c`=경로 초기화

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
