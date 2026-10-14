# Richt een LattePanda in voor bediening op afstand, zoals de Raspberry Pi's.
# Lost openstaand punt 1 uit "SETUP LattePanda sensoren.md" op: Windows heeft geen SSH-server,
# waardoor opnamesessie.ps1 en de meetscripts dit platform niet konden bedienen.
#
# Voer uit in PowerShell ALS ADMINISTRATOR:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   & "G:\My Drive\Claude\MIT Haalbaarheid 2026\scripts\setup_lattepanda_ssh.ps1" -Device A
#
# Na afloop is de machine bereikbaar met: ssh wimboeve@<ip>

param(
    [Parameter(Mandatory = $true)][ValidateSet("A", "B")][string]$Device,
    [string]$OsVersie = "",
    [switch]$GeenSleutels
)

$ErrorActionPreference = "Stop"

function Stap($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function OK($t)   { Write-Host "OK: $t" -ForegroundColor Green }
function Info($t) { Write-Host "    $t" -ForegroundColor Gray }
function Waarschuw($t) { Write-Host "LET OP: $t" -ForegroundColor Yellow }

# --- administrator-controle: zonder verhoogde rechten faalt de helft stilletjes ---
$ident = [Security.Principal.WindowsIdentity]::GetCurrent()
$prins = New-Object Security.Principal.WindowsPrincipal($ident)
if (-not $prins.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Dit script vereist administratorrechten. Start PowerShell met 'Als administrator uitvoeren'."
}

Stap "1. OpenSSH Server installeren"
$cap = Get-WindowsCapability -Online -Name "OpenSSH.Server*" | Select-Object -First 1
if ($cap.State -eq "Installed") {
    OK "OpenSSH Server al aanwezig"
} else {
    Info "Installeren (Windows-functie, geen download van derden)..."
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
    OK "OpenSSH Server geinstalleerd"
}

Stap "2. Service starten en op automatisch zetten"
Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd
OK "sshd draait en start voortaan automatisch"

Stap "3. Firewall"
$regel = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if ($regel) {
    Enable-NetFirewallRule -Name "OpenSSH-Server-In-TCP"
    OK "Firewallregel voor poort 22 staat aan"
} else {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    OK "Firewallregel aangemaakt"
}

Stap "4. PowerShell als shell voor inkomende sessies"
# Standaard is dat cmd.exe. De meetscripts gebruiken PowerShell-constructies, en met cmd als
# shell mislukken die zonder duidelijke fout.
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
    -Value "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -PropertyType String -Force | Out-Null
OK "PowerShell ingesteld als standaardshell"

if (-not $GeenSleutels) {
    Stap "5. Sleutels toestaan (geen wachtwoordgebruik nodig)"
    # Windows gebruikt voor leden van de groep Administrators NIET ~/.ssh/authorized_keys maar
    # een gezamenlijk bestand. Dit is de meest voorkomende oorzaak van "Permission denied
    # (publickey)" op een verder correct ingerichte Windows-sshd.
    # Let op: hier moet gekeken worden naar het account waarmee straks wordt INGELOGD, niet naar
    # het proces. Dit script draait verhoogd, dus het proces heeft altijd het beheerderstoken —
    # ook wanneer het doelaccount zelf geen beheerder is. Op die verwarring strandde de eerste
    # inrichting van device A: de sleutel belandde in administrators_authorized_keys terwijl sshd
    # voor dat account in het gebruikersprofiel keek.
    $doelAccount = $env:USERNAME
    $isAdminAccount = $false
    try {
        foreach ($lid in (Get-LocalGroupMember -Group "Administrators" -ErrorAction Stop)) {
            if ((($lid.Name -split '\\')[-1]) -eq $doelAccount) { $isAdminAccount = $true }
        }
    } catch {
        Waarschuw "Groepsleden niet op te vragen; val terug op het procestoken"
        $adminSid = New-Object Security.Principal.SecurityIdentifier("S-1-5-32-544")
        $isAdminAccount = ([Security.Principal.WindowsIdentity]::GetCurrent()).Groups -contains $adminSid
    }
    Info "doelaccount '$doelAccount' is administrator: $isAdminAccount"

    $sleutels = @()
    foreach ($naam in @("windevelop_key.pub", "werklaptop_key.pub")) {
        $pad = Join-Path $PSScriptRoot $naam
        if (Test-Path $pad) {
            $sleutels += (Get-Content $pad | Where-Object { $_.Trim() })
            Info "sleutel gelezen: $naam"
        } else {
            Waarschuw "$naam niet gevonden naast dit script"
        }
    }

    if ($sleutels.Count -eq 0) {
        Waarschuw "Geen publieke sleutels gevonden. Aanmelden gaat dan met wachtwoord."
    } else {
        if ($isAdminAccount) {
            $doel = "$env:ProgramData\ssh\administrators_authorized_keys"
            Info "Dit account is administrator, dus sleutels gaan naar administrators_authorized_keys"
        } else {
            $doel = "$env:USERPROFILE\.ssh\authorized_keys"
            New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
        }

        $bestaand = if (Test-Path $doel) { Get-Content $doel } else { @() }
        $nieuw = $sleutels | Where-Object { $bestaand -notcontains $_ }
        if ($nieuw) {
            ($bestaand + $nieuw) | Set-Content -Path $doel -Encoding utf8
            OK "$($nieuw.Count) sleutel(s) toegevoegd aan $doel"
        } else {
            OK "Sleutels stonden er al"
        }

        if ($isAdminAccount) {
            # Zonder deze rechten weigert sshd het bestand stilzwijgend.
            icacls $doel /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null
            OK "Rechten op het sleutelbestand gezet (alleen Administrators en SYSTEM)"
        }
    }
}

Stap "6. Omgevingsvariabelen voor de meetscripts"
$osv = if ($OsVersie) { $OsVersie } else { "Windows $([Environment]::OSVersion.Version)" }
$vars = @{
    LOODS_DEVICE     = $Device
    LOODS_HARDWARE   = "LattePanda"
    LOODS_OS         = $osv
    LOODS_OPERATOR   = "wim"
    LOODS_SW_VERSION = "v1.0-dev"
    LOODS_DATA_DIR   = "D:\Loods WP3\data"
    LOODS_AUDIO_DIR  = "D:\Loods WP3\audio"
    LOODS_MODEL_DIR  = "D:\Loods WP3\modellen"
}
foreach ($k in $vars.Keys) {
    # Machine-scope, zodat ze ook gelden in een inkomende ssh-sessie: die leest geen
    # gebruikersprofiel zoals een interactieve aanmelding dat doet.
    [Environment]::SetEnvironmentVariable($k, $vars[$k], "Machine")
    Info "$k = $($vars[$k])"
}
OK "Omgevingsvariabelen gezet (machine-scope)"

Stap "7. Verificatie"
$svc = Get-Service sshd
Info "sshd: $($svc.Status), start=$((Get-Service sshd).StartType)"
$ips = Get-NetIPConfiguration | Where-Object { $_.IPv4Address } |
       ForEach-Object { "$($_.InterfaceAlias): $($_.IPv4Address.IPAddress)" }
Write-Host "`nBereikbaar op:" -ForegroundColor Green
$ips | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "Klaar. Test vanaf de andere machine met:" -ForegroundColor Green
Write-Host "    ssh $env:USERNAME@<ip-hierboven> `"hostname`"" -ForegroundColor Yellow
Write-Host "`nLet op: de omgevingsvariabelen gelden pas na een herstart van sshd" -ForegroundColor Gray
Write-Host "of van de machine. Herstart sshd nu met: Restart-Service sshd" -ForegroundColor Gray
