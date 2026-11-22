@echo off
REM ===================================================================
REM  RepoXray - one-click start WITHOUT Docker (needs Python 3.11+ and Git)
REM  First run installs everything (a few minutes). Opens the browser itself.
REM ===================================================================
setlocal EnableExtensions
title RepoXray (local)
cd /d "%~dp0"
set "URL=http://localhost:8000"

REM ---- find Python 3.11+ ------------------------------------------------
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY ( python --version >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [X] Python is not installed. Get Python 3.11+ from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH" during setup.
  pause & exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo [X] Python 3.11 or newer is required. You have:
  %PY% --version
  pause & exit /b 1
)

REM ---- backend environment --------------------------------------------------
cd backend
if not exist ".venv\Scripts\python.exe" (
  echo [..] Creating Python environment...
  %PY% -m venv .venv || (echo [X] Could not create the environment. & pause & exit /b 1)
)
echo [..] Installing / checking Python packages...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 ( echo [X] pip install failed. Check your internet connection. & pause & exit /b 1 )
if not exist ".env" if exist "..\.env" copy "..\.env" ".env" >nul
if not exist ".env" copy "..\.env.example" ".env" >nul

REM ---- interface: use the pre-built one shipped in frontend\dist (no Node needed) ----
if not exist "static\index.html" (
  if exist "..\frontend\dist\index.html" (
    echo [..] Installing the interface...
    xcopy /E /I /Y /Q "..\frontend\dist" "static" >nul
  ) else (
    where npm >nul 2>nul
    if errorlevel 1 (
      echo [X] The interface is missing and Node.js is not installed. Get Node from https://nodejs.org
      pause & exit /b 1
    )
    echo [..] Building the interface ^(first run only^)...
    pushd ..\frontend
    call npm install --no-audit --no-fund || (echo [X] npm install failed. & popd & pause & exit /b 1)
    call npm run build:lowmem || (echo [X] Build failed. & popd & pause & exit /b 1)
    popd
    xcopy /E /I /Y /Q "..\frontend\dist" "static" >nul
  )
)

REM ---- progress page now; the real app opens in a new tab as soon as the server answers ----
start "" "%~dp0launcher\starting.html"
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 180;$i++){try{$r=Invoke-WebRequest -UseBasicParsing '%URL%/api/health' -TimeoutSec 2; if($r.StatusCode -lt 300){Start-Process '%URL%'; break}}catch{Start-Sleep 1}}"

echo.
echo   ==================================================
echo     RepoXray is starting at %URL%
echo     It opens in your browser automatically.
echo     Close this window (or press Ctrl+C) to stop.
echo   ==================================================
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
