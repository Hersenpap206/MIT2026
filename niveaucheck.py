# Niveaucheck voor opnames: piek- en RMS-niveau in dBFS, met oordeel.
# Draait op de Pi: python3 niveaucheck.py <wav> [<wav> ...]
import sys
import wave
import math

import numpy as np

for pad in sys.argv[1:]:
    try:
        w = wave.open(pad)
        rate = w.getframerate()
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0
        w.close()
        piek = 20 * math.log10(max(1e-9, float(np.abs(d).max())))
        rms = 20 * math.log10(max(1e-9, math.sqrt(float((d * d).mean()))))
        duur = len(d) / rate
        if piek > -3:
            oordeel = "TE LUID - zet het volume lager"
        elif piek < -12:
            oordeel = "TE ZACHT - zet het volume hoger"
        else:
            oordeel = "GOED"
        print(f"{pad}: piek {piek:.1f} dBFS, rms {rms:.1f} dBFS, duur {duur:.2f} s -> {oordeel}")
    except FileNotFoundError:
        print(f"{pad}: ONTBREEKT")
