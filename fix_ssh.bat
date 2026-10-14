@echo off
REM Starter om sleutel-authenticatie voor inkomende SSH te herstellen. Dubbelklikken is genoeg.
REM
REM Belangrijk: het account wordt vastgesteld VOOR de verhoging en als argument doorgegeven.
REM Na een UAC-verhoging is %USERNAME% het account dat de prompt goedkeurde, en dat hoeft niet
REM het account te zijn waarmee straks wordt ingelogd. Juist die verwisseling zorgde ervoor dat
REM de sleutel op de verkeerde plek belandde.
setlocal

set ACCOUNT=%1
if "%ACCOUNT%"=="" set ACCOUNT=%USERNAME%

net session >nul 2>&1
if errorlevel 1 goto verhogen
goto draaien

:verhogen
echo Account: %ACCOUNT%
echo Administratorrechten nodig. Er volgt een UAC-venster -- kies Ja.
echo.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%ACCOUNT%' -Verb RunAs"
exit /b 0

:draaien
set PSSCRIPT=%~dp0fix_ssh_sleutel.ps1
if not exist "%PSSCRIPT%" goto geenscript

echo === Sleutel herstellen voor account %ACCOUNT% ===
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PSSCRIPT%" -Account %ACCOUNT%
if errorlevel 1 goto fout
goto einde

:geenscript
echo FOUT: fix_ssh_sleutel.ps1 niet gevonden naast dit bestand.
echo Verwacht op: %PSSCRIPT%
goto einde

:fout
echo.
echo Het herstel is met een fout gestopt. Lees de melding hierboven.

:einde
echo.
pause
endlocal
