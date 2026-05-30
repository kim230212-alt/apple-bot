@echo off
chcp 65001 > nul
echo ============================================
echo   Ent Bot - 의존성 설치
echo ============================================
echo.

:: 관리자 권한 확인
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] 관리자 권한으로 실행하세요.
    echo 이 파일을 우클릭 → "관리자 권한으로 실행"
    pause
    exit /b 1
)

:: Python 확인
echo [1/4] Python 확인 중...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Python이 설치되어 있지 않습니다.
    echo.
    echo https://www.python.org/downloads/ 에서
    echo Python 3.10 또는 3.11을 설치하세요.
    echo.
    echo 설치 옵션에서 "Add Python to PATH" 반드시 체크!
    echo.
    pause
    exit /b 1
)
python --version

:: pip 업그레이드
echo.
echo [2/4] pip 업그레이드 중...
python -m pip install --upgrade pip -q

:: 패키지 설치
echo.
echo [3/4] 패키지 설치 중...
pip install numpy opencv-python pywin32 keyboard dxcam Pillow requests interception-python -q

if %errorlevel% neq 0 (
    echo.
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)
echo 패키지 설치 완료

:: Interception 드라이버 설치
echo.
echo [4/4] Interception 드라이버 설치 중...
if exist "Interception\command line installer\install-interception.exe" (
    "Interception\command line installer\install-interception.exe" /install
    echo Interception 드라이버 설치 완료
    echo.
    echo [중요] 드라이버 적용을 위해 재부팅이 필요합니다.
) else if exist "Interception\install-interception.exe" (
    "Interception\install-interception.exe" /install
    echo Interception 드라이버 설치 완료
    echo.
    echo [중요] 드라이버 적용을 위해 재부팅이 필요합니다.
) else if exist "interception_install.bat" (
    call interception_install.bat
) else (
    echo [경고] Interception 설치 파일을 찾을 수 없습니다.
    echo Interception 폴더가 있는지 확인하세요.
)

echo.
echo ============================================
echo   설치 완료!
echo   재부팅 후 launcher.exe를 실행하세요.
echo ============================================
pause
