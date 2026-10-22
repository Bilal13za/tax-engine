@echo off
REM Tax Engine - double-click this file to start the app.
echo [Tax Engine launcher]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
echo.
echo Exit code: %ERRORLEVEL%
echo If the app did not start, open launch.log in this folder and send it for help.
pause
