"""
Decision-tree dialoogengine (testplan T3.1 — "eenvoudige regelgebaseerde afhandeling").

Geen ML-classifier: een transparante, auditeerbare regelboom die een herkende uiting (tekst,
afkomstig uit whisper_runner.py/vosk_stream.py/azure_speech.py) en optioneel sensorcontext
(PIR/licht uit common/sensors.py) afbeeldt op een actie-categorie. Transparantie is hier
functioneel: voor WBSO/MIT-verantwoording en voor een latere publicatie moet de beslislogica
volledig herleidbaar zijn — geen black-box.

De regelboom hieronder is een eerste, expliciet aanpasbare versie met categorieën uit het
testplan (noodsituatie / hulpvraag / sociaal-praatje / onbekend). Pas REGELBOOM aan zodra de
definitieve GGZ-nachtzorg-intentlijst is vastgesteld (zie WP3-testplan, T3.1-voorbereiding) —
de motor zelf (`besluit()`) hoeft dan niet te veranderen.

Gebruik (los):
    python dialogue_engine.py --tekst "ik heb erge pijn in mijn buik"

Gebruik (in een testrun, gelogd):
    python dialogue_engine.py --manifest corpus/T3.1_manifest.csv --test-id T3.1
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.latency_timer import LatencyTimer
from common.logging_utils import TestLogger


@dataclass(frozen=True)
class Regel:
    categorie: str
    actie: str
    patronen: tuple[str, ...]  # regex, case-insensitive, op woordgrenzen waar zinvol


# Volgorde is betekenisvol: eerste match wint. Noodsituaties staan daarom vooraan.
REGELBOOM: tuple[Regel, ...] = (
    Regel(
        categorie="noodsituatie",
        actie="ESCALEER_DIRECT_NAAR_NACHTDIENST",
        patronen=(r"\bval(len|t)?\b", r"\bgevallen\b", r"\bniet meer op kan\b", r"\bbloed\b", r"\bpaniek\b"),
    ),
    Regel(
        categorie="hulpvraag_fysiek",
        actie="MELD_AAN_NACHTDIENST",
        patronen=(r"\bpijn\b", r"\bmisselijk\b", r"\bbenauwd\b", r"\bniet lekker\b"),
    ),
    Regel(
        categorie="hulpvraag_emotioneel",
        actie="BIED_GESPREKSMODULE_AAN",
        patronen=(r"\bangstig\b", r"\bonrustig\b", r"\bbang\b", r"\bniet kan slapen\b", r"\bpieker"),
    ),
    Regel(
        categorie="sociaal_praatje",
        actie="KORT_GESPREK_GEEN_ESCALATIE",
        patronen=(r"\bgoedenacht\b", r"\bhoe gaat het\b", r"\bik wilde alleen\b"),
    ),
)

CATEGORIE_ONBEKEND = "onbekend"
ACTIE_ONBEKEND = "LOG_EN_VRAAG_VERDUIDELIJKING"


@dataclass
class Besluit:
    categorie: str
    actie: str
    gematchte_regel: str | None


def besluit(tekst: str) -> Besluit:
    """Doorloopt REGELBOOM in volgorde en geeft het eerste matchende besluit terug."""
    tekst_lower = tekst.lower()
    for regel in REGELBOOM:
        for patroon in regel.patronen:
            if re.search(patroon, tekst_lower):
                return Besluit(categorie=regel.categorie, actie=regel.actie, gematchte_regel=patroon)
    return Besluit(categorie=CATEGORIE_ONBEKEND, actie=ACTIE_ONBEKEND, gematchte_regel=None)


def run_corpus(manifest_path: str | Path, test_id: str, fase: str = "dialoogafhandeling") -> None:
    """Verwerkt een manifest (CSV: uiting_id,tekst,verwachte_categorie) en logt besluit + latentie
    + correctheid (vergelijking met verwachte_categorie) — voor de T3.1-nauwkeurigheidsmeting."""
    manifest_path = Path(manifest_path)
    timer = LatencyTimer()
    n_correct = 0
    n_totaal = 0

    with TestLogger(test_id=test_id, fase=fase) as logger, manifest_path.open(encoding="utf-8") as fh:
        for rij in csv.DictReader(fh):
            with timer.measure(label=rij["uiting_id"]) as m:
                d = besluit(rij["tekst"])

            verwacht = rij.get("verwachte_categorie", "")
            correct = verwacht == "" or d.categorie == verwacht
            n_totaal += 1
            n_correct += int(correct)

            logger.log_run(
                testcorpus_uiting_id=rij["uiting_id"],
                transcript_ref=rij["tekst"],
                latentie_ms=m.latentie_ms,
                opmerkingen=(
                    f"categorie={d.categorie}; actie={d.actie}; regel={d.gematchte_regel}; "
                    f"verwacht={verwacht or 'n.v.t.'}; correct={correct}"
                ),
            )

    pct_correct = round((n_correct / n_totaal) * 100, 1) if n_totaal else 0.0
    print(f"Dialoogengine: {n_correct}/{n_totaal} correct geclassificeerd ({pct_correct}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision-tree dialoogengine (T3.1)")
    groep = parser.add_mutually_exclusive_group(required=True)
    groep.add_argument("--tekst", help="losse uiting testen zonder logging")
    groep.add_argument("--manifest", help="CSV met uiting_id,tekst,verwachte_categorie voor een gelogde testrun")
    parser.add_argument("--test-id", default="T3.1", help="vereist samen met --manifest")
    parser.add_argument("--fase", default="dialoogafhandeling")
    args = parser.parse_args()

    if args.tekst:
        d = besluit(args.tekst)
        print(f"categorie={d.categorie}  actie={d.actie}  regel={d.gematchte_regel}")
    else:
        run_corpus(args.manifest, args.test_id, args.fase)


if __name__ == "__main__":
    main()
