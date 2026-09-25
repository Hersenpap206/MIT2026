# Setup-script LattePanda 3 Delta (Windows) — Project Loods WP3
# Voer uit in PowerShell als administrator:
#   Right-click PowerShell -> "Als administrator uitvoeren"
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   & "D:\My Drive\Claude\Projects\MIT Haalbaarheid 2026\scripts\setup_windows_lattepanda.ps1"

$ErrorActionPreference = "Stop"

function Stap($tekst) { Write-Host "`n=== $tekst ===" -ForegroundColor Cyan }
function OK($tekst)   { Write-Host "OK: $tekst" -ForegroundColor Green }
function Info($tekst) { Write-Host "   $tekst" -ForegroundColor Gray }

Stap "1. Python 3.12.10 installeren"
$pyExe = "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe"
if (Test-Path $pyExe) {
    OK "Python al aanwezig — sla over"
} else {
    $url  = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $dest = "$env:TEMP\python-3.12.10-amd64.exe"
    Info "Downloaden..."
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Info "Installeren..."
    & $dest /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0
    OK "Python geinstalleerd"
}

# PATH vernieuwen voor deze sessie
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","User") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH","Machine")

Stap "2. Visual C++ Redistributable 2022"
if (Test-Path "C:\Windows\System32\vcruntime140.dll") {
    OK "VC++ Redistributable al aanwezig — sla over"
} else {
    $url  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $dest = "$env:TEMP\vc_redist.x64.exe"
    Info "Downloaden..."
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Info "Installeren..."
    $p = Start-Process -FilePath $dest -ArgumentList "/install /quiet /norestart" -Verb RunAs -Wait -PassThru
    if ($p.ExitCode -eq 0) { OK "VC++ Redistributable geinstalleerd" }
    else { throw "VC++ installatie mislukt (exit $($p.ExitCode))" }
}

Stap "3. ffmpeg installeren"
$ffmpegDir = "C:\Users\$env:USERNAME\AppData\Local\ffmpeg"
$ffmpegBin = (Get-ChildItem "$ffmpegDir\*\bin" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
if ($ffmpegBin -and (Test-Path "$ffmpegBin\ffmpeg.exe")) {
    OK "ffmpeg al aanwezig — sla over"
} else {
    $url  = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $dest = "$env:TEMP\ffmpeg.zip"
    Info "Downloaden..."
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Info "Uitpakken..."
    Expand-Archive -Path $dest -DestinationPath $ffmpegDir -Force
    Remove-Item $dest
    $ffmpegBin = (Get-ChildItem "$ffmpegDir\*\bin" -Directory | Select-Object -First 1).FullName
    $huidigPad = [System.Environment]::GetEnvironmentVariable("PATH","User")
    if ($huidigPad -notlike "*ffmpeg*") {
        [System.Environment]::SetEnvironmentVariable("PATH", "$huidigPad;$ffmpegBin", "User")
    }
    $env:PATH = $env:PATH + ";$ffmpegBin"
    OK "ffmpeg geinstalleerd"
}

Stap "4. Python packages installeren"
$pip = "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe"
$req = "$PSScriptRoot\requirements_windows.txt"
Info "pip install -r requirements_windows.txt (kan 5-10 min duren)..."
& $pip -m pip install -r $req
OK "Packages geinstalleerd"

Stap "5. Mapstructuur aanmaken op D:\Loods WP3"
$dirs = @(
    "D:\Loods WP3\audio\T1.1","D:\Loods WP3\audio\T1.2","D:\Loods WP3\audio\T1.3","D:\Loods WP3\audio\T1.4",
    "D:\Loods WP3\audio\T2.1","D:\Loods WP3\audio\T2.2","D:\Loods WP3\audio\T2.3",
    "D:\Loods WP3\audio\T3.1","D:\Loods WP3\audio\T3.2",
    "D:\Loods WP3\audio\T4.1","D:\Loods WP3\audio\T4.2",
    "D:\Loods WP3\data",
    "D:\Loods WP3\analyse\figuren",
    "D:\Loods WP3\modellen\whisper",
    "D:\Loods WP3\modellen\vosk"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force $d | Out-Null }
OK "Mapstructuur aangemaakt"

Stap "6. Whisper modellen downloaden (tiny + small)"
foreach ($m in @(@{naam="tiny"; mb=72}, @{naam="small"; mb=461})) {
    $whisperModel = "D:\Loods WP3\modellen\whisper\$($m.naam).pt"
    if (Test-Path $whisperModel) {
        OK "Whisper $($m.naam) model al aanwezig — sla over"
    } else {
        Info "Downloaden via Whisper ($($m.mb)MB)..."
        & $pip -c "import whisper; whisper.load_model('$($m.naam)', download_root=r'D:\Loods WP3\modellen\whisper')"
        OK "Whisper $($m.naam) model gedownload"
    }
}

Stap "7. Vosk small-nl model downloaden"
$voskModel = "D:\Loods WP3\modellen\vosk\vosk-model-small-nl-0.22"
if (Test-Path $voskModel) {
    OK "Vosk small-nl model al aanwezig — sla over"
} else {
    $url  = "https://alphacephei.com/vosk/models/vosk-model-small-nl-0.22.zip"
    $dest = "$env:TEMP\vosk-model-small-nl-0.22.zip"
    Info "Downloaden (39MB)..."
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Info "Uitpakken..."
    Expand-Archive -Path $dest -DestinationPath "D:\Loods WP3\modellen\vosk" -Force
    Remove-Item $dest
    OK "Vosk model gedownload"
}

Stap "8. Verificatie"
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","User") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH","Machine")
$check = @'
import sys, shutil
sys.path.insert(0, sys.argv[1])
import adafruit_blinka, hid, sounddevice, soundfile, whisper, vosk
import azure.cognitiveservices.speech, jiwer, edge_tts, paho.mqtt.client, webrtcvad
print("Alle packages OK")
if shutil.which("ffmpeg"): print("ffmpeg OK")
else: print("WAARSCHUWING: ffmpeg niet in PATH -- herstart terminal na setup")
'@
$checkFile = Join-Path $env:TEMP "loods_verify.py"
Set-Content -Path $checkFile -Value $check -Encoding UTF8
& $pip $checkFile $PSScriptRoot

Write-Host "`n" + ("="*50) -ForegroundColor Green
[System.Environment]::SetEnvironmentVariable("LOODS_OPERATOR", "wim", "User")
Write-Host "Setup klaar! Vervolgstappen (cmd of PowerShell, in deze scripts-map):" -ForegroundColor Green
Write-Host '  .\loods.cmd device A      # of B — eenmalig, blijft bewaard' -ForegroundColor Yellow
Write-Host '  .\loods.cmd check         # Drive-offline, packages, mappen, modellen' -ForegroundColor Yellow
Write-Host '  .\loods.cmd diagnose      # sensor-bedradingscheck (MCP2221A aangesloten)' -ForegroundColor Yellow
Write-Host "LOODS_SW_VERSION wordt door loods.cmd automatisch op de git-commit gezet." -ForegroundColor Green
