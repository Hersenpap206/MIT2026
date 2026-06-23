"""
Laptop-side aggregatie van alle per-device CSV-logs (testplan WP3 — draait NIET op de SBC's).

Doorzoekt de hele `data/<platform>/<device>/<fase>/*.csv`-boom (gegenereerd door
common/logging_utils.py op elk van de 6 testdevices) en voegt alles samen tot één
masterdataset, met een extra `bronbestand`-kolom voor herleidbaarheid (belangrijk voor
publicatie/EFRO-verantwoording: elke rij in het masterbestand is terug te traceren naar het
exacte CSV-bestand + device + testdag waar die vandaan komt).

Gebruik:
    python aggregate_data.py --data-dir ../../data --out ../../data/master_dataset.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError("pandas ontbreekt — installeer met: pip install pandas") from exc

from common.logging_utils import CSV_FIELDS


def vind_csv_bestanden(data_dir: str | Path) -> list[Path]:
    data_dir = Path(data_dir)
    bestanden = sorted(data_dir.glob("*/*/*/*.csv"))
    if not bestanden:
        raise FileNotFoundError(
            f"Geen CSV-bestanden gevonden onder {data_dir} (verwacht structuur "
            "<platform>/<device>/<fase>/*.csv — zie common/logging_utils.py)"
        )
    return bestanden


def aggregeer(data_dir: str | Path) -> "pd.DataFrame":
    frames = []
    for pad in vind_csv_bestanden(data_dir):
        df = pd.read_csv(pad, dtype=str)  # str-inlezen: numerieke conversie gebeurt bewust pas
        # in stats_report.py/publication_figures.py, om lege velden niet stilzwijgend tot 0 te maken.
        ontbrekend = set(CSV_FIELDS) - set(df.columns)
        if ontbrekend:
            print(f"WAARSCHUWING: {pad} mist kolommen {ontbrekend} — wordt aangevuld met lege waarden")
            for kolom in ontbrekend:
                df[kolom] = ""
        df = df[CSV_FIELDS]
        df["bronbestand"] = str(pad)
        frames.append(df)

    master = pd.concat(frames, ignore_index=True)
    voor_dedup = len(master)
    master = master.drop_duplicates(subset=[c for c in CSV_FIELDS if c != "bronbestand"], keep="first")
    if voor_dedup != len(master):
        print(f"{voor_dedup - len(master)} exacte duplicaatrijen verwijderd (bv. door herhaald uitvoeren)")

    return master


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregeer alle device-CSV's tot één masterdataset")
    parser.add_argument("--data-dir", default="data", help="root van de data/-boom")
    parser.add_argument("--out", default="data/master_dataset.csv")
    args = parser.parse_args()

    master = aggregeer(args.data_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Masterdataset geschreven: {out_path} ({len(master)} rijen, {len(master.columns)} kolommen)")


if __name__ == "__main__":
    main()
