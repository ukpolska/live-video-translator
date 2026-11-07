@echo off
title Live Video Translator
cd /d "%~dp0server"
if not exist venv\Scripts\python.exe goto :notready
if not exist config.json goto :notready

call venv\Scripts\activate.bat
echo.
echo  Live Video Translator
echo  Leave this window open while you watch. Close it to stop the translator.
echo.
python server.py %*
echo.
echo  The translator has stopped. Press any key to close this window.
pause >nul
exit /b 0

:notready
echo.
echo  The translator is not set up yet. Please double-click setup.bat first.
echo.
pause
exit /b 1
