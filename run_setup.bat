@echo off
chcp 65001 >nul
title ENT BOT - Setup
cd /d "%~dp0"
echo ============================================
echo   ENT BOT Setup
echo ============================================
echo.
echo  Start game first!
echo  Z=Patrol Zone  X=NPC Template  S=Save  Q=Quit
echo.
python ent_setup.py
pause
