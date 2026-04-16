@echo off
chcp 65001 >nul
title ENT BOT (Template)
cd /d "%~dp0"
python ent_bot_gui_template.py
pause
