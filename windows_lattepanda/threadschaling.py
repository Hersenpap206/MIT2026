"""Meet hoe de transcriptietijd schaalt met het aantal processorkernen.

Bepalend voor de hardwarekeuze: als de werklast nauwelijks met kernen schaalt, levert een
processor met meer kernen (zoals de LattePanda Sigma met 12) weinig op en telt vooral de snelheid
per kern. Schaalt hij wel, dan is een processor met meer kernen de goedkoopste weg naar de
responsie-eis.

Draait faster-whisper op dezelfde opnames met 1, 2 en 4 threads. Uitgevoerd op LP2 op
14 oktober 2026; de uitkomst staat in HARDWAREKEUZE - LattePanda-varianten en alternatieven.md.

De modelmap staat buiten de repo (modellen horen op een lokale schijf); overschrijf met
LOODS_MODELDIR als die elders staat.
"""

import os
import time
from pathlib import Path

import soundfile as sf
from faster_whisper import WhisperModel

REPO = Path(__file__).resolve().parent.parent
BASIS = REPO / "corpus" / "opnames" / "T2.2"
MODELDIR = Path(os.environ.get("LOODS_MODELDIR", r"D:\Loods WP3\modellen\faster-whisper"))
UITINGEN = ["N01i", "N02e", "N03g", "H01g", "S01e"]

bestanden = [BASIS / f"{u}.wav" for u in UITINGEN]
bestanden = [b for b in bestanden if b.is_file()]
if not bestanden:
    raise SystemExit(f"geen opnames gevonden in {BASIS}")

audio = [sf.read(str(b), dtype="float32")[0] for b in bestanden]
totale_duur = sum(len(a) for a in audio) / 16000
print(f"{len(audio)} opnames, samen {totale_duur:.1f} s audio\n")

resultaten = {}
for threads in (1, 2, 4):
    model = WhisperModel("small", device="cpu", compute_type="int8",
                         cpu_threads=threads, download_root=str(MODELDIR))
    # eerste transcriptie buiten de meting: modelinitialisatie hoort niet bij de rekentijd
    segs, _ = model.transcribe(audio[0], language="nl")
    list(segs)

    start = time.perf_counter()
    for a in audio:
        segs, _ = model.transcribe(a, language="nl")
        list(segs)
    duur = time.perf_counter() - start
    resultaten[threads] = duur
    print(f"{threads} thread(s): {duur:6.1f} s totaal, {duur/len(audio):5.1f} s per uiting, "
          f"{totale_duur/duur:4.2f}x realtime")
    del model

print()
basis = resultaten[1]
for t, d in resultaten.items():
    print(f"{t} thread(s): versnelling {basis/d:.2f}x  (ideaal zou {t}.00x zijn, "
          f"efficientie {100*basis/d/t:.0f}%)")
