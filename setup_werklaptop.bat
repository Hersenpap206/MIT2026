@echo off
setlocal
REM ============================================================
REM  Setup werklaptop voor WP3-opnamesessie (externe locatie)
REM  - controleert het netwerk (ICS-subnet 192.168.137.x)
REM  - maakt een SSH-sleutel aan en zet de publieke helft op G:
REM  - kopieert de scripts-map naar een lokale map (timing!)
REM  - test daarna de verbinding met beide Pi's
REM
REM  LET OP: de IP-adressen hieronder zijn de ICS-leases van
REM  2026-10-12. Na een herstart van WinDevelop of de Pi's kunnen
REM  ze veranderen; draai dan vind_pis.ps1 op WinDevelop.
REM ============================================================

set SRC=%~dp0
set SRC=%SRC:~0,-1%
set LOKAAL=%USERPROFILE%\Werk\scripts
set RASP1=wimboeve@192.168.137.239
set RASP2=wimboeve@192.168.137.213

echo.
echo === STAP 1/5: netwerk controleren ===
ipconfig > "%TEMP%\wp3_ipconfig.txt" 2>&1
findstr /c:"192.168.137." "%TEMP%\wp3_ipconfig.txt" >nul
if errorlevel 1 (
    echo   FOUT: deze laptop heeft geen 192.168.137.x-adres.
    echo   Controleer de netwerkkabel naar de Netgear-switch, wacht
    echo   tien seconden, en start dit script opnieuw.
    pause
    exit /b 1
)
echo   OK: aangesloten op het meetnetwerk.

echo.
echo === STAP 2/5: ssh-client aanwezig? ===
where ssh >nul 2>&1
if errorlevel 1 (
    echo   FOUT: ssh.exe niet gevonden. Zet in Windows-instellingen
    echo   de optionele functie "OpenSSH-client" aan en probeer opnieuw.
    pause
    exit /b 1
)
echo   OK.

echo.
echo === STAP 3/5: SSH-sleutel ===
if not exist "%USERPROFILE%\.ssh" mkdir "%USERPROFILE%\.ssh"
if exist "%USERPROFILE%\.ssh\id_ed25519" (
    echo   Sleutel bestaat al en wordt hergebruikt.
) else (
    ssh-keygen -t ed25519 -N "" -q -f "%USERPROFILE%\.ssh\id_ed25519"
    if errorlevel 1 (
        echo   FOUT: sleutel aanmaken mislukt.
        pause
        exit /b 1
    )
    echo   Nieuwe sleutel aangemaakt.
)
copy /y "%USERPROFILE%\.ssh\id_ed25519.pub" "%SRC%\werklaptop_key.pub" >nul
if errorlevel 1 (
    echo   FOUT: kon de publieke sleutel niet naar de G-schijf kopieren.
    pause
    exit /b 1
)
echo   Publieke sleutel staat klaar op de G-schijf.

echo.
echo === STAP 4/5: scripts lokaal kopieren ===
robocopy "%SRC%" "%LOKAAL%" /E /XD .git /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo   FOUT: kopieren mislukt. Is de G-schijf bereikbaar?
    pause
    exit /b 1
)
echo   Gekopieerd naar: %LOKAAL%

echo.
echo ============================================================
echo  Zeg nu tegen Claude op WinDevelop: "de sleutel staat klaar".
echo  Claude zet hem dan op beide Pi's.
echo  Druk DAARNA op een toets om de verbinding te testen.
echo ============================================================
pause

:test
set MISLUKT=0
echo.
echo === STAP 5/5: verbinding testen ===
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 %RASP1% hostname
if errorlevel 1 (
    echo   FOUT: rasp1 %RASP1% niet bereikbaar of sleutel nog niet actief.
    set MISLUKT=1
) else (
    echo   OK: rasp1.
)
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 %RASP2% hostname
if errorlevel 1 (
    echo   FOUT: rasp2 %RASP2% niet bereikbaar of sleutel nog niet actief.
    set MISLUKT=1
) else (
    echo   OK: rasp2.
)

if "%MISLUKT%"=="1" (
    echo.
    choice /c JN /m "Is de sleutel inmiddels geinstalleerd - opnieuw testen (J/N)"
    if errorlevel 2 exit /b 1
    goto test
)

echo.
echo ============================================================
echo  KLAAR. Start de opnamesessie zo:
echo.
echo    1. Open PowerShell
echo    2. cd %LOKAAL%
echo    3. .\opnamesessie.ps1 -TestId T2.1 -Device %RASP1%
echo       .\opnamesessie.ps1 -TestId T2.1 -Device %RASP2%
echo.
echo  Zet het Windows-volume op een vast niveau en noteer het;
echo  het moet gelijk blijven tussen device A en B en alle afstanden.
echo ============================================================
pause
exit /b 0
