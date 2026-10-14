# Herstelt sleutel-authenticatie voor inkomende SSH op Windows, en laat zien wat er mis was.
#
# Windows-sshd kiest het sleutelbestand op basis van het ACCOUNT waarmee wordt ingelogd:
#   - account in de groep Administrators -> C:\ProgramData\ssh\administrators_authorized_keys
#   - gewoon account                     -> C:\Users\<naam>\.ssh\authorized_keys
# setup_lattepanda_ssh.ps1 keek naar het proces in plaats van naar het doelaccount; draait dat
# script verhoogd vanuit een ander beheerdersaccount, dan belandt de sleutel op de verkeerde plek.
# Dit script zet de sleutel voor een opgegeven account op de juiste plaats, met de juiste rechten.
#
# Voer uit in PowerShell ALS ADMINISTRATOR:
#   .\fix_ssh_sleutel.ps1 -Account wimboeve

param(
    [Parameter(Mandatory = $true)][string]$Account
)

$ErrorActionPreference = "Stop"

function Stap($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function OK($t)   { Write-Host "OK: $t" -ForegroundColor Green }
function Info($t) { Write-Host "    $t" -ForegroundColor Gray }
function Waarschuw($t) { Write-Host "LET OP: $t" -ForegroundColor Yellow }

$ident = [Security.Principal.WindowsIdentity]::GetCurrent()
$prins = New-Object Security.Principal.WindowsPrincipal($ident)
if (-not $prins.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Dit script vereist administratorrechten."
}

Stap "1. Is '$Account' lid van de groep Administrators?"
$isAdmin = $false
try {
    $leden = Get-LocalGroupMember -Group "Administrators" -ErrorAction Stop
    foreach ($lid in $leden) {
        $naam = ($lid.Name -split '\\')[-1]
        if ($naam -eq $Account) { $isAdmin = $true }
        Info "lid: $($lid.Name)"
    }
} catch {
    Waarschuw "Groepsleden niet op te vragen: $($_.Exception.Message)"
}

if ($isAdmin) {
    OK "'$Account' IS administrator -> sleutel hoort in administrators_authorized_keys"
    $doel = "$env:ProgramData\ssh\administrators_authorized_keys"
} else {
    OK "'$Account' is GEEN administrator -> sleutel hoort in het profiel van dat account"
    $doel = "C:\Users\$Account\.ssh\authorized_keys"
}

Stap "2. Sleutels verzamelen"
$sleutels = @()
foreach ($naam in @("windevelop_key.pub", "werklaptop_key.pub")) {
    $pad = Join-Path $PSScriptRoot $naam
    if (Test-Path $pad) {
        $sleutels += (Get-Content $pad | Where-Object { $_.Trim() })
        Info "gelezen: $naam"
    }
}
if ($sleutels.Count -eq 0) { throw "Geen .pub-bestanden gevonden naast dit script." }

Stap "3. Sleutels wegschrijven naar $doel"
$map = Split-Path $doel -Parent
if (-not (Test-Path $map)) { New-Item -ItemType Directory -Force $map | Out-Null }
$bestaand = if (Test-Path $doel) { Get-Content $doel } else { @() }
$nieuw = $sleutels | Where-Object { $bestaand -notcontains $_ }
if ($nieuw) {
    ($bestaand + $nieuw) | Set-Content -Path $doel -Encoding utf8
    OK "$($nieuw.Count) sleutel(s) toegevoegd"
} else {
    OK "Sleutels stonden er al"
}

Stap "4. Rechten zetten"
# sshd weigert een sleutelbestand dat door anderen te schrijven is, zonder zichtbare melding.
if ($isAdmin) {
    icacls $doel /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null
    OK "Alleen Administrators en SYSTEM hebben rechten"
} else {
    icacls $doel /inheritance:r /grant "${Account}:F" /grant "SYSTEM:F" /grant "Administrators:F" | Out-Null
    OK "Rechten gezet voor $Account, SYSTEM en Administrators"
}

Stap "5. Beide locaties nalopen"
foreach ($p in @("$env:ProgramData\ssh\administrators_authorized_keys", "C:\Users\$Account\.ssh\authorized_keys")) {
    if (Test-Path $p) {
        $n = @(Get-Content $p | Where-Object { $_.Trim() }).Count
        Info "$p : $n sleutel(s)"
    } else {
        Info "$p : bestaat niet"
    }
}

Stap "6. sshd herstarten"
Restart-Service sshd
OK "sshd herstart"

Stap "7. Laatste weigeringen uit het sshd-logboek"
$log = "$env:ProgramData\ssh\logs\sshd.log"
if (Test-Path $log) {
    $regels = Get-Content $log -Tail 25 | Where-Object { $_ -match "Failed|denied|Authentication refused|bad permissions|Accepted" }
    if ($regels) { $regels | ForEach-Object { Info $_ } } else { Info "geen relevante regels in de laatste 25" }
} else {
    Info "Geen logbestand. Zet logging aan met: 'LogLevel VERBOSE' in $env:ProgramData\ssh\sshd_config"
}

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "Klaar. Laat de andere machine nu opnieuw verbinden." -ForegroundColor Green
