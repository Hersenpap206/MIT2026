@echo off
REM Pusht deze repo naar GitHub. Werkt ook als git niet in PATH staat: valt terug op de
REM git die met GitHub Desktop is meegeleverd (WinDevelop heeft geen losse Git-installatie).
REM Gebruikt %~dp0 als repo-pad, zodat dit los staat van de driveletter van de Drive-map.
setlocal

set GITEXE=
where git >nul 2>&1
if not errorlevel 1 set GITEXE=git

if "%GITEXE%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if exist "%%D\resources\app\git\cmd\git.exe" set GITEXE=%%D\resources\app\git\cmd\git.exe
    )
)

if "%GITEXE%"=="" (
    echo FOUT: geen git gevonden.
    echo Installeer met: winget install --id Git.Git -e
    exit /b 1
)

echo Git: %GITEXE%
echo.
echo === Nog te pushen ===
"%GITEXE%" -C "%~dp0." log --oneline origin/main..HEAD
echo.
echo === Pushen ===
"%GITEXE%" -C "%~dp0." push origin main
if errorlevel 1 (
    echo.
    echo FOUT: push mislukt.
    echo Staat er internet op? Controleer met: ping github.com
    echo Op WinDevelop staat de ethernetadapter mogelijk nog op het vaste adres van de
    echo internetdeling 192.168.137.1 zonder gateway. Zet IP-toewijzing dan op Automatisch DHCP.
    exit /b 1
)

echo.
echo KLAAR: alles gepusht.
endlocal
