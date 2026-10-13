@echo off
setlocal
REM ============================================================
REM  Meetsessie T2.2 + T2.2M - afstandsblokken 1,5 / 2,5 / 4,0 m
REM  Draaien op de werklaptop, met de UTP-kabel in de switch.
REM
REM  Per afstandsblok worden BEIDE stemmen opgenomen:
REM    T2.2  (vrouwelijk, Fenna)  - device A, dan device B
REM    T2.2M (mannelijk, Maarten) - device A, dan device B
REM  Daarna verzet je de laptop en kies je het volgende blok.
REM
REM  Volume NIET aanpassen: vaste stand 70 van de 1,0 m-sessie.
REM  Bestaande opnames worden standaard overgeslagen, dus een
REM  blok opnieuw starten na een fout is veilig.
REM ============================================================

set SRC=%~dp0
set SRC=%SRC:~0,-1%
set LOKAAL=%USERPROFILE%\Werk\scripts
set RASP1=wimboeve@192.168.137.239
set RASP2=wimboeve@192.168.137.213
set PS=powershell -NoProfile -ExecutionPolicy Bypass -File

echo.
echo === Controle: is het corpus compleet op de G-schijf? ===
powershell -NoProfile -Command "(Get-ChildItem '%SRC%\corpus\tts_bronnen\T2.2\*.mp3' -ErrorAction SilentlyContinue).Count" > "%TEMP%\wp3_n1.txt"
set /p N1=<"%TEMP%\wp3_n1.txt"
powershell -NoProfile -Command "(Get-ChildItem '%SRC%\corpus\tts_bronnen\T2.2M\*.mp3' -ErrorAction SilentlyContinue).Count" > "%TEMP%\wp3_n2.txt"
set /p N2=<"%TEMP%\wp3_n2.txt"
echo   T2.2 : %N1% van 60 mp3's
echo   T2.2M: %N2% van 60 mp3's
if not "%N1%"=="60" goto syncfout
if not "%N2%"=="60" goto syncfout
if not exist "%SRC%\corpus\bron_T2.2M.csv" goto syncfout
if not exist "%SRC%\corpus\T2.2M_manifest.csv" goto syncfout
echo   OK.

echo.
echo === Lokale kopie verversen vanaf de G-schijf ===
robocopy "%SRC%" "%LOKAAL%" /E /XD .git /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo FOUT: kopieren vanaf de G-schijf mislukt.
    pause
    exit /b 1
)
echo   OK.

echo.
echo Normaal gesproken: N. Bestaande opnames blijven dan staan en
echo alleen ontbrekende worden opgenomen. Kies J alleen voor een
echo bewuste herhaalronde van al opgenomen blokken.
choice /c JN /m "Bestaande opnames overschrijven"
if errorlevel 2 (set OVR=) else (set OVR=-Overschrijf)

:menu
echo.
echo ==========================================================
echo  Kies het afstandsblok - beide stemmen, beide devices
echo ==========================================================
echo   1 = 1,5 meter
echo   2 = 2,5 meter
echo   3 = 4,0 meter
echo   S = stoppen
choice /c 123S /m "Keuze"
if errorlevel 4 exit /b 0
if errorlevel 3 set AFST=4.0
if errorlevel 3 goto blok
if errorlevel 2 set AFST=2.5
if errorlevel 2 goto blok
set AFST=1.5

:blok
echo.
echo ----------------------------------------------------------
echo  Blok %AFST% meter.
echo  Zet de laptop-speakers op %AFST% meter van de microfoons.
echo  Volume op stand 70 laten staan.
echo ----------------------------------------------------------
pause

echo.
echo === T2.2 vrouwelijk, blok %AFST% m: device A ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId T2.2 -Device %RASP1% -Afstand %AFST% %OVR% -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo === T2.2 vrouwelijk, blok %AFST% m: device B ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId T2.2 -Device %RASP2% -Afstand %AFST% %OVR% -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo === T2.2M mannelijk, blok %AFST% m: device A ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId T2.2M -Device %RASP1% -Afstand %AFST% %OVR% -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo === T2.2M mannelijk, blok %AFST% m: device B ===
%PS% "%LOKAAL%\opnamesessie.ps1" -TestId T2.2M -Device %RASP2% -Afstand %AFST% %OVR% -GeenBevestiging
if errorlevel 1 goto opnamefout

echo.
echo Blok %AFST% m klaar - beide stemmen, beide devices.
echo Meld het blok aan Claude voor de niveaucheck en verzet daarna
echo de laptop voor het volgende blok.
goto menu

:syncfout
echo.
echo FOUT: het corpus op de G-schijf is nog niet compleet.
echo De Drive-synchronisatie loopt waarschijnlijk nog - kijk naar
echo het Drive-icoon in de taakbalk, wacht even en start opnieuw.
pause
exit /b 1

:opnamefout
echo FOUT: de opnamesessie gaf een fout. Zie de uitvoer hierboven.
echo Het is veilig om dit blok opnieuw te kiezen: bestaande opnames
echo worden overgeslagen, alleen ontbrekende worden opgenomen.
pause
exit /b 1
