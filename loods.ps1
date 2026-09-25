# Startscript Project Loods WP3 (Windows / LattePanda) - werkt vanuit elke map, ook de Google Drive-map:
#   & "D:\My Drive\Claude\Projects\MIT Haalbaarheid 2026\scripts\loods.ps1" diagnose
# of dubbelklik / typ in cmd:  loods.cmd diagnose
#
# Opdrachten:
#   check                     controleert Drive-offline-status, Python, packages, omgevingsvariabelen
#   device A|B                zet LOODS_DEVICE permanent voor deze Windows-gebruiker
#   diagnose                  stap-voor-stap sensor-bedradingscheck (MCP2221A, DHT20, licht, PIR)
#   sensoren [-n 60 -i 2]     sensormetingen printen
#   update                    code bijwerken via git pull (alleen als git geinstalleerd is)
#   run <script.py> [args]    willekeurig script uit deze map, bv.:
#                             loods.cmd run speech\whisper_runner.py --manifest ... --test-id T2.1
#
# Wat dit script regelt, zodat je niets hoeft te onthouden:
#   - werkmap = de map van dit script (dus relatieve paden als speech\whisper_runner.py kloppen)
#   - PYTHONDONTWRITEBYTECODE=1: geen __pycache__-mappen die Google Drive steeds gaat synchroniseren
#   - PYTHONUTF8=1: Nederlandse tekens en graden-teken correct in console en CSV
#   - BLINKA_MCP2221=1: Adafruit Blinka gebruikt de MCP2221A
#   - LOODS_SW_VERSION = git-commit van deze map (ook zonder geinstalleerde git), voor reproduceerbaarheid
# Meetdata en audio gaan NIET naar de Drive-map maar naar D:\Loods WP3 (zie common\config.py).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function OK($t)    { Write-Host "  [OK]   $t" -ForegroundColor Green }
function Waarsch($t) { Write-Host "  [LET OP] $t" -ForegroundColor Yellow }
function Fout($t)  { Write-Host "  [FOUT] $t" -ForegroundColor Red }

function Zoek-Python {
    $kandidaten = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($k in $kandidaten) { if (Test-Path $k) { return $k } }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py -and $py.Source -notlike "*WindowsApps*") { return $py.Source }
    throw "Python 3.12 niet gevonden - draai eerst setup_windows_lattepanda.ps1"
}

function Git-Commit {
    # Leest de commit direct uit .git, zodat het ook werkt op een machine zonder git.
    $gitDir = Join-Path $root ".git"
    if (-not (Test-Path "$gitDir\HEAD")) { return $null }
    $head = (Get-Content "$gitDir\HEAD" -Raw).Trim()
    if ($head -notlike "ref: *") { return $head.Substring(0, 7) }
    $ref = $head.Substring(5)
    $refFile = Join-Path $gitDir $ref
    if (Test-Path $refFile) { return (Get-Content $refFile -Raw).Trim().Substring(0, 7) }
    $packed = Join-Path $gitDir "packed-refs"
    if (Test-Path $packed) {
        $regel = Get-Content $packed | Where-Object { $_ -like "* $ref" } | Select-Object -First 1
        if ($regel) { return $regel.Substring(0, 7) }
    }
    return $null
}

function Zet-Omgeving {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONUTF8 = "1"
    $env:BLINKA_MCP2221 = "1"
    if (-not $env:LOODS_SW_VERSION -or $env:LOODS_SW_VERSION -eq "v1.0-dev") {
        $commit = Git-Commit
        if ($commit) { $env:LOODS_SW_VERSION = "git-$commit" }
    }
    if (-not $env:LOODS_DEVICE) {
        $env:LOODS_DEVICE = [System.Environment]::GetEnvironmentVariable("LOODS_DEVICE", "User")
    }
}

function Check-DriveOffline {
    # Google Drive (stream-modus) zet bij bestanden die alleen online staan het attribuut
    # RecallOnDataAccess/RecallOnOpen/Offline. Zonder internet (bv. in Zweden) zijn die niet te openen.
    $online = @(Get-ChildItem $root -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notlike "*\.git\*" } |
        Where-Object { ([int]$_.Attributes -band (0x400000 -bor 0x40000 -bor 0x1000)) -ne 0 })
    if ($online.Count -eq 0) {
        OK "alle scripts staan lokaal (werkt ook zonder internet)"
    } else {
        Waarsch "$($online.Count) bestand(en) staan alleen online in Google Drive, bv. $($online[0].Name)"
        Waarsch "Rechtsklik op de map 'scripts' in Verkenner > 'Offline beschikbaar maken' en wacht tot het klaar is"
    }
}

function Toon-Hulp {
    Get-Content $PSCommandPath | Select-Object -First 13 | ForEach-Object { $_ -replace "^# ?", "" }
}

$opdracht = if ($args.Count -gt 0) { $args[0] } else { "help" }
$rest = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

Zet-Omgeving

switch ($opdracht) {
    "check" {
        Write-Host "Scripts-map: $root"
        Check-DriveOffline
        try { $py = Zoek-Python; OK "Python: $py" } catch { Fout $_; exit 1 }
        & $py -c "import adafruit_blinka, hid, sounddevice, soundfile, whisper, vosk, jiwer, paho.mqtt.client, webrtcvad" 2>$null
        if ($LASTEXITCODE -eq 0) { OK "Python-packages aanwezig" } else { Fout "packages ontbreken - draai setup_windows_lattepanda.ps1" }
        if ($env:LOODS_DEVICE -in @("A", "B")) { OK "LOODS_DEVICE = $env:LOODS_DEVICE" }
        else { Fout "LOODS_DEVICE niet gezet - gebruik: loods.cmd device A  (of B)" }
        if ($env:LOODS_SW_VERSION) { OK "LOODS_SW_VERSION = $env:LOODS_SW_VERSION" }
        foreach ($d in @("D:\Loods WP3\data", "D:\Loods WP3\audio", "D:\Loods WP3\modellen\vosk")) {
            if (Test-Path $d) { OK "$d bestaat" } else { Fout "$d ontbreekt - draai setup_windows_lattepanda.ps1" }
        }
        if (Test-Path "D:\Loods WP3\modellen\whisper\small.pt") { OK "Whisper small aanwezig" }
        else { Waarsch "Whisper small ontbreekt - draai thuis (met internet) setup_windows_lattepanda.ps1 opnieuw" }
    }
    "device" {
        if ($rest.Count -ne 1 -or $rest[0] -notin @("A", "B")) { Fout "gebruik: loods.cmd device A  (of B)"; exit 1 }
        [System.Environment]::SetEnvironmentVariable("LOODS_DEVICE", $rest[0], "User")
        OK "LOODS_DEVICE = $($rest[0]) (permanent voor gebruiker $env:USERNAME)"
    }
    "diagnose" { & (Zoek-Python) "windows_lattepanda\sensor_reader.py" --diagnose; exit $LASTEXITCODE }
    "sensoren" { & (Zoek-Python) "windows_lattepanda\sensor_reader.py" @rest; exit $LASTEXITCODE }
    "update" {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Fout "git niet geinstalleerd op deze machine - werk de code bij op de laptop; Google Drive synchroniseert het hierheen"
            exit 1
        }
        git -C $root pull
        exit $LASTEXITCODE
    }
    "run" {
        if ($rest.Count -lt 1) { Fout "gebruik: loods.cmd run <script.py> [argumenten]"; exit 1 }
        if (-not $env:LOODS_DEVICE) { Waarsch "LOODS_DEVICE niet gezet - gebruik eerst: loods.cmd device A" }
        & (Zoek-Python) @rest
        exit $LASTEXITCODE
    }
    default { Toon-Hulp }
}
