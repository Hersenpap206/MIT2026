"""T3.1 over alle zes engines: waar zit de fout, in het luisteren of in het beslissen?

Tot 12 november was T3.1 alleen op perfecte tekst en met een enkele engine beoordeeld. Dit script
scheidt de twee foutbronnen:

  het plafond    - wat de regelboom haalt als de transcriptie foutloos is
  de afbrokkeling - hoeveel daarvan verloren gaat door spraakherkenningsfouten

en doet dat voor beide regelbomen uit dialogue_engine.py: de placeholder uit het testplan en de
op dit corpus afgestemde versie.

De veiligheidsvraag staat apart. Voor een nachtzorgsysteem is niet elke fout gelijk. Een
noodsituatie die als "onbekend" eindigt, leidt tot doorvragen en is te herstellen. Een
noodsituatie die als praatje wordt afgedaan, is dat niet.

Gebruik:
    py -3.12 analysis/dialoog_over_engines.py "D:/Loods WP3/analyse_replicatie/data"
"""

from __future__ import annotations

import csv
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from dialogue.dialogue_engine import REGELBOOM, REGELBOOM_NACHTZORG, besluit

# De eerste letter van het uiting-id draagt de bedoelde intentie.
BEDOELD = {"N": "noodsituatie", "H": "hulpvraag", "S": "sociaal", "O": "onbekend"}

# De placeholder gebruikt fijnere categorienamen; dit is wat daarvan als "goed" telt.
AANVAARDBAAR_PLACEHOLDER = {
    "noodsituatie": {"noodsituatie"},
    "hulpvraag": {"hulpvraag_fysiek", "hulpvraag_emotioneel", "noodsituatie"},
    "sociaal": {"hulpvraag_emotioneel", "sociaal_praatje"},
    "onbekend": {"onbekend"},
}

ERNST = {"noodsituatie": 3, "hulpvraag": 2, "hulpvraag_fysiek": 2, "hulpvraag_emotioneel": 2,
         "sociaal": 1, "sociaal_praatje": 1, "onbekend": 0}


def lees_corpus(corpusmap: pathlib.Path) -> tuple[dict, dict]:
    tekst, stijl = {}, {}
    for setnaam in ("T2.2", "T2.2M"):
        bestand = corpusmap / f"bron_{setnaam}.csv"
        with bestand.open(newline="", encoding="utf-8") as fh:
            for rij in csv.DictReader(fh):
                tekst[rij["uiting_id"]] = rij["tekst"]
                stijl[rij["uiting_id"]] = rij["categorie"]
    return tekst, stijl


def goed(categorie: str, bedoeld: str, afgestemd: bool) -> bool:
    if afgestemd:
        return categorie == bedoeld
    return categorie in AANVAARDBAAR_PLACEHOLDER[bedoeld]


def plafond(tekst: dict, regelboom, afgestemd: bool, naam: str) -> None:
    print(f"HET PLAFOND - {naam} op perfecte tekst")
    print("=" * 78)
    per = {}
    for uid, t in tekst.items():
        bedoeld = BEDOELD[uid[0]]
        per.setdefault(bedoeld, []).append(goed(besluit(t, regelboom).categorie, bedoeld, afgestemd))
    totaal_goed = totaal_n = 0
    for k in ("noodsituatie", "hulpvraag", "sociaal", "onbekend"):
        v = per[k]
        totaal_goed += sum(v)
        totaal_n += len(v)
        print(f"  {k:14s} {sum(v):2d}/{len(v):2d}  = {sum(v) / len(v) * 100:5.1f} %")
    print(f"  {'TOTAAL':14s} {totaal_goed:2d}/{totaal_n:2d}  = "
          f"{totaal_goed / totaal_n * 100:5.1f} %")
    print()


def keten(df: pd.DataFrame, tekst: dict, regelboom, afgestemd: bool, naam: str) -> None:
    print(f"DE VOLLEDIGE KETEN - {naam} op de werkelijke transcripties, 1,0 m")
    print("=" * 86)
    print(f"{'engine':30s} {'alles':>8s} {'volledige uitingen':>20s} {'nood escaleert':>15s}")
    print("-" * 86)
    for engine, g in df.groupby("engine"):
        alles = [goed(besluit(r.hyp, regelboom).categorie, r.intentie, afgestemd)
                 for _, r in g.iterrows()]
        volledig = [goed(besluit(r.hyp, regelboom).categorie, r.intentie, afgestemd)
                    for _, r in g.iterrows() if r.stijl != "incompleet"]
        nood = g[g.intentie == "noodsituatie"]
        escaleert = sum(besluit(r.hyp, regelboom).categorie == "noodsituatie"
                        for _, r in nood.iterrows())
        print(f"{engine:30s} {sum(alles) / len(alles) * 100:6.1f} % "
              f"{sum(volledig) / len(volledig) * 100:18.1f} % "
              f"{escaleert:6d}/{len(nood):<3d} {escaleert / len(nood) * 100:5.1f} %")
    print()


def veiligheid(df: pd.DataFrame, regelboom) -> None:
    print("WAT GEBEURT ER MET DE NOODSITUATIES? (veilig falen versus onveilig falen)")
    print("=" * 86)
    print(f"{'engine':30s} {'escaleert':>12s} {'vraagt door':>14s} {'VERKEERDE ACTIE':>18s}")
    print("-" * 86)
    for engine, g in df.groupby("engine"):
        nood = g[g.intentie == "noodsituatie"]
        uitslag = [besluit(r.hyp, regelboom).categorie for _, r in nood.iterrows()]
        esc = uitslag.count("noodsituatie")
        vraag = uitslag.count("onbekend")
        mis = len(uitslag) - esc - vraag
        n = len(uitslag)
        print(f"{engine:30s} {esc:5d} {esc / n * 100:5.1f} % {vraag:6d} {vraag / n * 100:5.1f} %"
              f" {mis:9d} {mis / n * 100:5.1f} %")
    print()
    print("Een noodsituatie die als 'onbekend' eindigt, leidt tot LOG_EN_VRAAG_VERDUIDELIJKING:")
    print("het systeem vraagt door. Alleen de laatste kolom is een stille fout.")
    print()


def main() -> None:
    datamap = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                           else r"D:\Loods WP3\analyse_replicatie\data")
    corpusmap = pathlib.Path(__file__).resolve().parents[1] / "corpus"
    tekst, stijl = lees_corpus(corpusmap)

    frames = [pd.read_csv(p) for p in datamap.rglob("*.csv")]
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["run_id"], keep="first")
    df = df[df.testcorpus_uiting_id.notna() & (df.test_id == "T2.2")
            & (df.afstand_m == 1.0)].copy()
    df["hyp"] = df.transcript_hyp.fillna("").astype(str)
    df["intentie"] = df.testcorpus_uiting_id.str[0].map(BEDOELD)
    df["stijl"] = df.testcorpus_uiting_id.map(stijl)

    print("DEEL 1 - de placeholder uit het testplan\n")
    plafond(tekst, REGELBOOM, False, "placeholder")
    keten(df, tekst, REGELBOOM, False, "placeholder")

    print("DEEL 2 - de op dit corpus afgestemde regelboom\n")
    plafond(tekst, REGELBOOM_NACHTZORG, True, "afgestemde regelboom")
    keten(df, tekst, REGELBOOM_NACHTZORG, True, "afgestemde regelboom")
    veiligheid(df, REGELBOOM_NACHTZORG)

    print("UITGESPLITST NAAR SPREEKSTIJL - afgestemde regelboom op perfecte tekst")
    print("=" * 78)
    per = {}
    for uid, t in tekst.items():
        per.setdefault(stijl[uid], []).append(
            besluit(t, REGELBOOM_NACHTZORG).categorie == BEDOELD[uid[0]])
    for k in sorted(per):
        v = per[k]
        print(f"  {k:14s} {sum(v):2d}/{len(v):2d}  = {sum(v) / len(v) * 100:5.1f} %")
    print()
    print("De regels zijn tegen dit corpus geschreven; de score op volledige uitingen zegt niets")
    print("over formuleringen die er niet in staan.")


if __name__ == "__main__":
    main()
