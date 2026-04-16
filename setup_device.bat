@echo off
setlocal EnableDelayedExpansion
title Device Setup
cd /d "%~dp0"

echo.
echo ============================================
echo   Keyboard / Mouse Device Setup
echo ============================================
echo.
echo   Press any KEY on your physical keyboard
echo   and MOVE your physical mouse.
echo.

py -3.11 -c "from interception import auto_capture_devices, _g_context; auto_capture_devices(keyboard=True, mouse=True, verbose=True); kb=_g_context.keyboard; ms=_g_context.mouse; print(); print(f'  Keyboard = {kb}'); print(f'  Mouse    = {ms}'); import json,os; p=os.path.join(os.path.dirname(os.path.abspath('.')), 'ent_config.json'); cfg=json.load(open(p)) if os.path.exists(p) else {}; cfg['keyboard_device']=kb; cfg['mouse_device']=ms; json.dump(cfg,open(p,'w'),indent=2); print(); print(f'  Saved to ent_config.json')"

echo.
echo ============================================
echo   Done! Devices saved to ent_config.json
echo ============================================
echo.
pause
