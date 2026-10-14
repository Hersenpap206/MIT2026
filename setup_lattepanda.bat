@echo off
REM Starter voor de LattePanda-inrichting. Dubbelklikken is genoeg: dit script vraagt zelf om
REM administratorrechten en zoekt zelf het pad naar het PowerShell-script.
REM
REM Waarom een starter: setup_lattepanda_ssh.ps1 vereist verhoogde rechten en het pad naar de
REM Drive-map verschilt per machine (G: op WinMini, D: of een andere letter op de LattePanda's).
REM Met %~dp0 wordt het pad afgeleid van de plek van dit bestand, dus zonder hardcoded drive.
setlocal

set DEVICE=%1

REM --- administratorrechten: net session faalt zonder verhoogde rechten ---
net session >nul 2>&1
if errorlevel 1 goto verhogen
goto draaien

:verhogen
echo Administratorrechten nodig. Er volgt een UAC-venster -- kies Ja.
echo.
if "%DEVICE%"=="" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
) else (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%DEVICE%' -Verb RunAs"
)
exit /b 0

:draaien
if "%DEVICE%"=="" (
    echo.
    echo Welk device is deze machine?
    echo   A = eerste LattePanda
    echo   B = tweede LattePanda
    echo.
    echo LET OP: beide machines op A zetten maakt de replicatietoets zinloos.
    echo.
    choice /c AB /n /m "Kies A of B: "
    if errorlevel 2 set DEVICE=B
    if errorlevel 1 if not errorlevel 2 set DEVICE=A
)

echo.
echo === Inrichten als device %DEVICE% ===
echo.

set PSSCRIPT=%~dp0setup_lattepanda_ssh.ps1
if not exist "%PSSCRIPT%" goto geenscript

powershell -NoProfile -ExecutionPolicy Bypass -File "%PSSCRIPT%" -Device %DEVICE%
if errorlevel 1 goto inrichtingfout
goto codebijwerken

:geenscript
echo FOUT: setup_lattepanda_ssh.ps1 niet gevonden naast dit bestand.
echo Verwacht op: %PSSCRIPT%
goto einde

:inrichtingfout
echo.
echo De inrichting is met een fout gestopt. Lees de melding hierboven.
goto einde

:codebijwerken

echo.
echo === Nu de projectcode bijwerken ===
set REPO=
if exist "D:\Loods WP3\MIT2026\.git" set REPO=D:\Loods WP3\MIT2026
if exist "C:\Loods WP3\MIT2026\.git" set REPO=C:\Loods WP3\MIT2026

if "%REPO%"=="" (
    echo Geen projectcheckout gevonden op D:\Loods WP3\MIT2026 of C:\Loods WP3\MIT2026.
    echo Werk de code daar handmatig bij met: git pull
) else (
    echo Checkout gevonden: %REPO%
    pushd "%REPO%"
    git pull
    if errorlevel 1 echo LET OP: git pull is mislukt -- controleer de internetverbinding.
    popd
)

:einde
echo.
echo Klaar. Geef het IP-adres hierboven door, dan wordt de rest op afstand gedaan.
echo.
pause
endlocal
