@echo off
setlocal EnableDelayedExpansion
title ENT BOT Installer

:: Check admin privileges
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo ============================================
    echo   Admin privileges required!
    echo   Right-click - Run as administrator
    echo ============================================
    echo.
    pause
    exit /b
)

cd /d "%~dp0"

echo.
echo ============================================
echo   ENT BOT Installer
echo ============================================
echo.

:: ── [1/5] Python 3.11 ──
echo [1/5] Checking Python 3.11...
py -3.11 --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Python 3.11 not found. Downloading...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '!temp!\python311_installer.exe' -UseBasicParsing"
    if !errorlevel! neq 0 (
        echo [ERROR] Python download failed
        echo Download manually: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
        goto :end
    )
    echo Installing Python 3.11.9...
    "!temp!\python311_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    if !errorlevel! neq 0 (
        echo [ERROR] Python install failed
        goto :end
    )
    echo [OK] Python 3.11.9 installed
) else (
    echo [OK] Python 3.11 found
)
echo.

:: ── [2/5] pip packages ──
echo [2/5] Installing packages...
py -3.11 -m pip install --upgrade pip >nul 2>&1
py -3.11 -m pip install -r "%~dp0requirements.txt"
if !errorlevel! neq 0 (
    echo [ERROR] Package install failed
    goto :end
)
py -3.11 -m pip uninstall opencv-python-headless -y >nul 2>&1
py -3.11 -m pip install opencv-python --force-reinstall >nul 2>&1
py -3.11 -m pip install certifi --upgrade >nul 2>&1
echo.
echo [OK] All packages installed
echo.

:: ── [3/5] PyTorch CUDA ──
echo [3/5] PyTorch CUDA...
py -3.11 -c "import torch; exit(0 if torch.cuda.is_available() else 1)" 2>nul
if !errorlevel! equ 0 (
    echo [OK] PyTorch CUDA ready
    goto :skip_torch
)
echo Installing PyTorch CUDA version...
py -3.11 -m pip uninstall torch torchvision -y >nul 2>&1
py -3.11 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
py -3.11 -c "import torch; print('PyTorch CUDA installed')"
:skip_torch
echo.

:: ── [4/5] SSL fix for EasyOCR ──
echo [4/5] SSL certificate fix...
py -3.11 -c "import ssl; print('SSL OK')" >nul 2>&1
py -3.11 -c "import certifi; import os; os.environ['SSL_CERT_FILE']=certifi.where(); import urllib.request; urllib.request.urlopen('https://www.google.com')" >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] SSL issue detected - will use fallback mode
) else (
    echo [OK] SSL OK
)
echo.

:: ── [5/5] Interception driver ──
echo [5/5] Interception driver...
set "DRIVER=%~dp0Interception\command line installer\install-interception.exe"
if not exist "!DRIVER!" (
    echo [ERROR] Interception installer not found
    goto :end
)
"!DRIVER!" /install
if !errorlevel! neq 0 (
    echo [INFO] Already installed or needs reboot
) else (
    echo [OK] Interception driver installed
)

:: ── [DONE] Device detection ──
echo.
echo ============================================
echo   Detecting keyboard/mouse devices...
echo ============================================
py -3.11 -c "from interception import auto_capture_devices; auto_capture_devices(keyboard=True, mouse=True, verbose=True)" 2>nul
echo.

echo ============================================
echo   INSTALL COMPLETE!
echo   1. Reboot your PC
echo   2. Run: run.bat
echo ============================================

:end
echo.
pause
\r