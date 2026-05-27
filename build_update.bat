@echo off
chcp 65001 > nul
echo ============================================
echo   update.zip + version.json 생성
echo   (NAS /update/ 폴더에 업로드용)
echo ============================================
echo.

set /p VER=버전 입력 (예: 1.0.5):
if "%VER%"=="" (
    echo 버전을 입력하세요.
    pause
    exit /b 1
)

:: 임시 폴더 정리
if exist _update_pkg rmdir /s /q _update_pkg

:: 폴더 구조 생성
mkdir _update_pkg\app
mkdir _update_pkg\templates

:: ===== 앱 소스 복사 (설정 파일 제외) =====
echo 소스 파일 복사 중...

copy ent_bot_gui_dual.py       _update_pkg\app\ > nul
copy ent_bot_gui_template.py   _update_pkg\app\ > nul
copy ent_bot_engine_template.py _update_pkg\app\ > nul
copy ent_bot_config.py         _update_pkg\app\ > nul
copy auto_login.py             _update_pkg\app\ > nul
copy capture_window.py         _update_pkg\app\ > nul
copy template_scanner.py       _update_pkg\app\ > nul
copy input_lock.py             _update_pkg\app\ > nul
copy ocr_process.py            _update_pkg\app\ > nul
copy keyboard_mouse_check.py   _update_pkg\app\ > nul
copy coord_picker.py           _update_pkg\app\ > nul
copy run_dual.bat              _update_pkg\app\ > nul

:: 설정 파일 기본값 (첫 실행용 — 이미 있으면 런처가 스킵함)
copy ent_config.json           _update_pkg\app\ > nul
copy ent_config2.json          _update_pkg\app\ > nul
copy auto_login_config.json    _update_pkg\app\ > nul

:: templates 폴더 복사
echo 템플릿 복사 중...
xcopy templates _update_pkg\templates /s /e /y /q > nul

:: Interception 폴더 (있으면 복사)
if exist Interception (
    echo Interception 복사 중...
    xcopy Interception _update_pkg\Interception /s /e /y /q > nul
)

:: zip 생성 (PowerShell)
echo.
echo update.zip 생성 중...
if exist update.zip del update.zip
powershell -Command "Compress-Archive -Path '_update_pkg\*' -DestinationPath 'update.zip' -Force"

if not exist update.zip (
    echo [오류] zip 생성 실패
    rmdir /s /q _update_pkg
    pause
    exit /b 1
)

:: version.json 생성
echo {"version": "%VER%", "file": "update.zip"} > version.json

:: 임시 폴더 정리
rmdir /s /q _update_pkg

echo.
echo ============================================
echo   생성 완료!
echo.
echo   update.zip   ^(%.0f KB^)
echo   version.json ^(버전: %VER%^)
echo.
echo   [NAS 업로드 방법]
echo   두 파일을 Synology NAS의
echo   /update/ 공유 폴더에 업로드하세요.
echo ============================================
pause
