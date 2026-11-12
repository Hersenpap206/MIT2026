"""Neemt een nacht op over alle microfoonkanalen tegelijk, in afwisselende AGC-condities.

Waarom dit script er is. De nachtmeting van 8 op 9 november is op kanaal 0 opgenomen - de
bewerkte uitgang van de XVF-3000, met automatische versterkingsregeling. Op dat kanaal vond de
energiedrempel 840 detecties per uur en meet de kamer -38 dBFS, terwijl de ruwe microfoons op
dezelfde akoestiek -61 dBFS meten. Daardoor staat de belangrijkste vraag van het project nog
open: is de WER van 40,2 % onder nachtruis (zie analysis/nacht_keten.py) een eigenschap van de
kamer of van kanaal 0?

Drie dingen zijn op 12 november op RASP2 vastgesteld en bepalen de opzet hieronder.

1. AGCONOFF 0 doet niet wat de naam suggereert. Het zet de regeling stil maar laat de
   versterking staan op de waarde die hij toevallig had bereikt. Gemeten: met AGC aan stond de
   versterking op 22,5x en lag kanaal 0 25,1 dB boven de ruwe microfoons; na AGCONOFF 0 stond hij
   op 26,7x en was het verschil 25,9 dB. Vrijwel niets veranderd.
2. AGCGAIN is de werkelijke knop. Met AGCONOFF 0 en AGCGAIN 1.0 zakt kanaal 0 naar 8,5 dB onder
   de ruwe microfoons - een verschuiving van ruim 34 dB ten opzichte van de fabrieksstand.
3. Absolute niveaus zijn onbruikbaar als maat, want de kamer verandert. Tussen twee metingen van
   tien seconden liepen de ruwe microfoons 6 dB op, en die staan buiten de AGC. Het verschil
   tussen kanaal 0 en de ruwe microfoons is wel kamer-onafhankelijk en is daarom de maat.

Daarom: niet de nacht in twee helften splitsen, maar de condities per segment afwisselen, zodat
drift in het omgevingsgeluid over alle condities gelijk uitvalt.

Het afstelgereedschap komt uit respeaker/usb_4_mic_array. Let op twee dingen bij dat script: het
vraagt rootrechten voor de USB-toegang, en in de versie van november 2026 staat nog
`response.tostring()`, dat sinds Python 3.9 is verdwenen - vervang dat door `response.tobytes()`.

De opnames blijven op de lokale schijf en gaan nergens naartoe.

Gebruik:
    py -3.11 dialogue/kanaalvergelijking.py --uren 8 --start 22:00 \
        --tuning ~/respeaker_tuning/tuning.py --doel ~/kanaalnacht
    py -3.11 dialogue/kanaalvergelijking.py --uren 0.05 --blok-s 10 --segment-min 1   # proefrun
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

SR = 16000

# Kanaalindeling van de ReSpeaker Mic Array v2.0 (XVF-3000), uit de Seeed-documentatie.
RUWE_KANALEN = (1, 2, 3, 4)
BEWERKT_KANAAL = 0

# De condities die afgewisseld worden. Elke conditie is een lijst parameters voor tuning.py.
CONDITIES: dict[str, tuple[tuple[str, str], ...]] = {
    "agc-aan": (("AGCONOFF", "1"),),                          # fabrieksstand, zoals 8 november
    "agc-uit": (("AGCONOFF", "0"),),                          # regeling stil, versterking blijft
    "gain-1": (("AGCONOFF", "0"), ("AGCGAIN", "1.0")),        # de werkelijke ingreep: 0 dB
}


def dbfs(x: np.ndarray) -> float:
    """Niveau in dBFS over een int16-signaal; -99 bij digitale stilte."""
    if x.size == 0:
        return -99.0
    rms = float(np.sqrt(np.mean((x.astype(np.float64) / 32768.0) ** 2)))
    return 20.0 * np.log10(max(rms, 1e-9))


def zoek_invoer(hint: str, kanalen: int) -> int:
    """Geeft het apparaatnummer van een invoer die de hint bevat en genoeg kanalen heeft.

    Het kanaalaantal is hier geen bijzaak maar het onderscheid. Zit er naast de Mic Array v2.0
    ook een ReSpeaker Lite aan dezelfde Pi, dan bevatten beide namen 'ReSpeaker' en zou de naam
    alleen de verkeerde microfoon kunnen opleveren - met een verloren meetnacht als gevolg. De
    Lite heeft 2 kanalen, de Mic Array v2.0 heeft 6.
    """
    kandidaten = [(nummer, apparaat) for nummer, apparaat in enumerate(sd.query_devices())
                  if hint.lower() in apparaat["name"].lower()
                  and apparaat["max_input_channels"] > 0]
    if not kandidaten:
        raise SystemExit(f"geen invoerapparaat gevonden met '{hint}' in de naam;\n"
                         f"{sd.query_devices()}")

    passend = [(n, a) for n, a in kandidaten if a["max_input_channels"] >= kanalen]
    if not passend:
        regels = "\n".join(f"  [{n}] {a['name'].strip()} - {a['max_input_channels']} kanalen"
                           for n, a in kandidaten)
        raise SystemExit(f"gevonden apparaten met '{hint}' hebben geen {kanalen} kanalen:\n"
                         f"{regels}\nHangt de Mic Array v2.0 er wel aan? "
                         f"Of bedoelde je --kanalen 2?")
    if len(passend) > 1:
        regels = "\n".join(f"  [{n}] {a['name'].strip()} - {a['max_input_channels']} kanalen"
                           for n, a in passend)
        print(f"let op: meer dan een passend apparaat gevonden, de eerste wordt gebruikt:\n"
              f"{regels}", flush=True)
    return passend[0][0]


def tuning_aanroep(tuning: Path, argumenten: list[str]) -> subprocess.CompletedProcess:
    """Roept tuning.py aan, met sudo zolang we niet als root draaien (USB-toegang vraagt dat)."""
    opdracht = [sys.executable, "-I", str(tuning), *argumenten]
    if os.geteuid() != 0:
        opdracht = ["sudo", *opdracht]
    return subprocess.run(opdracht, capture_output=True, text=True, timeout=30)


def zet_conditie(tuning: Path | None, naam: str) -> str:
    """Zet alle parameters van een conditie. Geeft terug wat er gebeurde, voor het logboek."""
    if tuning is None:
        return "niet geregeld (geen --tuning)"
    gelukt = []
    for parameter, waarde in CONDITIES[naam]:
        try:
            uit = tuning_aanroep(tuning, [parameter, waarde])
        except Exception as fout:                              # noqa: BLE001
            return f"MISLUKT bij {parameter} ({fout})"
        if uit.returncode != 0:
            return f"MISLUKT bij {parameter}: {uit.stderr.strip()[:70]}"
        gelukt.append(f"{parameter}={waarde}")
    return ", ".join(gelukt)


def lees_gain(tuning: Path | None) -> float | None:
    """Leest de actuele AGC-versterking, zodat in het logboek staat wat de DSP werkelijk deed."""
    if tuning is None:
        return None
    try:
        uit = tuning_aanroep(tuning, ["AGCGAIN"])
        return float(uit.stdout.strip().split()[-1])
    except Exception:                                          # noqa: BLE001
        return None


def maak_plan(uren: float, segment_min: float, namen: list[str]) -> list[tuple[str, float]]:
    """Verdeelt de nacht in segmenten die de condities herhaaldelijk aflopen."""
    plan, resterend = [], uren * 60.0
    i = 0
    while resterend > 0.01:
        duur = min(segment_min, resterend)
        plan.append((namen[i % len(namen)], duur))
        resterend -= duur
        i += 1
    return plan


def main() -> None:
    p = argparse.ArgumentParser(description="Nachtopname over alle kanalen, wisselende AGC")
    p.add_argument("--doel", default="opnames/kanaalnacht", help="map voor de opnames")
    p.add_argument("--uren", type=float, default=8.0)
    p.add_argument("--blok-s", type=float, default=60.0)
    p.add_argument("--kanalen", type=int, default=6, help="6 voor de Mic Array v2.0")
    p.add_argument("--invoer-hint", default="ReSpeaker", help="deel van de apparaatnaam")
    p.add_argument("--condities", default="agc-aan,agc-uit,gain-1",
                   help="komma-gescheiden, uit: " + ", ".join(CONDITIES))
    p.add_argument("--segment-min", type=float, default=20.0,
                   help="minuten per conditie voordat er gewisseld wordt")
    p.add_argument("--tuning", type=Path, default=None,
                   help="pad naar tuning.py uit respeaker/usb_4_mic_array")
    p.add_argument("--bewaar-elk", type=int, default=1,
                   help="elk N-de blok als WAV bewaren; 1 = alles, 0 = geen")
    p.add_argument("--start", default=None, help="wachten tot dit tijdstip, bv. 22:00")
    args = p.parse_args()

    namen = [n.strip() for n in args.condities.split(",") if n.strip()]
    onbekend = [n for n in namen if n not in CONDITIES]
    if onbekend:
        raise SystemExit(f"onbekende conditie(s): {onbekend}; keuze uit {list(CONDITIES)}")
    if args.tuning is not None and not args.tuning.is_file():
        raise SystemExit(f"tuning.py niet gevonden op {args.tuning}")

    doel = Path(args.doel).expanduser()
    doel.mkdir(parents=True, exist_ok=True)
    log = doel / f"kanaalnacht_{datetime.now():%Y%m%d_%H%M}.csv"

    # Nu al zoeken, zodat een verkeerde opstelling meteen opvalt en niet pas om 22:00.
    apparaat = zoek_invoer(args.invoer_hint, args.kanalen)
    print(f"gevonden: {sd.query_devices(apparaat)['name'].strip()}, "
          f"{args.kanalen} kanalen, {SR} Hz", flush=True)
    plan = maak_plan(args.uren, args.segment_min, namen)
    print(f"plan: {len(plan)} segmenten van {args.segment_min:.0f} min, "
          f"condities {' / '.join(namen)}", flush=True)
    print(f"log: {log}", flush=True)

    if args.start:
        nu = datetime.now()
        uur, minuut = (int(deel) for deel in args.start.split(":"))
        begin = nu.replace(hour=uur, minute=minuut, second=0, microsecond=0)
        if begin < nu:
            begin += timedelta(days=1)
        print(f"wachten tot {begin:%Y-%m-%d %H:%M} "
              f"({(begin - nu).total_seconds() / 60:.0f} min)", flush=True)
        time.sleep((begin - nu).total_seconds())
        # Opnieuw zoeken: wordt de array tussentijds losgemaakt en teruggezet, dan kan het
        # apparaatnummer veranderd zijn en zou een verouderd nummer de nacht verspelen.
        apparaat = zoek_invoer(args.invoer_hint, args.kanalen)
        print(f"opnemen via {sd.query_devices(apparaat)['name'].strip()}", flush=True)

    velden = (["tijd", "blok", "conditie", "agcgain", "bestand", "bewerkt_dbfs", "ruw_dbfs",
               "verschil_db"] + [f"kanaal{k}_dbfs" for k in range(args.kanalen)])
    blok = 0
    with log.open("w", newline="", encoding="utf-8") as fh:
        schrijver = csv.DictWriter(fh, fieldnames=velden)
        schrijver.writeheader()
        fh.flush()

        for conditie, duur_min in plan:
            stand = zet_conditie(args.tuning, conditie)
            print(f"\n=== {conditie} ({stand}) - {duur_min:.0f} min ===", flush=True)
            einde = time.monotonic() + duur_min * 60
            while time.monotonic() < einde:
                blok += 1
                opname = sd.rec(int(args.blok_s * SR), samplerate=SR,
                                channels=args.kanalen, dtype="int16", device=apparaat)
                sd.wait()

                niveaus = [dbfs(opname[:, k]) for k in range(args.kanalen)]
                bewerkt = niveaus[BEWERKT_KANAAL]
                ruw = float(np.mean([niveaus[k] for k in RUWE_KANALEN
                                     if k < args.kanalen]))

                bestand = ""
                if args.bewaar_elk > 0 and blok % args.bewaar_elk == 0:
                    naam = f"blok{blok:05d}_{datetime.now():%H%M%S}_{conditie}.wav"
                    sf.write(str(doel / naam), opname, SR, subtype="PCM_16")
                    bestand = naam

                gain = lees_gain(args.tuning)
                rij = {"tijd": datetime.now().isoformat(timespec="seconds"), "blok": blok,
                       "conditie": conditie,
                       "agcgain": "" if gain is None else round(gain, 3),
                       "bestand": bestand,
                       "bewerkt_dbfs": round(bewerkt, 2), "ruw_dbfs": round(ruw, 2),
                       "verschil_db": round(bewerkt - ruw, 2)}
                rij.update({f"kanaal{k}_dbfs": round(niveaus[k], 2)
                            for k in range(args.kanalen)})
                schrijver.writerow(rij)
                fh.flush()

                print(f"  blok {blok:4d} {rij['tijd'][11:]} {conditie:8s} "
                      f"k0 {bewerkt:7.2f}  ruw {ruw:7.2f}  verschil {bewerkt - ruw:6.2f} dB"
                      + (f"  gain {gain:.2f}" if gain is not None else ""), flush=True)

    # Altijd de fabrieksstand terugzetten, ook na een korte run.
    if args.tuning is not None:
        print(f"\nfabrieksstand terugzetten: {zet_conditie(args.tuning, 'agc-aan')}", flush=True)
    print(f"KLAAR na {blok} blokken; log: {log}", flush=True)
    print("Vervolg: analysis/nacht_keten.py per kanaal en per conditie draaien.")


if __name__ == "__main__":
    main()
