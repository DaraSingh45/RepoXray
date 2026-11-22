@echo off
REM ===================================================================
REM  RepoXray - one-click start (Windows + Docker Desktop)
REM  Double-click this file. It starts Docker if needed, builds and runs
REM  RepoXray, then opens http://localhost:3000 in your browser.
REM  Every step is written to repoxray-start.log (send it if something fails).
REM ===================================================================
setlocal EnableExtensions
title RepoXray
cd /d "%~dp0"
set "URL=http://localhost:3000"
set "LOG=%~dp0repoxray-start.log"
echo RepoXray start log > "%LOG%"
echo %DATE% %TIME% >> "%LOG%"

echo.
echo   ===============================
echo     RepoXray - starting up
echo   ===============================
echo.

REM ---- 1. Docker installed? ------------------------------------------
where docker >nul 2>nul
if errorlevel 1 (
  call :say "[X] Docker is not installed. Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
  pause
  exit /b 1
)

REM ---- 2. Docker running? Start Docker Desktop if not ------------------
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready
call :say "[..] Docker Desktop is not running. Starting it..."
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
ping -n 4 127.0.0.1 >nul
docker info >nul 2>nul
if not errorlevel 1 goto docker_ready
set /a tries+=1
if %tries% geq 60 (
  call :say "[X] Docker did not start within 3 minutes. Open Docker Desktop, wait for Engine running, then try again."
  pause
  exit /b 1
)
goto wait_docker
:docker_ready
call :say "[OK] Docker is running."

REM ---- 3. Settings file ------------------------------------------------
if not exist ".env" (
  copy ".env.example" ".env" >nul
  call :say "[OK] Created .env from .env.example"
)

REM ---- 4. Progress page in the browser (information only) ---------------
start "" "%~dp0launcher\starting.html"
call :say "[OK] Opened a progress page. RepoXray itself opens in a new tab when ready."

REM ---- 5. Ollama (optional) --------------------------------------------
set "HAVE_CURL=0"
where curl.exe >nul 2>nul && set "HAVE_CURL=1"
call :probe "http://localhost:11434/api/tags"
if errorlevel 1 (
  call :say "[i] Ollama is not running. Fine if you use Groq, Gemini, OpenAI or no AI."
) else (
  call :say "[OK] Ollama is running."
)

REM ---- 6. Build and start ----------------------------------------------
echo.
call :say "[..] Building and starting RepoXray. The FIRST run takes 5-10 minutes."
echo.
docker compose up -d --build
if errorlevel 1 (
  call :say "[X] Docker could not start RepoXray. Read the messages above. Make sure ports 3000 and 8000 are free."
  pause
  exit /b 1
)
call :say "[OK] Containers started."

REM ---- 7. Wait until the app answers ------------------------------------
call :say "[..] Waiting for RepoXray to answer at %URL% ..."
set /a tries=0
:wait_app
call :probe "%URL%/api/health"
if not errorlevel 1 goto app_ready
set /a tries+=1
if %tries% geq 150 (
  call :say "[X] RepoXray did not answer within 5 minutes. Last log lines:"
  docker compose logs --tail 40 api
  docker compose logs --tail 40 api >> "%LOG%" 2>&1
  call :open
  pause
  exit /b 1
)
ping -n 3 127.0.0.1 >nul
goto wait_app

:app_ready
call :say "[OK] RepoXray is ready."
call :open

:menu
echo.
echo   ==================================================
echo     RepoXray is running at %URL%
echo.
echo     Keep this window open while you use RepoXray.
echo       O = open RepoXray in the browser again
echo       S = stop RepoXray and close this window
echo   ==================================================
choice /c OS /n /m "  Press O or S: "
if errorlevel 2 goto stop
call :open
goto menu

:stop
call :say "[..] Stopping RepoXray..."
docker compose stop
call :say "[OK] Stopped. Your analyses are saved for next time."
ping -n 3 127.0.0.1 >nul
endlocal
exit /b 0

REM ===================================================================
REM  helpers
REM ===================================================================
:say
echo %~1
echo %~1 >> "%LOG%"
exit /b 0

:probe
REM exit code 0 when the address answers with HTTP 2xx
if "%HAVE_CURL%"=="1" (
  curl.exe -s -f -m 3 "%~1" >nul 2>nul
) else (
  powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing '%~1' -TimeoutSec 3; if($r.StatusCode -lt 300){exit 0}else{exit 1}}catch{exit 1}" >nul 2>nul
)
exit /b %errorlevel%

:open
REM open the app in the default browser (fallback if "start" fails)
call :say "[..] Opening %URL% in your browser..."
start "" "%URL%"
if errorlevel 1 rundll32 url.dll,FileProtocolHandler %URL%
exit /b 0
