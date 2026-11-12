"""Tilt een lokaal taalmodel het plafond van de intentieherkenning op?

De regelboom uit het testplan haalt 41,7 % op perfecte tekst; een op dit corpus afgestemde
regelboom haalt 83,3 %, maar valt terug naar enkele procenten op formuleringen die er niet in
staan (zie analysis/dialoog_over_engines.py). Dekking is dus het knelpunt, en dat is precies waar
een taalmodel in beginsel sterk in is.

Deze toets legt dezelfde uitingen voor aan een model dat lokaal via Ollama draait. Lokaal is geen
detail maar een projecteis: zorginhoud verlaat de machine niet. Gemeten wordt nauwkeurigheid per
intentie en latentie, want de eis van 2.000 ms geldt ook hier.

Gemeten 12 november 2026 met llama3.2:1b: 30,0 % totaal, mediaan 2.603 ms, p95 4.093 ms op een
16-core desktop. Slechter dan de regelboom en over de latentie-eis.

Gebruik:
    py -3.12 analysis/intentie_taalmodel.py llama3.2:1b
    py -3.12 analysis/intentie_taalmodel.py qwen2.5:3b 128
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
import sys
import time
import urllib.request

OLLAMA = "http://localhost:11434/api/generate"
CATEGORIEEN = ("NOODSITUATIE", "HULPVRAAG", "SOCIAAL", "ONBEKEND")
BEDOELD = {"N": "noodsituatie", "H": "hulpvraag", "S": "sociaal", "O": "onbekend"}

PROMPT = """Je bent een triage-assistent in de nachtzorg van een GGZ-instelling. Een client zegt 's nachts iets tegen een spraakapparaat. Bepaal welke van vier categorieen het beste past.

NOODSITUATIE - direct gevaar voor de gezondheid of veiligheid. Lichamelijke nood, letsel, benauwdheid, bloedverlies, acute angst voor een persoon in de kamer.
HULPVRAAG - een concreet verzoek om hulp of een handeling van de nachtdienst. Medicatie, licht aan, iemand sturen, overlast.
SOCIAAL - behoefte aan contact, gezelschap of geruststelling. Eenzaamheid, niet kunnen slapen, gemis, angst in het donker zonder concreet gevaar.
ONBEKEND - de uiting is te vaag, afgebroken of teruggetrokken om een bedoeling uit af te leiden.

Antwoord met uitsluitend een van deze vier woorden: NOODSITUATIE, HULPVRAAG, SOCIAAL, ONBEKEND.

Uiting van de client: "{tekst}"
Categorie:"""


def classificeer(model: str, tekst: str, num_predict: int) -> tuple[str, float]:
    """Geeft (categorie, latentie in ms). Modellen die eerst redeneren, krijgen hun denkblok
    weggeknipt; van de resterende tekst telt de laatste genoemde categorie als het oordeel."""
    body = json.dumps({
        "model": model,
        "prompt": PROMPT.format(tekst=tekst),
        "stream": False,
        "options": {"temperature": 0, "num_predict": num_predict},
    }).encode()
    verzoek = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(verzoek, timeout=900) as antwoord:
        uitvoer = json.load(antwoord)["response"]
    ms = (time.perf_counter() - start) * 1000

    schoon = re.sub(r"<think>.*?</think>", " ", uitvoer, flags=re.S).upper()
    treffers = [(schoon.rfind(c), c) for c in CATEGORIEEN if schoon.rfind(c) >= 0]
    return (max(treffers)[1].lower() if treffers else "onleesbaar"), ms


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "llama3.2:1b"
    num_predict = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    corpusmap = pathlib.Path(__file__).resolve().parents[1] / "corpus"

    # Het corpus bevat elke basiszin drie keer (gefluisterd, emotioneel, incompleet); de eerste
    # twee delen dezelfde tekst. Classificeren gebeurt op unieke tekst.
    teksten = {}
    for setnaam in ("T2.2", "T2.2M"):
        with (corpusmap / f"bron_{setnaam}.csv").open(newline="", encoding="utf-8") as fh:
            for rij in csv.DictReader(fh):
                teksten.setdefault(rij["tekst"], rij["uiting_id"])
    uitingen = {uid: tekst for tekst, uid in teksten.items()}

    print(f"model: {model} - {len(uitingen)} unieke uitingen, perfecte tekst\n")
    classificeer(model, "warmdraaien", num_predict)  # eerste aanroep laadt het model

    per_intentie, latenties, fouten = {}, [], []
    for uid, tekst in sorted(uitingen.items()):
        categorie, ms = classificeer(model, tekst, num_predict)
        verwacht = BEDOELD[uid[0]]
        per_intentie.setdefault(verwacht, []).append(categorie == verwacht)
        latenties.append(ms)
        if categorie != verwacht:
            fouten.append((uid, tekst, verwacht, categorie))

    print("NAUWKEURIGHEID PER INTENTIE")
    print("=" * 78)
    goed = totaal = 0
    for k in ("noodsituatie", "hulpvraag", "sociaal", "onbekend"):
        v = per_intentie.get(k, [])
        if not v:
            continue
        goed += sum(v)
        totaal += len(v)
        print(f"  {k:14s} {sum(v):2d}/{len(v):2d}  = {sum(v) / len(v) * 100:5.1f} %")
    print(f"  {'TOTAAL':14s} {goed:2d}/{totaal:2d}  = {goed / totaal * 100:5.1f} %")

    latenties.sort()
    print()
    print(f"LATENTIE  mediaan {latenties[len(latenties) // 2]:7.0f} ms"
          f"   p95 {latenties[int(len(latenties) * 0.95)]:7.0f} ms"
          f"   max {latenties[-1]:7.0f} ms      (eis < 2.000 ms)")
    print()
    print("FOUTEN")
    print("=" * 78)
    for uid, tekst, verwacht, gekregen in fouten:
        print(f"  {uid}  {tekst[:50]:52s} {verwacht} -> {gekregen}")


if __name__ == "__main__":
    main()
