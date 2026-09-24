# Opnamesessie testcorpus WP3 - project Loods (MIT Haalbaarheid 2026)
#
# Werkt de T2.x-opnamereeks af: speelt elke TTS-bronstimulus af via de luidspreker van deze pc
# en laat de Raspberry Pi die tegelijk opnemen met de ReSpeaker. De opname landt op het pad dat
# het manifest verwacht (corpus/opnames/<test_id>/<uiting_id>.wav).
#
# Waarom zo: zie de docstring van corpus/generate_tts_corpus.py. De mp3 is de bronstimulus, niet
# de testaudio. Door hem via een luidspreker af te spelen en met de echte microfoon op te nemen,
# meet de test de microfoon, de akoestiek van de ruimte en de afstand mee - in plaats van een
# kunstmatig schoon TTS-signaal rechtstreeks in de spraakherkenning te stoppen.
#
# De opname draait via mic_capture.py op de Pi (niet via arecord): dat gebruikt sounddevice met
# 1 kanaal en pakt daarmee kanaal 0 van de ReSpeaker - het beamformde, ruisonderdrukte kanaal.
# arecord met plughw zou alle zes kanalen middelen, inclusief de ruwe microfoons.
#
# Gebruik:
#   .\opnamesessie.ps1 -TestId T2.1 -Device rasp1-ip
#   .\opnamesessie.ps1 -TestId T2.2 -Device rasp2-ip -Afstand 1.5
#   .\opnamesessie.ps1 -TestId T2.1 -Device rasp1-ip -Alleen N01,N02 -Overschrijf
#
# Let op: zet de luidspreker op de afstand die bij het blok hoort en houd volume en opstelling
# gelijk voor device A en B. Anders meet de A/B-vergelijking het verschil tussen twee
# geluidsopstellingen in plaats van tussen twee devices.

param(
    [Parameter(Mandatory = $true)][ValidateSet("T2.1", "T2.2")][string]$TestId,
    [Parameter(Mandatory = $true)][string]$Device,
    [double]$Afstand = 0,
    [string[]]$Alleen = @(),
    [switch]$Overschrijf,
    [double]$AanloopS = 0.8,
    [double]$UitloopS = 0.7,
    [switch]$Proefrun,
    [switch]$GeenBevestiging,
    # Schrijft naar opnames/<test_id><DoelSuffix>/ in plaats van naar de officiele map. Gebruik dit
    # voor verkennende opnames op een afstand die niet in het testplan staat, zodat die niet in de
    # meetdataset terechtkomen. Bijvoorbeeld: -DoelSuffix _30cm
    [string]$DoelSuffix = ""
)

$ErrorActionPreference = "Stop"

$CorpusMap = Join-Path $PSScriptRoot "corpus"
$BronCsv = Join-Path $CorpusMap "bron_$TestId.csv"
$ManifestCsv = Join-Path $CorpusMap "${TestId}_manifest.csv"
$Mp3Map = Join-Path $CorpusMap "tts_bronnen\$TestId"

function Meld($tekst) { Write-Host $tekst }
function MeldFout($tekst) { Write-Host $tekst -ForegroundColor Red }
function MeldGoed($tekst) { Write-Host $tekst -ForegroundColor Green }

# --- Controles vooraf -------------------------------------------------------

foreach ($pad in @($BronCsv, $ManifestCsv, $Mp3Map)) {
    if (-not (Test-Path $pad)) { MeldFout "Niet gevonden: $pad"; exit 1 }
}

$bron = Import-Csv $BronCsv
$manifest = Import-Csv $ManifestCsv

# -Alleen komt via "powershell -File" binnen als een enkele string met komma's in plaats van als
# lijst. Splits daarom altijd alsnog op komma's, zodat beide aanroepvormen werken.
if ($Alleen.Count -gt 0) {
    $Alleen = $Alleen -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

# Koppel manifest en bron op uiting_id: het manifest geeft het doelpad en de referentietekst,
# de bron-csv geeft de afstand waarop de uiting moet worden afgespeeld.
$afstandPerId = @{}
foreach ($r in $bron) { $afstandPerId[$r.uiting_id] = [double]$r.afstand_m }

$werklijst = @()
foreach ($m in $manifest) {
    $id = $m.uiting_id
    $a = $afstandPerId[$id]
    if ($Afstand -gt 0 -and $a -ne $Afstand) { continue }
    if ($Alleen.Count -gt 0 -and $Alleen -notcontains $id) { continue }
    # Het manifest wijst naar opnames/<test_id>/<id>.wav. Met een suffix schrijven we naar een
    # aparte map, zodat verkennende opnames de meetdataset niet vervuilen.
    $doel = if ($DoelSuffix) { "opnames/$TestId$DoelSuffix/$id.wav" } else { $m.wav_path }
    $werklijst += [pscustomobject]@{
        Id        = $id
        Mp3       = Join-Path $Mp3Map "$id.mp3"
        DoelPad   = $doel
        Tekst     = $m.referentietekst
        Categorie = $m.categorie
        AfstandM  = $a
    }
}

if ($werklijst.Count -eq 0) { MeldFout "Geen uitingen die voldoen aan de selectie."; exit 1 }

$afstanden = ($werklijst | Select-Object -ExpandProperty AfstandM -Unique | Sort-Object)

Meld ""
Meld "=============================================================="
Meld " OPNAMESESSIE $TestId  ->  $Device"
Meld "=============================================================="
Meld "  uitingen        : $($werklijst.Count)"
Meld "  afstand(en)     : $($afstanden -join ', ') meter"
Meld "  aanloop/uitloop : $AanloopS s / $UitloopS s"
Meld ""

if ($afstanden.Count -gt 1) {
    Meld "  LET OP: deze selectie bevat meerdere afstanden. Draai per afstand een"
    Meld "          aparte reeks met -Afstand, zodat je de luidspreker tussendoor"
    Meld "          kunt verzetten. Bijvoorbeeld: -Afstand $($afstanden[0])"
    Meld ""
}
else {
    Meld "  Zet de luidspreker op $($afstanden[0]) meter van de ReSpeaker."
    Meld ""
}

# --- Verbinding en doelmap --------------------------------------------------

Meld "Verbinding met $Device controleren..."
$hostnaam = ssh -4 -o BatchMode=yes -o ConnectTimeout=10 $Device "hostname" 2>&1
if ($LASTEXITCODE -ne 0) { MeldFout "Geen verbinding met $Device : $hostnaam"; exit 1 }
Meld "  verbonden met: $hostnaam"

$doelMap = "~/MIT2026/corpus/opnames/$TestId$DoelSuffix"
ssh -4 -o BatchMode=yes $Device "mkdir -p $doelMap" 2>&1 | Out-Null
Meld "  doelmap op de Pi: $doelMap"
if ($DoelSuffix) {
    Meld "  LET OP: verkennende opnames - deze map staat BUITEN de meetdataset."
    Meld "          De spraakherkenning leest corpus/opnames/$TestId/, niet deze map."
}
Meld ""

if ($Proefrun) {
    Meld "PROEFRUN - er wordt niets opgenomen. Overzicht van wat er zou gebeuren:"
    foreach ($w in $werklijst) {
        Meld ("  {0,-6} {1,4:N1}m  {2,-13} {3}" -f $w.Id, $w.AfstandM, $w.Categorie, $w.Tekst)
    }
    exit 0
}

if (-not $GeenBevestiging) {
    Read-Host "Druk op Enter om te beginnen (Ctrl+C om te stoppen)" | Out-Null
}
Meld ""

# --- Afspeler ---------------------------------------------------------------

Add-Type -AssemblyName presentationCore
$speler = New-Object System.Windows.Media.MediaPlayer

function DuurVanMp3($pad) {
    # MediaPlayer laadt asynchroon; wacht tot de duur bekend is.
    $speler.Open([uri]$pad)
    $wachtte = 0
    while (-not $speler.NaturalDuration.HasTimeSpan -and $wachtte -lt 3000) {
        Start-Sleep -Milliseconds 50
        $wachtte += 50
    }
    if ($speler.NaturalDuration.HasTimeSpan) { return $speler.NaturalDuration.TimeSpan.TotalSeconds }
    return 6.0  # terugval als de duur niet uitgelezen kan worden
}

# --- Hoofdlus ---------------------------------------------------------------

$gelukt = 0
$overgeslagen = 0
$mislukt = @()
$start = Get-Date

for ($i = 0; $i -lt $werklijst.Count; $i++) {
    $w = $werklijst[$i]
    $nr = "[{0}/{1}]" -f ($i + 1), $werklijst.Count

    if (-not (Test-Path $w.Mp3)) {
        MeldFout "$nr $($w.Id) - mp3 ontbreekt: $($w.Mp3)"
        $mislukt += $w.Id
        continue
    }

    # Bestaat de opname al?
    $bestaat = ssh -4 -o BatchMode=yes $Device "test -s ~/MIT2026/corpus/$($w.DoelPad) && echo JA || echo NEE" 2>&1
    if ($bestaat -match "JA" -and -not $Overschrijf) {
        Meld "$nr $($w.Id) - bestaat al, overgeslagen (gebruik -Overschrijf om opnieuw op te nemen)"
        $overgeslagen++
        continue
    }

    $duur = DuurVanMp3 $w.Mp3
    $opnameDuur = [math]::Round($AanloopS + $duur + $UitloopS, 2)

    Meld ("$nr {0,-6} {1,4:N1}m  {2,-13} `"{3}`"" -f $w.Id, $w.AfstandM, $w.Categorie, $w.Tekst)

    # Opname starten op de Pi (achtergrond), zodat we hier kunnen afspelen terwijl hij loopt.
    $opnameJob = Start-Job -ScriptBlock {
        param($dev, $pad, $duur)
        ssh -4 -o BatchMode=yes $dev "cd ~/MIT2026 && python3 mic_capture.py --out corpus/$pad --duur $duur" 2>&1
    } -ArgumentList $Device, $w.DoelPad, $opnameDuur

    Start-Sleep -Milliseconds ([int]($AanloopS * 1000))

    $speler.Volume = 1.0
    $speler.Position = [TimeSpan]::Zero
    $speler.Play()
    Start-Sleep -Milliseconds ([int]($duur * 1000))
    $speler.Stop()

    $null = Wait-Job $opnameJob -Timeout ([int]($opnameDuur + 20))
    $uitvoer = Receive-Job $opnameJob 2>&1 | Out-String
    Remove-Job $opnameJob -Force -ErrorAction SilentlyContinue

    # Controleer dat er daadwerkelijk een gevuld bestand staat.
    $controle = ssh -4 -o BatchMode=yes $Device "stat -c %s ~/MIT2026/corpus/$($w.DoelPad) 2>/dev/null || echo 0" 2>&1
    $bytes = 0
    [int]::TryParse(($controle | Select-Object -First 1), [ref]$bytes) | Out-Null

    if ($bytes -gt 1000) {
        MeldGoed ("        opgenomen: {0:N1} s, {1:N0} bytes" -f $opnameDuur, $bytes)
        $gelukt++
    }
    else {
        MeldFout "        MISLUKT - geen of leeg bestand. Uitvoer van de Pi:"
        MeldFout ("        " + ($uitvoer.Trim() -replace "`r?`n", "`n        "))
        $mislukt += $w.Id
    }

    Start-Sleep -Milliseconds 300
}

$speler.Close()
$duurTotaal = (Get-Date) - $start

# --- Samenvatting -----------------------------------------------------------

Meld ""
Meld "=============================================================="
Meld " KLAAR - $TestId op $hostnaam"
Meld "=============================================================="
Meld "  opgenomen    : $gelukt"
Meld "  overgeslagen : $overgeslagen"
Meld "  mislukt      : $($mislukt.Count)"
if ($mislukt.Count -gt 0) { MeldFout "    $($mislukt -join ', ')" }
Meld ("  duur         : {0:mm}m {0:ss}s" -f $duurTotaal)
Meld ""
Meld "Opnames staan op de Pi in: ~/MIT2026/corpus/opnames/$TestId$DoelSuffix/"
if ($DoelSuffix) {
    Meld "Dit waren VERKENNENDE opnames - ze staan buiten de meetdataset en worden niet"
    Meld "meegenomen door de spraakherkenning."
}
else {
    Meld "Volgende stap: de spraakherkenning draaien, bijvoorbeeld"
    Meld "  ssh $Device `"cd ~/MIT2026 && python3 speech/whisper_runner.py --manifest corpus/${TestId}_manifest.csv --test-id $TestId --model small`""
}
Meld ""
