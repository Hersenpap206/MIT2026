"""FRR (gemiste hulpvragen) alsnog bepalen uit de bestaande transcripties.

Het logschema kent een FRR-veld, maar van de 3.157 meetregels dragen er 67 een waarde en die is
altijd 0,0: de runners hebben hem nooit gevuld. De gegevens om hem te bepalen liggen er wel. Elke
regel bevat de referentietekst en de werkelijke transcriptie, en een uiting die spraak bevat maar
niets of onzin oplevert, is precies een gemiste hulpvraag.

Twee maten:
  volledig gemist : de engine levert een lege transcriptie
  onbruikbaar     : de engine levert tekst, maar minder dan een kwart van de woorden klopt

Gebruik:
    py -3.12 analysis/frr_uit_transcripties.py "D:/Loods WP3/analyse_replicatie/data"
"""

from __future__ import annotations

import csv
import pathlib
import sys

import pandas as pd

DREMPEL_ONBRUIKBAAR = 75.0  # WER vanaf welke de transcriptie geen bruikbare hulpvraag meer is


def laad(datamap: pathlib.Path) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in datamap.rglob("*.csv")]
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["run_id"], keep="first")
    df = df[df.testcorpus_uiting_id.notna() & df.test_id.isin(["T2.1", "T2.2"])].copy()
    df["leeg"] = df.transcript_hyp.fillna("").astype(str).str.strip().str.len() == 0
    df["onbruikbaar"] = df.wer_pct >= DREMPEL_ONBRUIKBAAR
    return df


def tabel(df: pd.DataFrame, titel: str) -> None:
    print(titel)
    print("=" * 78)
    print(f"{'engine':30s} {'n':>5s} {'volledig gemist':>16s} {'onbruikbaar':>13s}")
    print("-" * 78)
    for engine, g in df.groupby("engine"):
        print(f"{engine:30s} {len(g):5d} {g.leeg.mean() * 100:14.1f} % "
              f"{g.onbruikbaar.mean() * 100:11.1f} %")
    print()


def main() -> None:
    datamap = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                           else r"D:\Loods WP3\analyse_replicatie\data")
    corpusmap = pathlib.Path(__file__).resolve().parents[1] / "corpus"
    df = laad(datamap)
    print(f"{len(df)} transcripties beoordeeld; drempel onbruikbaar: WER >= "
          f"{DREMPEL_ONBRUIKBAAR:.0f} %\n")

    tabel(df, "ALLE CONDITIES")
    op_1m = df[(df.test_id == "T2.2") & (df.afstand_m == 1.0)]
    tabel(op_1m, "NACHTZORGSPRAAK OP 1,0 METER (de conditie die telt, eis FRR < 10 %)")
    tabel(op_1m[op_1m.testcorpus_uiting_id.str.startswith("N")],
          "DE VEILIGHEIDSKRITISCHE SNEDE: alleen noodsituaties")

    categorie = {}
    for setnaam, stem in (("T2.2", "vrouw"), ("T2.2M", "man")):
        bestand = corpusmap / f"bron_{setnaam}.csv"
        if not bestand.is_file():
            continue
        with bestand.open(newline="", encoding="utf-8") as fh:
            for rij in csv.DictReader(fh):
                categorie[(stem, rij["uiting_id"])] = rij["categorie"]

    print("PER SPREEKSTIJL, faster-whisper small int8 op 1,0 m")
    print("=" * 78)
    g = op_1m[op_1m.engine == "faster-whisper-small-int8"].copy()
    g["stem"] = g.device.map({"LP1": "vrouw", "LP2": "man"})
    g["stijl"] = [categorie.get((a, b)) for a, b in zip(g.stem, g.testcorpus_uiting_id)]
    for stijl, sub in g.groupby("stijl"):
        print(f"  {stijl:14s} n={len(sub):3d}  volledig gemist {sub.leeg.mean() * 100:5.1f} %"
              f"  onbruikbaar {sub.onbruikbaar.mean() * 100:5.1f} %")


if __name__ == "__main__":
    main()
