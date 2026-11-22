@echo off
REM Stops RepoXray (your analyses are kept).
cd /d "%~dp0"
docker compose stop
echo RepoXray stopped.
timeout /t 3 >nul
