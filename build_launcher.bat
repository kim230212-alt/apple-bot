@echo off
chcp 65001 > nul
echo ============================================
echo   launcher.exe 빌드 (PyArmor + PyInstaller)
echo ============================================
echo.
python build_launcher.py
pause
