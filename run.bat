@echo off
chcp 65001 >nul
title ENT BOT
cd /d "%~dp0"
python ent_bot_gui.py
pause
