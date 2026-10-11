# Zoek de Raspberry Pi's op een onbekend netwerk — project Loods WP3
#
# Op een andere locatie (ander netwerk, andere router) krijgen de Pi's andere IP-adressen, en
# mDNS (.local) werkt wisselend op Windows. Dit script vindt ze op hun MAC-adres, dat wel
# hetzelfde blijft, en werkt desgewenst ~/.ssh/config bij zodat "ssh rasp1" weer werkt.
#
# Gebruik:
#   .\vind_pis.ps1              # zoeken en rapporteren
#   .\vind_pis.ps1 -Bijwerken   # en ook de ssh-config aanpassen

param([switch]$Bijwerken)

# MAC-adressen van de testdevices (vastgesteld 2026-09-23).
$DEVICES = @{
    "88-A2-9E-A8-0A-7C" = @{naam = "rasp1"; rol = "device A"; poort = "eth0" }
    "88-A2-9E-A8-0A-7D" = @{naam = "rasp1"; rol = "device A"; poort = "wlan0" }
    "88-A2-9E-D0-30-11" = @{naam = "rasp2"; rol = "device B"; poort = "eth0" }
    "88-A2-9E-D0-30-12" = @{naam = "rasp2"; rol = "device B"; poort = "wlan0" }
}

Write-Host ""
Write-Host "=== EIGEN NETWERKADRESSEN ==="
$eigen = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
    Select-Object IPAddress, InterfaceAlias, PrefixLength
foreach ($e in $eigen) {
    Write-Host ("  {0,-16} {1}  /{2}" -f $e.IPAddress, $e.InterfaceAlias, $e.PrefixLength)
}

$subnetten = $eigen | ForEach-Object { ($_.IPAddress -split '\.')[0..2] -join '.' } | Select-Object -Unique
if (-not $subnetten) { Write-Host "  Geen bruikbaar netwerk gevonden."; exit 1 }

Write-Host ""
Write-Host "=== SCANNEN ==="
foreach ($sub in $subnetten) {
    Write-Host "  $sub.0/24 ..." -NoNewline

    # Prikkel de ARP-tabel met een snelle sweep. Fouten negeren: de meeste adressen antwoorden niet.
    $taken = 1..254 | ForEach-Object {
        $ip = "$sub.$_"
        (New-Object System.Net.NetworkInformation.Ping).SendPingAsync($ip, 400)
    }
    [System.Threading.Tasks.Task]::WaitAll($taken) 2>$null
    Write-Host " klaar"
}

Write-Host ""
Write-Host "=== GEVONDEN TESTDEVICES ==="
$gevonden = @{}
$buren = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.LinkLayerAddress -and $_.State -ne 'Unreachable' }

foreach ($b in $buren) {
    $mac = $b.LinkLayerAddress.ToUpper()
    if ($DEVICES.ContainsKey($mac)) {
        $d = $DEVICES[$mac]
        $ssh = Test-NetConnection $b.IPAddress -Port 22 -WarningAction SilentlyContinue -InformationLevel Quiet
        Write-Host ("  {0,-8} {1,-11} {2,-7} {3,-16} ssh={4}" -f $d.naam, $d.rol, $d.poort, $b.IPAddress, $ssh)
        # Bekabeld heeft voorrang boven wifi: stabieler tijdens metingen.
        if ($ssh -and ($d.poort -eq "eth0" -or -not $gevonden.ContainsKey($d.naam))) {
            $gevonden[$d.naam] = $b.IPAddress
        }
    }
}

if ($gevonden.Count -eq 0) {
    Write-Host "  Geen testdevices gevonden."
    Write-Host ""
    Write-Host "  Mogelijke oorzaken:"
    Write-Host "   - de Pi's staan uit of zijn nog aan het opstarten (geef ze een minuut)"
    Write-Host "   - ze hangen aan een ander netwerk dan deze laptop"
    Write-Host "   - de netwerkkabel zit niet goed, of de router gaf geen adres uit"
    Write-Host ""
    Write-Host "  Kom je er zo niet in: sluit een monitor (micro-HDMI) en toetsenbord aan en"
    Write-Host "  kijk met 'hostname -I' welk adres het device heeft."
    exit 1
}

Write-Host ""
Write-Host "=== VERBINDING TESTEN ==="
$sleutel = "$env:USERPROFILE\.ssh\id_ed25519_rasp2"
foreach ($naam in $gevonden.Keys | Sort-Object) {
    $ip = $gevonden[$naam]
    $uit = ssh -4 -i $sleutel -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no "wimboeve@$ip" "hostname; echo ok" 2>&1 | Out-String
    if ($uit -match "ok") {
        Write-Host ("  {0,-8} {1,-16} sleutel werkt" -f $naam, $ip)
    }
    else {
        Write-Host ("  {0,-8} {1,-16} GEEN TOEGANG" -f $naam, $ip) -ForegroundColor Red
        Write-Host "           Let op: deze devices accepteren alleen een SSH-sleutel, geen wachtwoord."
        Write-Host "           Zonder id_ed25519_rasp2 kom je er niet in."
    }
}

if ($Bijwerken) {
    Write-Host ""
    Write-Host "=== SSH-CONFIG BIJWERKEN ==="
    $cfg = "$env:USERPROFILE\.ssh\config"
    $regels = if (Test-Path $cfg) { Get-Content $cfg } else { @() }

    # Verwijder eerdere -loc blokken (van een vorige locatie) en voeg nieuwe toe.
    $nieuw = New-Object System.Collections.Generic.List[string]
    $sla = $false
    foreach ($r in $regels) {
        if ($r -match '^Host\s+rasp\d-loc\s*$') { $sla = $true; continue }
        if ($sla -and $r -match '^\S') { $sla = $false }
        if (-not $sla) { $nieuw.Add($r) }
    }
    $nieuw.Add("")
    $nieuw.Add("# Toegevoegd door vind_pis.ps1 op $(Get-Date -Format 'yyyy-MM-dd HH:mm') — huidige locatie.")
    foreach ($naam in $gevonden.Keys | Sort-Object) {
        $nieuw.Add("Host $naam-loc")
        $nieuw.Add("    HostName $($gevonden[$naam])")
        $nieuw.Add("    User wimboeve")
        $nieuw.Add("    IdentityFile ~/.ssh/id_ed25519_rasp2")
        $nieuw.Add("")
    }
    Set-Content -Path $cfg -Value $nieuw -Encoding utf8
    Write-Host "  bijgewerkt: $cfg"
    Write-Host "  je kunt nu gebruiken: " -NoNewline
    Write-Host (($gevonden.Keys | Sort-Object | ForEach-Object { "ssh $_-loc" }) -join "   ")
}

Write-Host ""
