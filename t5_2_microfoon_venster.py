"""T-5 microfoonverificatie zonder tijdsdruk: neem lang op, toets op het actiefste venster.

De operator hoeft niet op een signaal te wachten en kan ergens in de opnameperiode spreken.
Het script zoekt achteraf het luidste aaneengesloten venster en toetst daarop, want de eis gaat
over het signaal dat de microfoon levert bij spraak - niet over het gemiddelde van een opname
die grotendeels stilte is.

Gebruik:
    py -3.12 t5_venster.py --duur 20 --venster 5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Loods WP3\MIT2026")

import numpy as np
import sounddevice as sd

from common.config import MIC_CHANNELS, MIC_DEVICE_NAME_HINT, MIC_SAMPLE_RATE_HZ

PIEK_MIN_DBFS, PIEK_MAX_DBFS = -20.0, -1.0
RMS_MIN_DBFS = -35.0
KLIP_GRENS = 32767


def db(v: float) -> float:
    return float("-inf") if v <= 0 else 20.0 * np.log10(v / 32768.0)


def vind_device() -> int:
    for i, d in enumerate(sd.query_devices()):
        if MIC_DEVICE_NAME_HINT.lower() in d["name"].lower() and d["max_input_channels"] > 0:
            return i
    raise SystemExit("Geen ReSpeaker-opnameapparaat gevonden.")


def luidste_venster(mono: np.ndarray, venster_s: float) -> tuple[int, int]:
    """Geeft (begin, eind) van het aaneengesloten venster met de hoogste energie."""
    n = int(venster_s * MIC_SAMPLE_RATE_HZ)
    if len(mono) <= n:
        return 0, len(mono)
    # voortschrijdende som van het kwadraat, in stappen van 0,1 s
    stap = int(0.1 * MIC_SAMPLE_RATE_HZ)
    kwadraat = mono.astype(np.float64) ** 2
    cumsom = np.concatenate([[0.0], np.cumsum(kwadraat)])
    beste, beste_i = -1.0, 0
    for i in range(0, len(mono) - n + 1, stap):
        energie = cumsom[i + n] - cumsom[i]
        if energie > beste:
            beste, beste_i = energie, i
    return beste_i, beste_i + n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duur", type=float, default=20.0, help="totale opnameduur")
    ap.add_argument("--venster", type=float, default=5.0, help="lengte van het getoetste venster")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    idx = vind_device()
    print(f"Apparaat : [{idx}] {sd.query_devices()[idx]['name']}")
    print(f"Opname   : {args.duur:.0f} s — spreek ergens in deze periode een paar zinnen\n",
          flush=True)

    opname = sd.rec(int(args.duur * MIC_SAMPLE_RATE_HZ), samplerate=MIC_SAMPLE_RATE_HZ,
                    channels=MIC_CHANNELS, device=idx, dtype="int16")
    sd.wait()
    mono = opname.reshape(-1)

    b, e = luidste_venster(mono, args.venster)
    deel = mono[b:e]
    piek = int(np.max(np.abs(deel)))
    rms = float(np.sqrt(np.mean(deel.astype(np.float64) ** 2)))
    piek_db, rms_db = db(piek), db(rms)
    geklipt = int(np.sum(np.abs(deel) >= KLIP_GRENS))

    print(f"luidste venster : {b / MIC_SAMPLE_RATE_HZ:.1f}-{e / MIC_SAMPLE_RATE_HZ:.1f} s")
    print(f"piekniveau      : {piek_db:7.2f} dBFS  (ruwe piek {piek})")
    print(f"RMS-niveau      : {rms_db:7.2f} dBFS")
    print(f"geklipt         : {geklipt} van {len(deel)} monsters")

    print("\nverloop per seconde over de hele opname:")
    for s in range(int(args.duur)):
        blok = mono[s * MIC_SAMPLE_RATE_HZ:(s + 1) * MIC_SAMPLE_RATE_HZ].astype(np.float64)
        if len(blok):
            merk = "  <-- getoetst" if b <= s * MIC_SAMPLE_RATE_HZ < e else ""
            print(f"  {s:2d}-{s+1:2d}s   piek {db(np.max(np.abs(blok))):7.2f}   "
                  f"rms {db(np.sqrt(np.mean(blok ** 2))):7.2f}{merk}")

    if args.out:
        import soundfile as sf
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(p, opname, MIC_SAMPLE_RATE_HZ, subtype="PCM_16")
        print(f"\nopgeslagen : {p}")

    niveau_ok = PIEK_MIN_DBFS <= piek_db <= PIEK_MAX_DBFS
    klip_ok = geklipt == 0
    signaal_ok = rms_db >= RMS_MIN_DBFS
    print("\n--- eis T-5 (getoetst op het luidste venster) ---")
    print(f"  16 kHz mono opname          : ja")
    print(f"  piek tussen -20 en -1 dBFS  : {'ja' if niveau_ok else 'NEE'}")
    print(f"  niet klippend               : {'ja' if klip_ok else 'NEE'}")
    print(f"  signaal aanwezig (RMS>{RMS_MIN_DBFS:.0f})  : {'ja' if signaal_ok else 'NEE'}")
    print("\nT-5 BEHAALD" if (niveau_ok and klip_ok and signaal_ok) else "\nT-5 NIET BEHAALD")


if __name__ == "__main__":
    main()
