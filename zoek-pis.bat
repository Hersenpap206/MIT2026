@echo off
REM Starter voor vind_pis.ps1 - project Loods WP3.
REM Dubbelklikken is genoeg; het pad met spaties en de execution policy zijn hier al geregeld.
REM Alleen ASCII in dit bestand: cmd struikelt over accenten en speciale tekens.

setlocal
set SCRIPT=%~dp0vind_pis.ps1

if not exist "%SCRIPT%" (
    echo FOUT: vind_pis.ps1 niet gevonden naast dit bestand.
    echo Verwacht op: %SCRIPT%
    goto einde
)

echo ==========================================================
echo  Testdevices zoeken op het huidige netwerk
echo ==========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Bijwerken

echo.
echo ==========================================================
if errorlevel 1 (
    echo  Geen devices gevonden - zie de meldingen hierboven.
    echo.
    echo  Staan de Pi's aan en zitten de netwerkkabels erin?
    echo  Geef ze na het aanzetten een minuut om op te starten.
    echo  Lukt het niet: sluit een monitor aan via micro-HDMI.
) else (
    echo  Klaar. Je kunt nu verbinden met:  ssh rasp1-loc   of   ssh rasp2-loc
)
echo ==========================================================

:einde
echo.
pause
endlocal
