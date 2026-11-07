@echo off
title Live Video Translator - uninstall
cd /d "%~dp0server"
echo.
echo  This disconnects the translator from Chrome.
echo.
if exist venv\Scripts\python.exe (
  venv\Scripts\python.exe register_native_host.py --remove
)
echo.
echo  To finish removing it:
echo    1. In Chrome, open chrome://extensions and click Remove on "Live Video Translator".
echo    2. Delete this folder.
echo.
pause
