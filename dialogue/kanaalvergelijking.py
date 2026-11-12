"""Neemt een nacht op over alle microfoonkanalen tegelijk, met en zonder AGC.

Waarom dit script er is. De nachtmeting van 8 op 9 november is op kanaal 0 opgenomen - de
bewerkte uitgang van de XVF-3000, met automatische versterkingsregeling. Op dat kanaal vond de
energiedrempel 840 detecties per uur en meet de kamer -38 dBFS. Een losse opname van dertig
seconden over alle zes kanalen liet zien dat de ruwe microfoons op dezelfde akoestiek -61 dBFS
meten en nul keer detecteren: de AGC tilt de ruisvloer 21,6 dB op.

Die losse opname duurde dertig seconden en bevatte geen spraak. Daardoor staat de belangrijkste
vraag van het project nog open: is de WER van 40,2 % onder nachtruis (zie
analysis/nacht_keten.py) een eigenschap van de kamer of van kanaal 0? Dit script beantwoordt hem
door een hele nacht alle kanalen naast elkaar te bewaren, zodat elk kanaal achteraf door dezelfde
keten kan.

De AGC is op de ReSpeaker Mic Array v2.0 uit te zetten met het officiele afstelgereedschap:

    python tuning.py AGCONOFF 0      # uit
    python tuning.py AGCONOFF 1      # aan
    python tuning.py -p              # alle parameters tonen

Dat gereedschap staat in de repository respeaker/usb_4_mic_array. Met --agc regelt dit script
hem zelf, mits --tuning naar die tuning.py wijst. Seeed raadt aan een parameter per keer te
veranderen en dezelfde toetsen opnieuw te draaien; --agc beide doet dat in een run door de nacht
in twee helften te splitsen.

De opnames blijven op de lokale schijf en gaan nergens naartoe.

Gebruik:
    py -3.11 dialogue/kanaalvergelijking.py --uren 8 --doel /media/opnames/kanaalnacht
    py -3.11 dialogue/kanaalvergelijking.py --uren 8 --agc beide --tuning ~/usb_4_mic_array/tuning.py
    py -3.11 dialogue/kanaalvergelijking.py --uren 0.05 --blok-s 20   # korte proefrun
"""

from __future__ import annotations

import argparse
import csv
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
KANAALROL = {
    0: "bewerkt (AGC + beamforming)",
    1: "ruwe microfoon 1",
    2: "ruwe microfoon 2",
    3: "ruwe microfoon 3",
    4: "ruwe microfoon 4",
    5: "playback / merged",
}


def dbfs(x: np.ndarray) -> float:
    """Niveau in dBFS over een int16-signaal; -99 bij digitale stilte."""
    if x.size == 0:
        return -99.0
    rms = float(np.sqrt(np.mean((x.astype(np.float64) / 32768.0) ** 2)))
    return 20.0 * np.log10(max(rms, 1e-9))


def zoek_invoer(hint: str) -> int:
    """Geeft het apparaatnummer van de eerste invoer waarvan de naam de hint bevat."""
    for nummer, apparaat in enumerate(sd.query_devices()):
        if hint.lower() in apparaat["name"].lower() and apparaat["max_input_channels"] > 0:
            return nummer
    raise SystemExit(f"geen invoerapparaat gevonden met '{hint}' in de naam; "
                     f"beschikbaar:\n{sd.query_devices()}")


def zet_agc(tuning: Path | None, aan: bool) -> str:
    """Zet de AGC aan of uit via het officiele afstelgereedschap. Geeft terug wat er gebeurde."""
    if tuning is None:
        return "niet geregeld (geen --tuning opgegeven)"
    opdracht = [sys.executable, str(tuning), "AGCONOFF", "1" if aan else "0"]
    try:
        uit = subprocess.run(opdracht, capture_output=True, text=True, timeout=30)
    except Exception as fout:                                  # noqa: BLE001
        return f"MISLUKT ({fout})"
    if uit.returncode != 0:
        return f"MISLUKT (afsluitcode {uit.returncode}: {uit.stderr.strip()[:80]})"
    return "aan" if aan else "uit"


def neem_blok_op(apparaat: int, kanalen: int, blok_s: float) -> np.ndarray:
    opname = sd.rec(int(blok_s * SR), samplerate=SR, channels=kanalen,
                    dtype="int16", device=apparaat)
    sd.wait()
    return opname


def main() -> None:
    p = argparse.ArgumentParser(description="Nachtopname over alle kanalen, met en zonder AGC")
    p.add_argument("--doel", default="opnames/kanaalnacht", help="map voor de opnames")
    p.add_argument("--uren", type=float, default=8.0)
    p.add_argument("--blok-s", type=float, default=60.0)
    p.add_argument("--kanalen", type=int, default=6, help="6 voor de Mic Array v2.0")
    p.add_argument("--invoer-hint", default="ReSpeaker", help="deel van de apparaatnaam")
    p.add_argument("--agc", choices=["aan", "uit", "beide"], default="beide",
                   help="beide splitst de nacht in twee helften")
    p.add_argument("--tuning", type=Path, default=None,
                   help="pad naar tuning.py uit respeaker/usb_4_mic_array")
    p.add_argument("--bewaar-elk", type=int, default=1,
                   help="elk N-de blok als WAV bewaren; 1 = alles")
    p.add_argument("--start", default=None, help="wachten tot dit tijdstip, bv. 21:30")
    args = p.parse_args()

    doel = Path(args.doel)
    doel.mkdir(parents=True, exist_ok=True)
    log = doel / f"kanaalnacht_{datetime.now():%Y%m%d_%H%M}.csv"

    if args.start:
        nu = datetime.now()
        uur, minuut = (int(deel) for deel in args.start.split(":"))
        begin = nu.replace(hour=uur, minute=minuut, second=0, microsecond=0)
        if begin < nu:
            begin += timedelta(days=1)
        print(f"wachten tot {begin:%Y-%m-%d %H:%M} "
              f"({(begin - nu).total_seconds() / 60:.0f} min)", flush=True)
        time.sleep((begin - nu).total_seconds())

    apparaat = zoek_invoer(args.invoer_hint)
    print(f"opnemen via {sd.query_devices(apparaat)['name'].strip()}, "
          f"{args.kanalen} kanalen, {SR} Hz", flush=True)
    print(f"log: {log}", flush=True)

    # Bij 'beide' krijgt elke helft van de nacht een stand; anders de hele nacht een.
    helften = [(args.uren / 2, False), (args.uren / 2, True)] if args.agc == "beide" \
        else [(args.uren, args.agc == "aan")]

    velden = ["tijd", "blok", "agc", "bestand"] + [f"kanaal{k}_dbfs" for k in range(args.kanalen)]
    blok = 0
    with log.open("w", newline="", encoding="utf-8") as fh:
        schrijver = csv.DictWriter(fh, fieldnames=velden)
        schrijver.writeheader()
        fh.flush()

        for duur_uren, agc_aan in helften:
            stand = zet_agc(args.tuning, agc_aan)
            print(f"\n=== AGC {stand} - {duur_uren:.2f} uur ===", flush=True)
            einde = time.monotonic() + duur_uren * 3600
            while time.monotonic() < einde:
                blok += 1
                opname = neem_blok_op(apparaat, args.kanalen, args.blok_s)
                niveaus = [dbfs(opname[:, k]) for k in range(args.kanalen)]

                bestand = ""
                if args.bewaar_elk > 0 and blok % args.bewaar_elk == 0:
                    naam = f"blok{blok:05d}_{datetime.now():%H%M%S}_agc{'1' if agc_aan else '0'}.wav"
                    sf.write(str(doel / naam), opname, SR, subtype="PCM_16")
                    bestand = naam

                rij = {"tijd": datetime.now().isoformat(timespec="seconds"), "blok": blok,
                       "agc": "aan" if agc_aan else "uit", "bestand": bestand}
                rij.update({f"kanaal{k}_dbfs": round(niveaus[k], 2)
                            for k in range(args.kanalen)})
                schrijver.writerow(rij)
                fh.flush()

                print(f"  blok {blok:4d} {rij['tijd'][11:]} agc={rij['agc']}  "
                      + "  ".join(f"k{k}:{niveaus[k]:7.2f}" for k in range(args.kanalen)),
                      flush=True)

    print(f"\nKLAAR na {blok} blokken; log: {log}", flush=True)
    print("Vervolg: analysis/nacht_keten.py per kanaal draaien en de WER vergelijken.")


if __name__ == "__main__":
    main()
