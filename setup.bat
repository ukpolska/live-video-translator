@echo off
setlocal
title Live Video Translator - setup
cd /d "%~dp0server"

echo.
echo  Live Video Translator - setup
echo  -----------------------------
echo  This installs what the translator needs and downloads the speech and
echo  translation models (about 1.1 GB). It can take 10-30 minutes, and it is
echo  safe to run again if anything goes wrong.
echo.

rem --- find Python (3.12 is the version this was tested with) ---
set "PY="
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo  Python was not found on this computer.
  echo.
  echo  Please install Python 3.12 from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" on the first screen of the installer.
  echo  Then double-click setup.bat again.
  echo.
  pause
  exit /b 1
)
echo  Using Python:
%PY% --version
%PY% -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)"
if errorlevel 1 (
  echo.
  echo  This version of Python is not supported yet. Please install Python 3.12
  echo  from https://www.python.org/downloads/ and run this setup again.
  echo.
  pause
  exit /b 1
)

if not exist venv\Scripts\python.exe (
  echo.
  echo  Creating a private Python environment for the translator...
  %PY% -m venv venv || goto :failed
)
call venv\Scripts\activate.bat

echo.
echo  Installing the Python libraries...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt || goto :failed

echo.
echo  Downloading the models...
python setup_models.py %* || goto :failed

echo.
echo  Connecting the translator to Chrome...
python register_native_host.py || goto :failed

echo.
echo  ==================================================================
echo   Setup finished.
echo   Next: add the extension to Chrome (see README.md, step 3),
echo   then double-click start_server.bat whenever you want captions.
echo  ==================================================================
echo.
pause
exit /b 0

:failed
echo.
echo  Setup did not finish. Please read the messages above. Most problems are
echo  a lost internet connection or too little disk space: fix that and run
echo  setup.bat again; anything already downloaded is kept.
echo.
pause
exit /b 1
