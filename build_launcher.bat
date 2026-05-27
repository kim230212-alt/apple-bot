@echo off
chcp 65001 > nul
echo ============================================
echo   launcher.exe 빌드 (PyArmor + PyInstaller)
echo ============================================
echo.

:: 도구 확인 및 설치
echo [1/4] 도구 확인 중...
pip install pyarmor pyinstaller requests -q
if %errorlevel% neq 0 (
    echo [오류] 패키지 설치 실패
    pause & exit /b 1
)

:: 이전 빌드 정리
if exist _armored  rmdir /s /q _armored
if exist dist\launcher.exe del /q dist\launcher.exe

:: PyArmor 난독화
echo.
echo [2/4] PyArmor 난독화 중...
pyarmor gen --output _armored launcher.py
if %errorlevel% neq 0 (
    echo [오류] PyArmor 난독화 실패
    pause & exit /b 1
)
echo 난독화 완료: _armored\launcher.py

:: PyInstaller 빌드 (난독화된 코드 사용)
echo.
echo [3/4] PyInstaller 빌드 중...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name launcher ^
    --add-data "_armored\pyarmor_runtime_*;pyarmor_runtime_*" ^
    --hidden-import requests ^
    --hidden-import tkinter ^
    --hidden-import uuid ^
    _armored\launcher.py

if %errorlevel% neq 0 (
    echo [오류] PyInstaller 빌드 실패
    pause & exit /b 1
)

:: 배포 폴더 구성
echo.
echo [4/4] 배포 폴더 구성 중...
set DIST=dist\ent_bot_deploy
if exist %DIST% rmdir /s /q %DIST%
mkdir %DIST%

copy dist\launcher.exe       %DIST%\  > nul
copy launcher_config.json    %DIST%\  > nul
copy install_deps.bat        %DIST%\  > nul

:: 임시 정리
rmdir /s /q _armored
if exist build rmdir /s /q build
if exist launcher.spec del launcher.spec

echo.
echo ============================================
echo   빌드 완료!
echo   배포 폴더: %DIST%
echo.
echo   [배포 파일 목록]
echo   - launcher.exe         (실행 파일)
echo   - launcher_config.json (NAS URL/계정 설정)
echo   - install_deps.bat     (최초 1회 설치)
echo.
echo   [다음 단계]
echo   1. %DIST%\launcher_config.json 에
echo      실제 NAS URL / 계정 입력
echo   2. NAS /update/ 에 licenses.json 업로드
echo      (PC ID 추가 후)
echo   3. %DIST% 폴더를 다른 PC에 복사
echo ============================================
pause
