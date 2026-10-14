"""Controleert of dit platform een complete meetregel kan wegschrijven (eis T-7, Addendum A).

Draai dit op elk nieuw platform of besturingssysteem voordat er gemeten wordt. Het stelt vast:
  1. welke identificatie het platform zelf oplevert (platform, hardware, os_versie, device);
  2. dat de velden uit Addendum A paragraaf 5 gevuld zijn en een toegestane waarde hebben;
  3. dat een meetregel wegschrijven en terugteruglezen werkt, met de kolommen in de
     canonieke volgorde uit Data_Codebook.md.

Schrijft naar een tijdelijke map, zodat er geen meetdata vervuild raakt.

Gebruik (vanuit de scripts-map):
    python verifieer_logschema.py
    python verifieer_logschema.py --uit C:\\Windows\\Temp\\schemacheck
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.config import VALID_DEVICES, VALID_HARDWARE, VALID_PLATFORMS, RunContext
from common.logging_utils import CSV_FIELDS, TestLogger


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifieer het logschema op dit platform")
    parser.add_argument("--uit", default="", help="map om naar te schrijven (standaard: tijdelijke map)")
    args = parser.parse_args()

    uit = Path(args.uit) if args.uit else Path(tempfile.mkdtemp(prefix="loods_schemacheck_"))
    problemen: list[str] = []

    print("1. Identificatie van dit platform")
    ctx = RunContext()
    try:
        ctx.validate()
    except ValueError as exc:
        problemen.append(f"validate() faalt: {exc}")
    for naam, waarde in (("platform", ctx.platform), ("hardware", ctx.hardware),
                         ("os_versie", ctx.os_versie), ("device", ctx.device)):
        print(f"   {naam:10} = {waarde!r}")

    print("\n2. Toegestane waarden")
    if ctx.platform not in VALID_PLATFORMS:
        problemen.append(f"platform {ctx.platform!r} niet in {VALID_PLATFORMS}")
    if ctx.device not in VALID_DEVICES:
        problemen.append(f"device {ctx.device!r} niet in {VALID_DEVICES}")
    if not ctx.hardware:
        problemen.append("hardware is leeg - zet LOODS_HARDWARE (verplicht waar geen device-tree is)")
    elif ctx.hardware not in VALID_HARDWARE:
        problemen.append(f"hardware {ctx.hardware!r} niet in {VALID_HARDWARE}")
    if not ctx.os_versie:
        problemen.append("os_versie is leeg - zet LOODS_OS")
    if not problemen:
        print("   alle identificatievelden gevuld en toegestaan")

    print("\n3. Meetregel wegschrijven en terugteruglezen")
    with TestLogger(test_id="T0.0-schemacheck", fase="hardwareonderzoek", out_dir=uit) as log:
        log.log_run(temp_c=20.0, opmerkingen="verificatie logschema, geen meting")
        pad = log.csv_path

    with open(pad, newline="", encoding="utf-8") as fh:
        rijen = list(csv.DictReader(fh))

    if not rijen:
        problemen.append("geen rij weggeschreven")
    else:
        rij = rijen[-1]
        print(f"   bestand   = {pad}")
        print(f"   hardware  = {rij.get('hardware')!r}")
        print(f"   os_versie = {rij.get('os_versie')!r}")
        if list(rij.keys()) != CSV_FIELDS:
            problemen.append("kolomvolgorde wijkt af van CSV_FIELDS")
        for veld in ("platform", "hardware", "os_versie", "device"):
            if not rij.get(veld):
                problemen.append(f"kolom {veld} is leeg in de weggeschreven rij")

    print()
    if problemen:
        print("NIET GEHAALD - eis T-7 (Addendum A):")
        for p in problemen:
            print(f"  - {p}")
        return 1

    print("GEHAALD - eis T-7: dit platform schrijft een complete meetregel conform Data_Codebook.")
    print(f"Testbestand staat in: {uit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
