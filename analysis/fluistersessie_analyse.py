"""Analyseert de fluistersessie van 16 november 2026: de eerste meting met een echte stem.

Opzet van de sessie. Twintig nachtzorgzinnen, door een mens gefluisterd op 1,0 meter, doorlopend
opgenomen over alle zes kanalen in twee AGC-condities (fabrieksstand en AGCGAIN 1.0). De zinnen
zijn achteraf op de stiltes geknipt; de stilte vlak voor elke zin is de ruismeting, in hetzelfde
bestand en bij dezelfde versterking als de spraak erna. Dat is de vergelijking die op kanaal 0
niet te maken was toen achtergrond en spraak los van elkaar waren gemeten, en waaruit de onjuiste
aanname van 2,5 dB was ontstaan.

Uitkomsten:

  conditie             kanaal 0    ruwe microfoons
  AGC aan (fabriek)     18,93 dB          8,16 dB
  AGCGAIN 1.0           13,02 dB          5,12 dB

De verhouding is dus geen knelpunt: 18,93 dB ligt ruim boven de 7,5 dB die de curve in
kanaalnacht_analyse.py als drempel aanwees. En de DSP helpt: kanaal 0 geeft ruim tien decibel meer
verhouding dan een onbewerkte microfoon, omdat bundelvorming en ruisonderdrukking de spraak
sterker versterken dan de ruis. De AGC is een probleem voor een energiedrempel, niet voor de
transcriptie.

De WER wel. Op kanaal 0 in fabrieksstand 41,05 procent, tegen 14,10 procent op het synthetische
corpus bij een betere verhouding. Het verschil zit in de stem: Edge TTS "gefluisterd" heeft
stembandtrilling en een echte fluistering niet. Met AGCGAIN 1.0 loopt de WER boven de 100 procent
en is de transcriptie onbruikbaar; die instelling valt daarmee af als werkstand.

Tot slot een waarschuwing over de maat zelf. Een uiting kwam eruit als "Ik denk dat er niemand in
mijn kamer staat" in plaats van "iemand": 8 procent WER, betekenis omgekeerd. De regelboom haalde
op diezelfde transcripties 14 van de 20 en liet geen enkele noodsituatie verkeerd aflopen. Voor
nachtzorg telt de actie, niet het aantal kloppende woorden.

Gebruik:
    py -3.12 analysis/fluistersessie_analyse.py knippen "D:/Loods WP3/fluistersessie"
    py -3.12 analysis/fluistersessie_analyse.py wer     "D:/Loods WP3/fluistersessie"
"""

from __future__ import annotations

import csv
import pathlib
import re
import sys
import wave

import numpy as np

SR, KANALEN, RUW = 16000, 6, (1, 2, 3, 4)
VENSTER = 0.05        # 50 ms analysevensters
MARGE_DB = 6.0        # spraak = meer dan dit boven de ruisvloer
MIN_DUUR = 0.5        # korter telt niet als zin
GAT = 1.0             # stiltes korter dan dit verbinden een zin
RUIS_VOOR = 2.0       # seconden ruis vlak voor de zin


def db(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    return -999.0 if r <= 0 else 20 * np.log10(r / 32768.0)


def lees(pad: pathlib.Path) -> np.ndarray:
    with wave.open(str(pad)) as w:
        ruw = w.readframes(w.getnframes())
    return np.frombuffer(ruw, dtype=np.int16).reshape(-1, KANALEN)


def woorden(t: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", "", t.lower().replace("-", " ")).split()


def wer_pct(ref: str, hyp: str) -> float:
    r, h = woorden(ref), woorden(hyp)
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=np.int32)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1,
                          d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / max(len(r), 1) * 100


def zinnen_uit_corpus() -> tuple[list[str], list[str]]:
    bron = pathlib.Path(__file__).resolve().parents[1] / "corpus" / "bron_T2.2.csv"
    with bron.open(newline="", encoding="utf-8") as fh:
        rijen = [r for r in csv.DictReader(fh) if r["categorie"] == "gefluisterd"]
    return [r["uiting_id"] for r in rijen], [r["tekst"] for r in rijen]


def segmenteer(x: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    """Vindt de zinnen op basis van de ruwe microfoons, want die kennen geen AGC."""
    ruw = x[:, list(RUW)].astype(np.float64).mean(axis=1)
    n = int(VENSTER * SR)
    k = len(ruw) // n
    rms = np.sqrt((ruw[:k * n].reshape(k, n) ** 2).mean(axis=1))
    niveau = 20 * np.log10(np.maximum(rms, 1) / 32768)
    stil = float(np.median(niveau[:int(15 / VENSTER)]))
    actief = niveau > stil + MARGE_DB
    uit: list[tuple[float, float]] = []
    start = laatste = None
    for i, a in enumerate(actief):
        if a:
            if start is None:
                start = i
            laatste = i
        elif start is not None and (i - laatste) * VENSTER > GAT:
            if (laatste - start) * VENSTER >= MIN_DUUR:
                uit.append((start * VENSTER, (laatste + 1) * VENSTER))
            start = None
    if start is not None and (laatste - start) * VENSTER >= MIN_DUUR:
        uit.append((start * VENSTER, (laatste + 1) * VENSTER))
    return uit, stil


def knippen(map_: pathlib.Path) -> None:
    ids, zinnen = zinnen_uit_corpus()
    doel = map_ / "segmenten"
    doel.mkdir(parents=True, exist_ok=True)
    alles: list[dict] = []
    for conditie in ("agc-aan", "gain-1"):
        pad = map_ / f"doorlopend_{conditie}.wav"
        if not pad.is_file():
            print(f"{conditie}: bestand ontbreekt")
            continue
        x = lees(pad)
        segs, stil = segmenteer(x)
        print(f"\n=== {conditie} ===")
        print(f"ruisvloer ruwe microfoons: {stil:.2f} dBFS   {len(segs)} segmenten gevonden")
        if len(segs) > 20:
            print("  (de eerste 20 zijn de zinnen; de rest is overig geluid)")
        segs = segs[:20]
        print(f"{'nr':>3s} {'k0 ruis':>9s}{'k0 spraak':>10s}{'k0 SNR':>8s}"
              f"{'ruw ruis':>10s}{'ruw spr.':>10s}{'ruw SNR':>9s}   zin")
        print("-" * 98)
        for i, (a, b) in enumerate(segs):
            s0, s1 = int(a * SR), int(b * SR)
            r0 = max(0, int((a - RUIS_VOOR) * SR))
            spraak = {k: db(x[s0:s1, k]) for k in range(KANALEN)}
            ruis = {k: db(x[r0:s0, k]) for k in range(KANALEN)}
            rij = {"conditie": conditie, "nr": i + 1, "uiting_id": ids[i], "tekst": zinnen[i],
                   "start_s": round(a, 2), "eind_s": round(b, 2),
                   "k0_ruis": round(ruis[0], 2), "k0_spraak": round(spraak[0], 2),
                   "k0_snr": round(spraak[0] - ruis[0], 2),
                   "ruw_ruis": round(float(np.mean([ruis[k] for k in RUW])), 2),
                   "ruw_spraak": round(float(np.mean([spraak[k] for k in RUW])), 2),
                   "ruw_snr": round(float(np.mean([spraak[k] - ruis[k] for k in RUW])), 2)}
            alles.append(rij)
            print(f"{i + 1:3d} {rij['k0_ruis']:9.1f}{rij['k0_spraak']:10.1f}"
                  f"{rij['k0_snr']:8.1f}{rij['ruw_ruis']:10.1f}{rij['ruw_spraak']:10.1f}"
                  f"{rij['ruw_snr']:9.1f}   {zinnen[i][:28]}")
            with wave.open(str(doel / f"{conditie}_{ids[i]}.wav"), "wb") as o:
                o.setnchannels(KANALEN)
                o.setsampwidth(2)
                o.setframerate(SR)
                o.writeframes(x[max(0, s0 - int(0.3 * SR)):s1 + int(0.3 * SR)].tobytes())
        k0s = [r["k0_snr"] for r in alles if r["conditie"] == conditie]
        rws = [r["ruw_snr"] for r in alles if r["conditie"] == conditie]
        print("-" * 98)
        print(f"  GEMIDDELD  kanaal 0 {np.mean(k0s):6.2f} dB   "
              f"ruwe microfoons {np.mean(rws):6.2f} dB")

    if not alles:
        return
    log = map_ / "fluister_metingen.csv"
    with log.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(alles[0]))
        w.writeheader()
        w.writerows(alles)
    print(f"\n{len(alles)} metingen weggeschreven naar {log}")


def wer(map_: pathlib.Path) -> None:
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    with (map_ / "fluister_metingen.csv").open(newline="", encoding="utf-8") as fh:
        meting = {(r["conditie"], r["uiting_id"]): r for r in csv.DictReader(fh)}

    print(f"{'conditie':9s} {'kanaal':7s} {'WER gem.':>9s} {'mediaan':>8s} {'foutloos':>9s} "
          f"{'SNR':>8s}")
    print("-" * 62)
    detail = []
    for conditie in ("agc-aan", "gain-1"):
        for kanaal, naam in ((0, "k0"), (1, "ruw")):
            fouten, snrs = [], []
            for pad in sorted((map_ / "segmenten").glob(f"{conditie}_*.wav")):
                uid = pad.stem.split("_", 1)[1]
                m = meting.get((conditie, uid))
                if not m:
                    continue
                audio = lees(pad)[:, kanaal].astype(np.float32) / 32768.0
                hyp = " ".join(s.text.strip() for s in
                               model.transcribe(audio, language="nl", beam_size=5,
                                                vad_filter=False)[0]).strip()
                fouten.append(wer_pct(m["tekst"], hyp))
                snrs.append(float(m["k0_snr" if kanaal == 0 else "ruw_snr"]))
                if kanaal == 0:
                    detail.append((conditie, uid, m["tekst"], hyp, fouten[-1]))
            if not fouten:
                continue
            print(f"{conditie:9s} {naam:7s} {np.mean(fouten):8.2f} % {np.median(fouten):7.2f} % "
                  f"{sum(1 for f in fouten if f == 0):4d}/{len(fouten):<4d} "
                  f"{np.mean(snrs):6.2f} dB")

    print()
    print("TRANSCRIPTIES per uiting (kanaal 0, fabrieksstand)")
    print("=" * 96)
    for conditie, uid, ref, hyp, f in detail:
        if conditie != "agc-aan":
            continue
        print(f" {'    ' if f == 0 else f'{f:3.0f}%'} {uid:5s} {ref}")
        if f > 0:
            print(f"            -> {hyp}")


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    opdracht, map_ = sys.argv[1], pathlib.Path(sys.argv[2])
    if opdracht == "knippen":
        knippen(map_)
    elif opdracht == "wer":
        wer(map_)
    else:
        raise SystemExit(f"onbekende opdracht {opdracht!r}; kies knippen of wer")


if __name__ == "__main__":
    main()
