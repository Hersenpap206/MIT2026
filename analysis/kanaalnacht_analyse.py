"""Analyseert de zeskanaalsnacht van 12 op 13 november 2026.

De meting (dialogue/kanaalvergelijking.py) draaide acht uur in drie AGC-condities die per twintig
minuten afwisselden, met alle zes kanalen van de ReSpeaker Mic Array v2.0 bewaard. Zij moest een
vraag beantwoorden die laag 2 van de architectuur blokkeerde: is de WER van 40,2 % onder
nachtruis een eigenschap van de kamer of van kanaal 0?

Dit script doet vier dingen, die elk apart aan te roepen zijn:

  niveaus   - niveau per kanaal en per conditie uit het meetlogboek, plus de tijdsdrift
  drempel   - de energiedrempel uit de oorspronkelijke nachtmeting (RMS > 250 op frames van
              30 ms) nagebootst per conditie en per kanaal
  poort     - de inhoudelijke poortwachter (Silero-VAD) en de hallucinatieneiging van Whisper
  curve     - WER als functie van de aangenomen verhouding tussen spraak en nachtruis

Uitkomsten van 13 november 2026, 480 blokken van 60 s:

  conditie   AGC-gain   kanaal 0   ruwe mics   verschil   spreiding kanaal 0
  agc-aan      13,73x    -50,12      -60,70     +10,58 dB      10,45 dB
  agc-uit      28,20x    -38,91      -60,76     +21,84 dB       1,95 dB
  gain-1        1,00x    -67,74      -60,81      -6,93 dB       0,74 dB

De energiedrempel ging af op 23,8 % van de frames bij agc-aan en 66,3 % bij agc-uit, beide op
kanaal 0, en op 0,0 % bij gain-1 en op elk onbewerkt kanaal. Dat verklaart de 840 valse alarmen
per uur van 8 op 9 november, en wijst twee onafhankelijke oplossingen aan.

De inhoudelijke poortwachter ging in geen van de condities open en Whisper verzon geen woord.

De WER-curve laat zien dat de eis van 25 % gehaald wordt vanaf ongeveer 7,5 dB. Daarmee is de
openstaande vraag niet langer of de transcriptie werkt, maar wat de werkelijke verhouding is
tussen gefluisterde spraak en nachtruis - en die is op kanaal 0 niet betrouwbaar te meten, omdat
de AGC tussen stilte en spraak van versterking verandert.

Gebruik:
    py -3.12 analysis/kanaalnacht_analyse.py niveaus <logboek.csv>
    py -3.12 analysis/kanaalnacht_analyse.py drempel <map met mono-wavs>
    py -3.12 analysis/kanaalnacht_analyse.py poort   <map met mono-wavs>
    py -3.12 analysis/kanaalnacht_analyse.py curve   <map met ruis> <map met opnames>
"""

from __future__ import annotations

import csv
import pathlib
import re
import sys
import wave

import numpy as np

FRAME_MS = 30        # zoals dialogue/vad_hybrid.py
RMS_DREMPEL = 250    # de strengste instelling uit de nachtmeting (or_250)
SR = 16000
RUWE_KANALEN = (1, 2, 3, 4)


def lees_mono(pad: pathlib.Path) -> np.ndarray:
    with wave.open(str(pad)) as w:
        ruw = w.readframes(w.getnframes())
    return np.frombuffer(ruw, dtype=np.int16).astype(np.float32) / 32768.0


def dbfs(x: np.ndarray) -> float:
    return 20 * np.log10(max(float(np.sqrt(np.mean(x ** 2))), 1e-9))


def conditie_en_kanaal(pad: pathlib.Path) -> tuple[str, str]:
    """Bestandsnaam blok00011_220100_agc-aan_k0.wav -> ('agc-aan', 'k0')."""
    deel = pad.stem.split("_")
    return deel[2], deel[3]


def niveaus(logboek: pathlib.Path) -> None:
    import pandas as pd
    df = pd.read_csv(logboek, parse_dates=["tijd"])
    print(f"{len(df)} blokken, {df.tijd.min():%H:%M} tot {df.tijd.max():%H:%M}\n")
    print("PER CONDITIE")
    print("=" * 86)
    print(f"{'conditie':10s} {'n':>4s} {'AGC-gain':>9s} {'kanaal 0':>10s} {'ruwe mics':>10s} "
          f"{'VERSCHIL':>9s} {'spreiding k0':>13s}")
    print("-" * 86)
    for c, g in df.groupby("conditie", sort=False):
        print(f"{c:10s} {len(g):4d} {g.agcgain.mean():9.2f} {g.bewerkt_dbfs.mean():9.2f} "
              f"{g.ruw_dbfs.mean():10.2f} {g.verschil_db.mean():8.2f} dB "
              f"{g.bewerkt_dbfs.std():9.2f} dB")

    print()
    print("DE KAMER ZELF (ruwe microfoons, buiten de AGC om) - toets op tijdsdrift")
    print("=" * 86)
    df["uur"] = df.tijd.dt.hour
    pv = df.pivot_table(index="uur", columns="conditie", values="ruw_dbfs", aggfunc="mean")
    for uur, rij in pv.iterrows():
        print(f"  {uur:02d}:00   " + "   ".join(
            f"{c}: {rij[c]:6.2f}" for c in pv.columns if not np.isnan(rij[c])))
    print(f"\n  spreiding over de nacht: {df.ruw_dbfs.min():.2f} tot {df.ruw_dbfs.max():.2f} dBFS")
    print("  Blijft die spreiding klein, dan kan tijdsdrift het verschil tussen de condities")
    print("  niet verklaren en doet de afwisseling per twintig minuten zijn werk.")


def drempel(map_: pathlib.Path) -> None:
    """De energiedrempel uit de nachtmeting, nagebootst zonder webrtcvad.

    In 'or'-modus is de RMS-tak de tak die in de praktijk als eerste afgaat (zie de noot bij
    T4.2), dus die alleen nabootsen geeft een eerlijke ondergrens van het aantal detecties.
    """
    samen: dict[tuple[str, str], list[int]] = {}
    for pad in sorted(map_.glob("*.wav")):
        x = np.frombuffer(wave.open(str(pad)).readframes(10 ** 9), dtype=np.int16)
        n = int(SR * FRAME_MS / 1000)
        k = len(x) // n
        rms = np.sqrt((x[:k * n].reshape(k, n).astype(np.float64) ** 2).mean(axis=1))
        s = samen.setdefault(conditie_en_kanaal(pad), [0, 0])
        s[0] += int((rms > RMS_DREMPEL).sum())
        s[1] += k

    print(f"DE ENERGIEDREMPEL UIT DE NACHTMETING (RMS > {RMS_DREMPEL} op frames van {FRAME_MS} ms)")
    print("=" * 74)
    print(f"{'conditie':9s} {'kanaal':6s} {'frames boven drempel':>24s} {'aandeel':>10s}")
    print("-" * 74)
    for (c, k), (boven, totaal) in sorted(samen.items()):
        print(f"{c:9s} {k:6s} {boven:13d} / {totaal:<8d} {boven / totaal * 100:8.1f} %")


def poort(map_: pathlib.Path) -> None:
    """Gaat de inhoudelijke poortwachter af, en verzint Whisper iets?"""
    import os
    os.environ.setdefault("HF_HOME", str(pathlib.Path("hfcache").resolve()))
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")

    samen: dict[tuple[str, str], dict] = {}
    for pad in sorted(map_.glob("*.wav")):
        audio = lees_mono(pad)
        met_poort = list(model.transcribe(audio, language="nl", beam_size=5,
                                          vad_filter=True)[0])
        zonder = " ".join(s.text.strip() for s in
                          model.transcribe(audio, language="nl", beam_size=5,
                                           vad_filter=False)[0]).strip()
        s = samen.setdefault(conditie_en_kanaal(pad),
                             {"n": 0, "poort": 0, "woorden": 0, "niveau": []})
        s["n"] += 1
        s["poort"] += bool(met_poort)
        s["woorden"] += len(zonder.split())
        s["niveau"].append(dbfs(audio))

    print("DE INHOUDELIJKE POORTWACHTER OP NACHTRUIS")
    print("=" * 86)
    print(f"{'conditie':9s} {'kanaal':6s} {'niveau':>8s} {'poort ging open':>17s} "
          f"{'verzonnen woorden':>18s}")
    print("-" * 86)
    for (c, k), s in sorted(samen.items()):
        print(f"{c:9s} {k:6s} {np.mean(s['niveau']):7.2f} "
              f"{s['poort']:8d}/{s['n']:<8d} {s['woorden']:14d}")


def curve(ruismap: pathlib.Path, opnamemap: pathlib.Path) -> None:
    """WER als functie van de aangenomen verhouding tussen spraak en nachtruis."""
    import os
    os.environ.setdefault("HF_HOME", str(pathlib.Path("hfcache").resolve()))
    from faster_whisper import WhisperModel

    rng = np.random.default_rng(20261113)
    corpusmap = pathlib.Path(__file__).resolve().parents[1] / "corpus"
    referentie, stijl = {}, {}
    for setnaam in ("T2.2", "T2.2M"):
        with (corpusmap / f"bron_{setnaam}.csv").open(newline="", encoding="utf-8") as fh:
            for rij in csv.DictReader(fh):
                referentie[(setnaam, rij["uiting_id"])] = rij["tekst"]
                stijl[(setnaam, rij["uiting_id"])] = rij["categorie"]

    ruis = [lees_mono(p) for p in sorted(ruismap.glob("*.wav"))]
    opnames = [(s, p) for s in ("T2.2", "T2.2M")
               for p in sorted((opnamemap / s / "d10").glob("*.wav"))]
    model = WhisperModel("small", device="cpu", compute_type="int8")

    def woorden(t: str) -> list[str]:
        return re.sub(r"[^a-z0-9 ]", "", t.lower().replace("-", " ")).split()

    def wer(ref: str, hyp: str) -> float:
        r, h = woorden(ref), woorden(hyp)
        d = np.zeros((len(r) + 1, len(h) + 1), dtype=np.int32)
        d[:, 0] = np.arange(len(r) + 1)
        d[0, :] = np.arange(len(h) + 1)
        for i in range(1, len(r) + 1):
            for j in range(1, len(h) + 1):
                d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1,
                              d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
        return d[len(r), len(h)] / max(len(r), 1) * 100

    def meng(x: np.ndarray, snr_db: float) -> np.ndarray:
        n = ruis[rng.integers(len(ruis))]
        start = rng.integers(0, len(n) - len(x)) if len(n) > len(x) else 0
        stuk = np.resize(n[start:start + len(x)], len(x))
        doel = (float(np.sqrt(np.mean(x ** 2))) + 1e-9) / (10 ** (snr_db / 20.0))
        stuk = stuk * (doel / (float(np.sqrt(np.mean(stuk ** 2))) + 1e-9))
        return np.clip(x + stuk, -1.0, 1.0)

    print(f"{len(opnames)} opnames, {len(ruis)} ruisblokken\n")
    print(f"{'verhouding':>11s} {'WER gem.':>9s} {'mediaan':>8s} {'gefluisterd':>12s} "
          f"{'emotioneel':>11s} {'incompleet':>11s}")
    print("-" * 70)
    for snr in (2.5, 5.0, 7.5, 10.0, 15.0, 20.0):
        fouten, per_stijl = [], {}
        for setnaam, pad in opnames:
            audio = meng(lees_mono(pad), snr)
            hyp = " ".join(s.text.strip() for s in
                           model.transcribe(audio, language="nl", beam_size=5,
                                            vad_filter=True)[0]).strip()
            f = wer(referentie[(setnaam, pad.stem)], hyp)
            fouten.append(f)
            per_stijl.setdefault(stijl[(setnaam, pad.stem)], []).append(f)
        print(f"{snr:9.1f} dB {np.mean(fouten):8.2f} % {np.median(fouten):7.2f} % "
              f"{np.mean(per_stijl['gefluisterd']):11.2f} % "
              f"{np.mean(per_stijl['emotioneel']):10.2f} % "
              f"{np.mean(per_stijl['incompleet']):10.2f} %", flush=True)


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    opdracht = sys.argv[1]
    if opdracht == "niveaus":
        niveaus(pathlib.Path(sys.argv[2]))
    elif opdracht == "drempel":
        drempel(pathlib.Path(sys.argv[2]))
    elif opdracht == "poort":
        poort(pathlib.Path(sys.argv[2]))
    elif opdracht == "curve":
        curve(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
    else:
        raise SystemExit(f"onbekende opdracht {opdracht!r}; zie de docstring")


if __name__ == "__main__":
    main()
