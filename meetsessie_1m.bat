@echo off
setlocal
REM ============================================================
REM  Meetsessie op 1,0 meter (externe locatie)
REM  Draaien op de werklaptop, met de UTP-kabel in de switch.
REM
REM  Aanroep:
REM    meetsessie_1m.bat            -> T2.1  (vrouwelijke stem, Fenna)
REM    meetsessie_1m.bat T2.1M      -> T2.1M (mannelijke stem, Maarten)
REM
REM  Stappen:
REM   1. lokale kopie verversen vanaf de G-schijf
REM   2. niveaucheck met uiting N01 op beide devices,
REM      met herkansing na volume-aanpassing
REM   3. volledige reeks op device A en B
REM
REM  IP-adressen zijn de ICS-leases van 2026-10-12; veranderen ze,
REM  draai dan vind_pis.ps1 op WinDevelop.
REM ============================================================

set TESTID=%~1
if "%TESTID%"=="" set TESTID=T2.1

set SRC=%~dp0
set SRC=%SRC:~0,-1%
set LOKAAL=%USERPROFILE%\Werk\scripts
set RASP1=wimboeve@192.168.137.239
set RASP2=wimboeve@192.168.137.213
set PS=powershell -NoProfile -ExecutionPolicy Bypass -File

echo.
echo === Lokale kopie verversen vanaf de G-schijf ===
robocopy "%SRC%" "%LOKAAL%" /E /XD .git /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo FOUT: kopieren vanaf de G-schijf mislukt. Is de Drive bereikbaar?
    pause
    exit /b 1
)
if not exist "%LOKAAL%\corpus\tts_bronnen\%TESTID%\N01.mp3" (
    echo FOUT: geen mp3-bestanden voor %TESTID% gevonden.
    echo Wacht tot de Drive-synchronisatie klaar is en probeer opnieuw.
    pause
    exit /b 1
)
echo   OK.

echo.
echo ==========================================================
echo  MEETSESSIE %TESTID% - baseline op 1,0 meter
echo ==========================================================
echo  Controleer de opstelling:
echo   - beide Pi's naast elkaar, microfoons op gelijke hoogte
echo   - laptop-speakers op 1,0 meter van de microfoons
echo   - ruimte zo stil mogelijk
echo   - UTP-kabel zit in de laptop
echo   - volume op de genoteerde vaste stand
echo.
pause

scp -q "%SRC%\niveaucheck.py" %RASP1%:MIT2026/niveaucheck.py
if errorlevel 1 goto scpfout
scp -q "%SRC%\niveaucheck.py" %RASP2%:MIT2026/niveaucheck.py
if errorlevel 1 goto scpfout

:niveau
echo.
echo === NIVEAUCHECK: N01 opnemen op beide devices ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId %TESTID% -Device %RASP1% -Alleen N01 -Overschrijf -GeenBevestiging
if errorlevel 1 goto opnamefout
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId %TESTID% -Device %RASP2% -Alleen N01 -Overschrijf -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo === GEMETEN NIVEAUS ===
echo device A:
ssh %RASP1% "cd ~/MIT2026 && python3 niveaucheck.py corpus/opnames/%TESTID%/N01.wav"
echo device B:
ssh %RASP2% "cd ~/MIT2026 && python3 niveaucheck.py corpus/opnames/%TESTID%/N01.wav"
echo.
echo Beide regels moeten GOED tonen; mik op een piek rond -8 tot -6 dBFS.
echo Noteer de volumestand zodra hij goed zit en houd hem de hele dag gelijk.
echo.
choice /c GVS /m "G=goed doorgaan, V=volume aangepast dus opnieuw checken, S=stoppen"
if errorlevel 3 exit /b 1
if errorlevel 2 goto niveau

echo.
echo Herhaalronde: J overschrijft ALLE bestaande opnames van %TESTID%.
echo Eerste ronde of aanvullen: N neemt alleen ontbrekende uitingen op.
choice /c JN /m "Bestaande opnames overschrijven"
if errorlevel 2 (set OVR=) else (set OVR=-Overschrijf)

echo.
echo === VOLLEDIGE %TESTID%-REEKS: device A ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId %TESTID% -Device %RASP1% %OVR% -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo === VOLLEDIGE %TESTID%-REEKS: device B ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId %TESTID% -Device %RASP2% %OVR% -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo ==========================================================
echo  KLAAR met de %TESTID%-opnames op 1,0 meter.
echo  Laat de opstelling staan en meld aan Claude op WinDevelop:
echo  "%TESTID% opnames klaar" - hij controleert de opnames.
echo ==========================================================
pause
exit /b 0

:scpfout
echo FOUT: kon niveaucheck.py niet naar de Pi kopieren. Zit de netwerkkabel erin?
pause
exit /b 1

:opnamefout
echo FOUT: de opnamesessie gaf een fout. Zie de uitvoer hierboven.
pause
exit /b 1
