"""
TTS-corpusgenerator voor het WP3-testcorpus (T2.1-baseline / T2.2-nachtzorgcondities).

**Laptop-only voorbewerkingsscript.** Dit draait NIET op de SBC's (RPi5/LattePanda/STM32MP257F) —
het is bedoeld om vóór een testdag op de laptop het bron-audiomateriaal te genereren. Daarom staat
de dependency (`edge-tts`) alleen in `requirements_windows.txt`, niet in `requirements_linux.txt`
of `requirements_termux.txt`.

**Methodologisch kernpunt — lees dit voordat je het manifest gebruikt:**
De hier gegenereerde mp3's zijn GEEN testaudio voor de ASR-engines. Ze zijn de bronstimulus die op
testdag via een speaker op een vaste, vooraf bepaalde afstand wordt afgespeeld en via de
SBC-microfoon wordt opgenomen. Het is die *opname* (met de echte microfoon, akoestiek van de
testruimte en afstand van de testopstelling) die uiteindelijk door whisper_runner.py/vosk_stream.py
/azure_speech.py via common/engine_runner.py wordt getranscribeerd en gescoord. Dit script schrijft
daarom een manifest waarin `wav_path` verwijst naar het *toekomstige opnamepad*
(`opnames/<test_id>/<uiting_id>.wav`, relatief t.o.v. de manifestlocatie) — een bestand dat op het
moment van genereren nog NIET bestaat. De mp3's zelf komen in een apart pad
(`tts_bronnen/<test_id>/<uiting_id>.mp3`) dat door engine_runner.py niet wordt gelezen.

Dit is bewust zo ontworpen: het garandeert dat elke testrun (elk platform/device/engine) precies
dezelfde bronstimulus krijgt afgespeeld — terwijl de daadwerkelijke ASR-test alsnog de echte
microfoon, akoestiek en afstand van die specifieke testopstelling meet, in plaats van een
kunstmatig schoon TTS-signaal direct in de engine te stoppen. Vóór een testrun moet je dus:
  1. dit script draaien om de mp3's + manifest te genereren,
  2. elke mp3 via een speaker afspelen op de in `bron.csv` opgegeven `afstand_m`,
  3. de opname met de SBC-microfoon wegschrijven naar het pad dat het manifest verwacht
     (`opnames/<test_id>/<uiting_id>.wav`),
  4. pas dan whisper_runner.py / vosk_stream.py / azure_speech.py draaien.

**Prosodie-presets per categorie — GEEN akoestisch echte fluister-/emotiesimulatie.** edge-tts
(en vrijwel alle mainstream neurale TTS) modelleert geen stemplooitrilling (of het ontbreken
daarvan); fluisteren is akoestisch een fundamenteel ander productiemechanisme (turbulente luchtstroom
zonder glottale pulsing) dat een rate/volume-aanpassing niet kan reproduceren. De onderstaande
presets zijn dus een pragmatische, goedkope benadering om prosodische variatie in het testcorpus te
krijgen (zachter/sneller/trager spreken) — geen ground truth voor "hoe een fluisterende of
emotionele bewoner werkelijk klinkt". Voor een sterkere T2.2-claim zou je deze stimuli moeten
aanvullen met opnames van echte sprekers.

Categorie -> (rate, volume):
    normaal     : +0%,  +0%
    gefluisterd : -15%, -60%
    emotioneel  : +15%, +0%
    incompleet  : -10%, +0%   (de afkapping zit al in de broncontent van `tekst`, niet in de
                                audio-rendering)

Bron-CSV-formaat (UTF-8, met header):
    uiting_id,tekst,categorie,afstand_m
    N01,Ik heb erge pijn op mijn borst,normaal,1.0
    N01i,Ik heb pijn op mijn...,incompleet,4.0

Gebruik:
    python generate_tts_corpus.py --bron corpus/bron_T2.1.csv --test-id T2.1 --output-dir corpus/
    python generate_tts_corpus.py --bron corpus/bron_T2.2.csv --test-id T2.2 --output-dir corpus/ \\
        --stem nl-NL-MaartenNeural
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from pathlib import Path

try:
    import edge_tts
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "edge-tts ontbreekt — installeer met: pip install edge-tts "
        "(alleen nodig op de laptop, zie requirements_windows.txt)"
    ) from exc

# Categorie -> (rate, volume). Zie module-docstring voor de methodologische kanttekening.
PROSODIE_PRESETS: dict[str, tuple[str, str]] = {
    "normaal": ("+0%", "+0%"),
    "gefluisterd": ("-15%", "-60%"),
    "emotioneel": ("+15%", "+0%"),
    "incompleet": ("-10%", "+0%"),
}

DEFAULT_STEM = "nl-NL-FennaNeural"


@dataclass
class BronRegel:
    uiting_id: str
    tekst: str
    categorie: str
    afstand_m: str  # vrije tekst doorgeven aan het manifest; leeg toegestaan


def laad_bron(bron_path: Path) -> list[BronRegel]:
    regels: list[BronRegel] = []
    with bron_path.open(encoding="utf-8") as fh:
        for rij in csv.DictReader(fh):
            regels.append(
                BronRegel(
                    uiting_id=rij["uiting_id"],
                    tekst=rij["tekst"],
                    categorie=rij["categorie"],
                    afstand_m=rij.get("afstand_m", "") or "",
                )
            )
    if not regels:
        raise ValueError(f"Bron-CSV {bron_path} bevat geen rijen")
    return regels


async def _genereer_mp3(tekst: str, stem: str, rate: str, volume: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(tekst, stem, rate=rate, volume=volume)
    await communicate.save(str(out_path))


def genereer_corpus(bron_path: Path, test_id: str, output_dir: Path, stem: str = DEFAULT_STEM) -> None:
    regels = laad_bron(bron_path)

    tts_dir = output_dir / "tts_bronnen" / test_id
    tts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{test_id}_manifest.csv"

    manifest_rijen: list[dict[str, str]] = []

    for regel in regels:
        if regel.categorie not in PROSODIE_PRESETS:
            raise ValueError(
                f"Onbekende categorie '{regel.categorie}' voor uiting {regel.uiting_id} — "
                f"verwacht een van: {sorted(PROSODIE_PRESETS)}"
            )
        rate, volume = PROSODIE_PRESETS[regel.categorie]
        mp3_path = tts_dir / f"{regel.uiting_id}.mp3"

        print(f"Genereer {mp3_path} (stem={stem}, rate={rate}, volume={volume})...")
        asyncio.run(_genereer_mp3(regel.tekst, stem, rate, volume, mp3_path))

        manifest_rijen.append(
            {
                "uiting_id": regel.uiting_id,
                "wav_path": f"opnames/{test_id}/{regel.uiting_id}.wav",
                "referentietekst": regel.tekst,
                "categorie": regel.categorie,
            }
        )

    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["uiting_id", "wav_path", "referentietekst", "categorie"])
        writer.writeheader()
        writer.writerows(manifest_rijen)

    print()
    print(f"Klaar: {len(manifest_rijen)} mp3's gegenereerd in {tts_dir}")
    print(f"Manifest geschreven naar {manifest_path}")
    print()
    print(
        "HERINNERING: het manifest verwijst naar opnamepaden onder "
        f"{output_dir / 'opnames' / test_id}/<uiting_id>.wav — die bestaan nog NIET. Speel elke "
        "mp3 uit tts_bronnen/ af via een speaker op de opgegeven afstand_m en neem de uiting op "
        "met de SBC-microfoon naar het verwachte opnamepad, vóórdat engine_runner.py "
        "(whisper_runner.py/vosk_stream.py/azure_speech.py) op dit manifest kan draaien."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Genereer TTS-bronaudio + manifest voor het WP3-testcorpus")
    parser.add_argument("--bron", required=True, help="pad naar bron-CSV (uiting_id,tekst,categorie,afstand_m)")
    parser.add_argument("--test-id", required=True, help="bv. T2.1 of T2.2 — bepaalt submap- en bestandsnamen")
    parser.add_argument("--output-dir", default="corpus/", help="basis-outputmap (default: corpus/)")
    parser.add_argument(
        "--stem",
        default=DEFAULT_STEM,
        help=f"edge-tts voice-naam (default: {DEFAULT_STEM}; alternatief: nl-NL-MaartenNeural)",
    )
    args = parser.parse_args()

    genereer_corpus(
        bron_path=Path(args.bron),
        test_id=args.test_id,
        output_dir=Path(args.output_dir),
        stem=args.stem,
    )


if __name__ == "__main__":
    main()
