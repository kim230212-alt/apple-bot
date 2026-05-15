@echo off

net session >nul 2>&1
if %errorlevel% == 0 goto :run

echo Admin privileges required. Click [Yes] on the UAC prompt.
set vbs=%TEMP%\elev%RANDOM%.vbs
echo Set UAC = CreateObject("Shell.Application") > %vbs%
echo UAC.ShellExecute "%~f0", "", "%~dp0", "runas", 1 >> %vbs%
wscript %vbs%
del %vbs% 2>nul
exit /b

:run
chcp 65001 >nul
title ENT BOT DUAL
cd /d "%~dp0"

where py >nul 2>&1 && py ent_bot_gui_dual.py && goto :end
where python >nul 2>&1 && python ent_bot_gui_dual.py && goto :end
echo Python not found.

:end
pause
