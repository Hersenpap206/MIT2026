"""Inventariseert wat de ReSpeaker Lite op een Raspberry Pi levert.

Waarom dit script er is. De Lite is een kandidaat voor de appliance: 2-microfoonarray met een
XMOS XU316-DSP en een XIAO ESP32-S3 op hetzelfde bord, voor ongeveer 26 euro. Interessant is
vooral dat de ESP32 erbij zit, want uit de metingen van 12 november volgt een gelaagd ontwerp
waarin de poortwachter continu en goedkoop moet draaien en de transcriptie zelden en duur. Een
poortwachter op de module zelf zou de Pi alleen hoeven wekken.

Wat daarvoor eerst vast moet staan is ongedocumenteerd: hoeveel kanalen levert de USB-firmware
van de Lite, met welke bemonsteringsfrequentie, en hoe gedraagt de ruisvloer zich per kanaal.
De zeskanaalsindeling die overal wordt geciteerd (0 bewerkt, 1-4 ruwe microfoons, 5 playback)
hoort bij de oudere 4-mic array, niet bij de Lite.

LET OP - de juiste USB-poort. Het bord heeft twee USB-C-aansluitingen. Alleen die van de XMOS
geeft audio; de poort van de XIAO ESP32-S3 geeft een serieel debugapparaat. Zit de kabel in de
XIAO-poort, dan meldt de Pi 'Espressif USB JTAG/serial debug unit' en is er geen opnameapparaat.
Verhuis de kabel naar de XMOS-poort. Blijft het apparaat dan nog weg, dan draait er
I2S-firmware op de XU316 en moet de USB-build geflasht worden met dfu-util.

Gebruik (op de Pi):
    py -3.11 linux_rpi5/lite_inventarisatie.py
    py -3.11 linux_rpi5/lite_inventarisatie.py --seconden 600 --doel ~/lite_nacht
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

KANDIDAATNAMEN = ("respeaker", "xmos", "xvf", "seeed")
PROBEER_FREQUENTIES = (16000, 32000, 44100, 48000)


def dbfs(x: np.ndarray) -> float:
    if x.size == 0:
        return -99.0
    rms = float(np.sqrt(np.mean((x.astype(np.float64) / 32768.0) ** 2)))
    return 20.0 * np.log10(max(rms, 1e-9))


def toon_usb() -> str:
    """Toont de USB-apparaten en geeft terug wat er van de Lite te zien is:
    'xmos', 'xiao' of 'niets'. Dat bepaalt welke diagnose klopt als er geen audio is."""
    print("USB-APPARATEN")
    print("=" * 72)
    try:
        uit = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=10).stdout
    except Exception as fout:                                  # noqa: BLE001
        print(f"  lsusb niet beschikbaar ({fout})")
        return "niets"
    gezien = "niets"
    for regel in uit.splitlines():
        merk = ""
        if "303a:" in regel:
            merk = "   <-- XIAO ESP32-S3: VERKEERDE poort voor audio"
            gezien = "xiao" if gezien == "niets" else gezien
        elif "2886:" in regel or any(n in regel.lower() for n in ("xmos", "respeaker")):
            merk = "   <-- de ReSpeaker Lite zelf"
            gezien = "xmos"
        print(f"  {regel}{merk}")
    print()
    return gezien


def toon_dfu_diagnose() -> None:
    """De Lite is zichtbaar maar levert geen audio. Toont welke interfaceklassen hij biedt,
    want dat onderscheidt 'verkeerde firmware' van 'driver niet geladen'."""
    try:
        uit = subprocess.run(["lsusb", "-v", "-d", "2886:0019"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:                                          # noqa: BLE001
        return
    klassen = [r.strip() for r in uit.splitlines() if "bInterfaceClass" in r]
    if not klassen:
        return
    print("  interfaceklassen van het apparaat:")
    for k in sorted(set(klassen)):
        print(f"    {k}")
    if any("254" in k for k in klassen) and not any(" 1 Audio" in k for k in klassen):
        print()
        print("  Alleen klasse 254 (Device Firmware Update), geen audioklasse. De XU316 draait")
        print("  de I2S-firmware, bedoeld voor de XIAO. Voor gebruik als USB-geluidskaart moet")
        print("  de USB-build erop met dfu-util:")
        print("    sudo apt install dfu-util")
        print("    # firmware uit github.com/respeaker/ReSpeaker_Lite")
        print("    sudo dfu-util -R -e -a 1 -D <usb-firmware>.bin")
        print("  Let op: daarmee werkt het bord niet meer met de XIAO tot de I2S-build")
        print("  teruggezet wordt. Relevant als het tweede exemplaar in ZorgScribe zit.")


def zoek_invoerapparaten() -> list[tuple[int, dict]]:
    gevonden = []
    for nummer, apparaat in enumerate(sd.query_devices()):
        if apparaat["max_input_channels"] > 0:
            gevonden.append((nummer, apparaat))
    return gevonden


def toon_apparaten(apparaten: list[tuple[int, dict]], gezien: str) -> int | None:
    print("OPNAMEAPPARATEN VOLGENS SOUNDDEVICE")
    print("=" * 72)
    if not apparaten:
        print("  GEEN. De Pi ziet geen enkele opnamebron.")
        if gezien == "xiao":
            print("  Alleen de XIAO ESP32-S3 is zichtbaar: de kabel zit in de verkeerde poort.")
            print("  Verhuis hem naar de USB-C-poort van de XMOS.")
        elif gezien == "xmos":
            print("  De Lite is wel zichtbaar, maar levert geen audio.")
            toon_dfu_diagnose()
        else:
            print("  Er is helemaal geen ReSpeaker zichtbaar op de USB-bus.")
        print()
        return None
    keuze = None
    for nummer, apparaat in apparaten:
        naam = apparaat["name"].strip()
        is_lite = any(n in naam.lower() for n in KANDIDAATNAMEN)
        if is_lite and keuze is None:
            keuze = nummer
        print(f"  [{nummer}] {naam}")
        print(f"        kanalen: {apparaat['max_input_channels']}, "
              f"standaardfrequentie: {apparaat['default_samplerate']:.0f} Hz"
              + ("   <-- kandidaat" if is_lite else ""))
    print()
    return keuze


def toets_frequenties(apparaat: int, kanalen: int) -> list[int]:
    print("ONDERSTEUNDE BEMONSTERINGSFREQUENTIES")
    print("=" * 72)
    werkend = []
    for frequentie in PROBEER_FREQUENTIES:
        try:
            sd.check_input_settings(device=apparaat, channels=kanalen,
                                    samplerate=frequentie, dtype="int16")
            werkend.append(frequentie)
            print(f"  {frequentie:6d} Hz  ja")
        except Exception:                                      # noqa: BLE001
            print(f"  {frequentie:6d} Hz  nee")
    print()
    return werkend


def meet_kanalen(apparaat: int, kanalen: int, frequentie: int, seconden: float,
                 doel: Path | None) -> None:
    print(f"RUISVLOER PER KANAAL ({seconden:.0f} s op {frequentie} Hz)")
    print("=" * 72)
    opname = sd.rec(int(seconden * frequentie), samplerate=frequentie,
                    channels=kanalen, dtype="int16", device=apparaat)
    sd.wait()

    niveaus = [dbfs(opname[:, k]) for k in range(kanalen)]
    for k, niveau in enumerate(niveaus):
        piek = 20 * np.log10(max(float(np.max(np.abs(opname[:, k]))) / 32768.0, 1e-9))
        print(f"  kanaal {k}:  RMS {niveau:7.2f} dBFS   piek {piek:7.2f} dBFS")

    if kanalen > 1:
        spreiding = max(niveaus) - min(niveaus)
        print()
        print(f"  verschil tussen hoogste en laagste kanaal: {spreiding:.2f} dB")
        if spreiding > 10:
            print("  Een verschil van deze orde wijst op een bewerkt kanaal naast ruwe kanalen,")
            print("  zoals de 21,6 dB die de AGC op de Mic Array v2.0 toevoegt.")
        else:
            print("  Alle kanalen liggen dicht bij elkaar: waarschijnlijk allemaal bewerkt,")
            print("  of allemaal ruw. Zonder ruw kanaal is de AGC-vraag hier niet te toetsen.")

    if doel is not None:
        doel.mkdir(parents=True, exist_ok=True)
        bestand = doel / f"lite_{datetime.now():%Y%m%d_%H%M%S}_{frequentie}Hz_{kanalen}ch.wav"
        sf.write(str(bestand), opname, frequentie, subtype="PCM_16")
        print(f"\n  opname bewaard: {bestand}")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description="Inventarisatie ReSpeaker Lite op de Pi")
    p.add_argument("--seconden", type=float, default=30.0, help="duur van de ruismeting")
    p.add_argument("--doel", type=Path, default=None, help="map om de opname te bewaren")
    p.add_argument("--apparaat", type=int, default=None, help="apparaatnummer forceren")
    args = p.parse_args()

    gezien = toon_usb()
    apparaten = zoek_invoerapparaten()
    gekozen = args.apparaat if args.apparaat is not None else toon_apparaten(apparaten, gezien)
    if gekozen is None:
        if apparaten:
            print("Geen apparaat met een herkenbare naam gevonden; kies er zelf een met "
                  "--apparaat <nummer>.")
        return

    info = sd.query_devices(gekozen)
    kanalen = int(info["max_input_channels"])
    print(f"GEKOZEN: [{gekozen}] {info['name'].strip()} met {kanalen} kanalen\n")

    frequenties = toets_frequenties(gekozen, kanalen)
    if not frequenties:
        print("Geen bruikbare bemonsteringsfrequentie gevonden.")
        return

    frequentie = 16000 if 16000 in frequenties else frequenties[0]
    meet_kanalen(gekozen, kanalen, frequentie, args.seconden, args.doel)

    print("VERVOLG")
    print("=" * 72)
    print("  1. Is er een ruw kanaal naast het bewerkte? Dan is dezelfde AGC-toets mogelijk")
    print("     als op de Mic Array v2.0 (dialogue/kanaalvergelijking.py).")
    print("  2. Zo niet, dan is de Lite geen meetinstrument voor die vraag, maar blijft hij")
    print("     kandidaat voor de architectuur: poortwachter op de ESP32, Pi alleen voor")
    print("     de transcriptie.")


if __name__ == "__main__":
    main()
