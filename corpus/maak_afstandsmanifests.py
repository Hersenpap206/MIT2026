"""Genereert per afstand een manifest uit de bron-CSV's van T2.2 en T2.2M.

De bron-CSV bevat per uiting op welke afstand die is opgenomen. Voor het transcriberen van één
afstandsblok is een manifest met alleen die uitingen nodig. Deze manifests zijn tot nu toe
per meetdag op de devices zelf aangemaakt en stonden daardoor niet in het versiebeheer; zodra
een device uitging waren ze weg. Dit script maakt ze reproduceerbaar.

Gebruik (vanuit scripts/):
    python corpus/maak_afstandsmanifests.py
"""

from __future__ import annotations

import csv
from pathlib import Path

BASIS = Path(__file__).resolve().parent
AFSTANDEN = {"1.5": "d15", "2.5": "d25", "4.0": "d40"}


def main() -> None:
    for testset in ("T2.2", "T2.2M"):
        bron = BASIS / f"bron_{testset}.csv"
        if not bron.is_file():
            print(f"{bron.name} niet gevonden - overgeslagen")
            continue

        with bron.open(newline="", encoding="utf-8") as fh:
            alle = list(csv.DictReader(fh))

        for afstand, achtervoegsel in AFSTANDEN.items():
            rijen = [r for r in alle if r["afstand_m"] == afstand]
            if not rijen:
                print(f"{testset}: geen uitingen op {afstand} m")
                continue

            doel = BASIS / f"{testset}_manifest_{achtervoegsel}.csv"
            with doel.open("w", newline="", encoding="utf-8") as fh:
                schrijver = csv.writer(fh)
                schrijver.writerow(["uiting_id", "wav_path", "referentietekst", "categorie"])
                for r in rijen:
                    schrijver.writerow([
                        r["uiting_id"],
                        f"opnames/{testset}/{r['uiting_id']}.wav",
                        r["tekst"],
                        r["categorie"],
                    ])
            print(f"{doel.name}: {len(rijen)} uitingen")


if __name__ == "__main__":
    main()
