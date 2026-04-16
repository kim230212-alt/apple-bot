@echo off
title Interception Install
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   관리자 권한으로 실행하세요!
    echo.
    pause
    exit /b
)
cd /d "%~dp0"
echo.
echo   Interception 드라이버 설치 중...
echo.
"%~dp0Interception\command line installer\install-interception.exe" /install
echo.
echo   완료! PC를 재부팅하세요.
echo.
pause
