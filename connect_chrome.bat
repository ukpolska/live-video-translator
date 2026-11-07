@echo off
title Live Video Translator - connect to Chrome
cd /d "%~dp0server"
echo.
echo  Connecting the translator to Chrome (only for your Windows account)...
echo.
if not exist venv\Scripts\python.exe (
  echo  The translator is not set up yet. Please double-click setup.bat first.
  echo.
  pause
  exit /b 1
)
venv\Scripts\python.exe register_native_host.py
echo.
echo  Done. Run this again if you ever move this folder.
echo.
pause
