"""Verificatie van eis T-5 (microfoon) uit Addendum A: werkt de ReSpeaker op dit platform?

De eis luidt: opname van 16 kHz mono mogelijk, piekniveau tussen -20 en -1 dBFS, niet klippend.
Dat is een platformtest, geen akoestische meting: hij stelt vast dat het besturingssysteem de
USB-microfoon als opnameapparaat aanbiedt en dat er een bruikbaar signaalniveau uit komt.

Deze test vervangt niet de afstandsmetingen van T2.2. Die hoeven op een tweede platform ook niet
herhaald te worden — Addendum A staat bij T5.4 expliciet hergebruik van bestaande opnames toe, en
dat is methodologisch ook juister: met identieke audio meet je het platform en niet het verschil
tussen twee opnamesessies.

Gebruik (spreek of maak geluid tijdens de opname):
    py -3.12 t5_2_microfoon.py --duur 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from common.config import MIC_CHANNELS, MIC_DEVICE_NAME_HINT, MIC_SAMPLE_RATE_HZ

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError as exc:  # pragma: no cover
    raise ImportError("sounddevice/soundfile ontbreken — pip install sounddevice soundfile") from exc

PIEK_MIN_DBFS = -20.0
PIEK_MAX_DBFS = -1.0
KLIP_GRENS = 32767          # int16-maximum; daarboven kan niet, daarop is klippen

# Zonder deze ondergrens zou de test slagen op een stille opname met één incidentele tik: de
# piek haalt dan de eis terwijl er geen signaal is. Bij stille kamerruis ligt de RMS rond
# -40 dBFS, bij spraak op korte afstand ruim daarboven. De eis is bedoeld om vast te stellen
# dat er een bruikbaar signaal binnenkomt, niet dat er ooit een geluid was.
RMS_MIN_DBFS = -35.0


def dbfs(waarde: float) -> float:
    """Omrekenen naar dBFS ten opzichte van de int16-volle schaal."""
    if waarde <= 0:
        return float("-inf")
    return 20.0 * np.log10(waarde / 32768.0)


def vind_device() -> int:
    kandidaten = [(i, d) for i, d in enumerate(sd.query_devices())
                  if MIC_DEVICE_NAME_HINT.lower() in d["name"].lower()
                  and d["max_input_channels"] > 0]
    if not kandidaten:
        lijst = "\n".join(f"  [{i}] {d['name']}" for i, d in enumerate(sd.query_devices()))
        raise SystemExit(f"Geen opnameapparaat met '{MIC_DEVICE_NAME_HINT}' in de naam.\n{lijst}")
    return kandidaten[0][0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Verificatie eis T-5 (microfoon)")
    ap.add_argument("--duur", type=float, default=5.0, help="opnameduur in seconden")
    ap.add_argument("--out", default=None, help="optioneel: bewaar de opname op dit pad")
    ap.add_argument("--device-index", type=int, default=None)
    args = ap.parse_args()

    idx = args.device_index if args.device_index is not None else vind_device()
    naam = sd.query_devices()[idx]["name"]
    print(f"Apparaat : [{idx}] {naam}")
    print(f"Formaat  : {MIC_SAMPLE_RATE_HZ} Hz, {MIC_CHANNELS} kanaal")
    print(f"Opname   : {args.duur:.0f} s — maak nu geluid\n")

    opname = sd.rec(int(args.duur * MIC_SAMPLE_RATE_HZ), samplerate=MIC_SAMPLE_RATE_HZ,
                    channels=MIC_CHANNELS, device=idx, dtype="int16")
    sd.wait()
    mono = opname.reshape(-1)

    piek = int(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    piek_db, rms_db = dbfs(piek), dbfs(rms)
    geklipt = int(np.sum(np.abs(mono) >= KLIP_GRENS))

    print(f"piekniveau : {piek_db:7.2f} dBFS   (ruwe piek {piek})")
    print(f"RMS-niveau : {rms_db:7.2f} dBFS")
    print(f"geklipte monsters: {geklipt} van {len(mono)}")

    if args.out:
        pad = Path(args.out)
        pad.parent.mkdir(parents=True, exist_ok=True)
        sf.write(pad, opname, MIC_SAMPLE_RATE_HZ, subtype="PCM_16")
        print(f"opgeslagen : {pad}")

    # waar zit de piek? Een piek in de eerste milliseconden is een inschakelpuls van het
    # apparaat en zegt niets over de opnamekwaliteit.
    piek_i = int(np.argmax(np.abs(mono)))
    piek_ms = piek_i / MIC_SAMPLE_RATE_HZ * 1000
    print(f"piek op    : {piek_ms:.0f} ms van {len(mono) / MIC_SAMPLE_RATE_HZ * 1000:.0f} ms")

    # toetsing
    print("\n--- eis T-5 ---")
    formaat_ok = True   # we nemen expliciet op 16 kHz mono op; lukt dat niet, dan faalt sd.rec
    niveau_ok = PIEK_MIN_DBFS <= piek_db <= PIEK_MAX_DBFS
    klip_ok = geklipt == 0
    signaal_ok = rms_db >= RMS_MIN_DBFS
    print(f"  16 kHz mono opname          : {'ja' if formaat_ok else 'nee'}")
    print(f"  piek tussen -20 en -1 dBFS  : {'ja' if niveau_ok else 'NEE'}")
    print(f"  niet klippend               : {'ja' if klip_ok else 'NEE'}")
    print(f"  signaal aanwezig (RMS>{RMS_MIN_DBFS:.0f})  : {'ja' if signaal_ok else 'NEE'}")

    if niveau_ok and klip_ok and signaal_ok:
        print("\nT-5 BEHAALD")
    elif not signaal_ok:
        print(f"\nT-5 NIET BEHAALD — de RMS van {rms_db:.1f} dBFS wijst op een stille opname. "
              "Een piek alleen volstaat niet: die kan van een enkele tik komen. "
              "Herhaal terwijl er doorlopend gesproken wordt.")
    elif piek_db < PIEK_MIN_DBFS:
        print("\nT-5 NIET BEHAALD — signaal te zwak. Harder spreken, dichterbij, of de "
              "ingangsversterking verhogen; herhaal daarna.")
    else:
        print("\nT-5 NIET BEHAALD — signaal te sterk of klippend. Zachter of verder weg.")


if __name__ == "__main__":
    main()
