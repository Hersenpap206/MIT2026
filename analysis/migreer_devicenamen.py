"""Zet de oude devicenamen A en B om naar de sprekende namen RASP1 en RASP2.

Tot 14 oktober 2026 heetten de twee Raspberry Pi's in de meetdata A en B, terwijl de machines
zelf Rasp1 en Rasp2 heten en de ssh-aliassen dat ook doen. Met drie platforms erbij werd "device
A" dubbelzinnig: A van welk platform? Deze migratie trekt de meetdata gelijk met de hostnamen.

Aangepast worden, uitsluitend voor platform Linux:
  1. mapnamen        data/Linux/A        -> data/Linux/RASP1
  2. bestandsnamen   T1.1_Linux_A_...    -> T1.1_Linux_RASP1_...
  3. de kolom device A                   -> RASP1

Andere platforms en andere kolommen blijven ongemoeid. Vóór elke wijziging wordt een kopie van
de hele boom gemaakt. Draai eerst met --proef om te zien wat er zou gebeuren.

Gebruik:
    python analysis/migreer_devicenamen.py --data-dir "D:\\Loods WP3\\backup_14okt" --proef
    python analysis/migreer_devicenamen.py --data-dir "D:\\Loods WP3\\backup_14okt"
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

OMZETTING = {"A": "RASP1", "B": "RASP2"}
PLATFORM = "Linux"


def vind_csvs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.csv") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Devicenamen A/B omzetten naar RASP1/RASP2")
    parser.add_argument("--data-dir", required=True, help="map met de meetdata-boom")
    parser.add_argument("--proef", action="store_true", help="alleen tonen, niets wijzigen")
    args = parser.parse_args()

    root = Path(args.data_dir)
    if not root.is_dir():
        print(f"niet gevonden: {root}")
        return 1

    print(f"{'PROEF: ' if args.proef else ''}migratie in {root}\n")

    # --- 1. kopie van de hele boom, zodat terugdraaien altijd kan ---
    if not args.proef:
        stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
        kopie = root.parent / f"{root.name}_voor_migratie_{stempel}"
        shutil.copytree(root, kopie)
        print(f"kopie gemaakt: {kopie}\n")

    # --- 2. inhoud van de CSV's: de kolom device ---
    rijen_aangepast = 0
    bestanden_aangepast = 0
    for pad in vind_csvs(root):
        with pad.open(newline="", encoding="utf-8") as fh:
            lezer = csv.DictReader(fh)
            velden = lezer.fieldnames
            rijen = list(lezer)
        if not velden or "device" not in velden or "platform" not in velden:
            continue

        n = 0
        for rij in rijen:
            if rij.get("platform") == PLATFORM and rij.get("device") in OMZETTING:
                rij["device"] = OMZETTING[rij["device"]]
                n += 1
        if n == 0:
            continue

        print(f"  {pad.name}: {n} rijen")
        rijen_aangepast += n
        bestanden_aangepast += 1
        if not args.proef:
            with pad.open("w", newline="", encoding="utf-8") as fh:
                schrijver = csv.DictWriter(fh, fieldnames=velden)
                schrijver.writeheader()
                schrijver.writerows(rijen)

    print(f"\nkolom device: {rijen_aangepast} rijen in {bestanden_aangepast} bestanden\n")

    # --- 3. bestandsnamen ---
    naam_aangepast = 0
    for pad in vind_csvs(root):
        nieuw = pad.name
        for oud, vervang in OMZETTING.items():
            nieuw = nieuw.replace(f"_{PLATFORM}_{oud}_", f"_{PLATFORM}_{vervang}_")
        if nieuw != pad.name:
            print(f"  {pad.name} -> {nieuw}")
            naam_aangepast += 1
            if not args.proef:
                pad.rename(pad.with_name(nieuw))
    print(f"\nbestandsnamen: {naam_aangepast}\n")

    # --- 4. mapnamen, van diep naar ondiep zodat paden geldig blijven ---
    map_aangepast = 0
    mappen = sorted((p for p in root.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True)
    for map_pad in mappen:
        if map_pad.name in OMZETTING and map_pad.parent.name == PLATFORM:
            doel = map_pad.with_name(OMZETTING[map_pad.name])
            print(f"  {map_pad.name} -> {doel.name}  (in {map_pad.parent})")
            map_aangepast += 1
            if not args.proef:
                if doel.exists():
                    print(f"    OVERGESLAGEN: {doel} bestaat al")
                    continue
                map_pad.rename(doel)
    print(f"\nmapnamen: {map_aangepast}\n")

    # --- 5. controle ---
    if not args.proef:
        resten = 0
        for pad in vind_csvs(root):
            with pad.open(newline="", encoding="utf-8") as fh:
                for rij in csv.DictReader(fh):
                    if rij.get("platform") == PLATFORM and rij.get("device") in OMZETTING:
                        resten += 1
        if resten:
            print(f"LET OP: nog {resten} rijen met een oude devicenaam")
            return 1
        print("Controle: geen oude devicenamen meer in de data.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
