@echo off
rem Wrapper zodat loods.ps1 werkt zonder de PowerShell execution policy aan te passen.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0loods.ps1" %*
exit /b %ERRORLEVEL%
