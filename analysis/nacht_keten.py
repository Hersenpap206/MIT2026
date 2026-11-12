"""De volledige keten op echte nachtaudio: verzint het systeem een hulpvraag, en hoort het er een?

De spraakmetingen en de nachtmeting zijn tot nu toe gescheiden gebleven: de WER van 14,10 % komt
uit een stille kamer, de 840 valse detecties per uur uit een nacht zonder spraak. Dit script legt
ze op elkaar, in twee delen.

DEEL 1 - nachtruis zonder spraak. Wat komt er uit de spraakherkenning als er niets gezegd wordt?
Een lege transcriptie is goed nieuws; een verzonnen zin die de regelboom als hulpvraag leest, is
een vals alarm van de hele keten.

DEEL 2 - nachtruis met spraak. Elke opname van 1,0 m wordt gemengd met een willekeurig stuk echte
nachtruis, op de in de kamer gemeten verhouding: spraak 2,5 dB boven de achtergrond. De spraak
blijft ongewijzigd en de ruis wordt geschaald, zodat de schone meting de vergelijkingsbasis is.

Gemeten 12 november 2026, twaalf blokken van 60 s uit de nacht van 8 op 9 november (kanaal 0 van
de ReSpeaker, dus met AGC - dezelfde audio waarop de energiedrempel 1.968 spraaksegmenten vond):

  vosk, nachtruis zonder spraak            : 0 woorden, 0 alarmen, 0,13-0,28x realtime
  whisper small int8, zonder stiltefilter  : 15 verzonnen woorden in 1 van 12 blokken,
                                             0 alarmen, 0,30-1,43x realtime
  whisper small int8, met stiltefilter     : 0 woorden, 0 alarmen, 0,00-0,02x realtime

De meetmachine had geen engines geinstalleerd; vosk en faster-whisper zijn daar uit wheels in een
aparte map gedraaid. Op een machine met een gewone installatie werkt dit script zonder meer.

Gebruik:
    py -3.12 analysis/nacht_keten.py "D:/Loods WP3/nachtmeting/steekproef" \
        "D:/Loods WP3/lattepanda_pakket/corpus/opnames/gepaard"
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import wave

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from dialogue.dialogue_engine import REGELBOOM_NACHTZORG, besluit

SR = 16000
SNR_DB = 2.5          # in de kamer gemeten: spraak 2,5 dB boven de achtergrond
RNG = np.random.default_rng(20261112)
ALARMCATEGORIEEN = {"noodsituatie", "hulpvraag", "sociaal"}


def lees_wav(pad: pathlib.Path) -> np.ndarray:
    with wave.open(str(pad)) as w:
        ruw = w.readframes(w.getnframes())
    return np.frombuffer(ruw, dtype=np.int16).astype(np.float32) / 32768.0


def woorden(tekst: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", "", tekst.lower().replace("-", " ")).split()


def wer(referentie: str, hypothese: str) -> float:
    r, h = woorden(referentie), woorden(hypothese)
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=np.int32)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1,
                          d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / max(len(r), 1) * 100


def meng(spraak: np.ndarray, ruisblokken: list[np.ndarray]) -> np.ndarray:
    """Legt echte nachtruis onder een opname, op de gemeten verhouding."""
    blok = ruisblokken[RNG.integers(len(ruisblokken))]
    start = RNG.integers(0, len(blok) - len(spraak)) if len(blok) > len(spraak) else 0
    stuk = np.resize(blok[start:start + len(spraak)], len(spraak))
    rms_spraak = float(np.sqrt(np.mean(spraak ** 2))) + 1e-9
    doel = rms_spraak / (10 ** (SNR_DB / 20.0))
    stuk = stuk * (doel / (float(np.sqrt(np.mean(stuk ** 2))) + 1e-9))
    return np.clip(spraak + stuk, -1.0, 1.0)


def deel1_vosk(blokken: list[pathlib.Path], modelpad: str) -> None:
    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)
    model = Model(modelpad)
    print("DEEL 1a - vosk op nachtruis zonder spraak")
    print("=" * 80)
    alarmen = aantal_woorden = 0
    for pad in blokken:
        with wave.open(str(pad)) as w:
            herkenner = KaldiRecognizer(model, w.getframerate())
            start = time.perf_counter()
            stukken = []
            while True:
                data = w.readframes(4000)
                if not data:
                    break
                if herkenner.AcceptWaveform(data):
                    stukken.append(json.loads(herkenner.Result())["text"])
            stukken.append(json.loads(herkenner.FinalResult())["text"])
        tekst = " ".join(s for s in stukken if s)
        duur = (time.perf_counter() - start) / 60.0
        aantal_woorden += len(tekst.split())
        categorie = besluit(tekst, REGELBOOM_NACHTZORG).categorie if tekst else "(stil)"
        alarmen += categorie in ALARMCATEGORIEEN
        print(f"  {pad.stem:22s} {duur:5.2f}x  {categorie:14s} "
              f"{tekst[:34] if tekst else '(geen spraak herkend)'}")
    print(f"  -> {aantal_woorden} verzonnen woorden, {alarmen} alarmen in {len(blokken)} blokken")
    print()


def deel1_whisper(blokken: list[pathlib.Path], model) -> None:
    for stiltefilter in (False, True):
        naam = "met" if stiltefilter else "zonder"
        print(f"DEEL 1b - faster-whisper op nachtruis zonder spraak, {naam} stiltefilter")
        print("=" * 80)
        alarmen = aantal_woorden = 0
        for pad in blokken:
            audio = lees_wav(pad)
            start = time.perf_counter()
            segmenten, _ = model.transcribe(audio, language="nl", beam_size=5,
                                            vad_filter=stiltefilter)
            tekst = " ".join(s.text.strip() for s in segmenten).strip()
            duur = (time.perf_counter() - start) / (len(audio) / SR)
            aantal_woorden += len(tekst.split())
            categorie = besluit(tekst, REGELBOOM_NACHTZORG).categorie if tekst else "(stil)"
            alarmen += categorie in ALARMCATEGORIEEN
            print(f"  {pad.stem:22s} {duur:5.2f}x  {categorie:14s} "
                  f"{tekst[:34] if tekst else '(geen spraak herkend)'}")
        print(f"  -> {aantal_woorden} verzonnen woorden, {alarmen} alarmen "
              f"in {len(blokken)} blokken")
        print()


def deel2(opnamemap: pathlib.Path, blokken: list[pathlib.Path], model) -> None:
    import csv
    corpusmap = pathlib.Path(__file__).resolve().parents[1] / "corpus"
    referentie, stijl = {}, {}
    for setnaam in ("T2.2", "T2.2M"):
        with (corpusmap / f"bron_{setnaam}.csv").open(newline="", encoding="utf-8") as fh:
            for rij in csv.DictReader(fh):
                referentie[(setnaam, rij["uiting_id"])] = rij["tekst"]
                stijl[(setnaam, rij["uiting_id"])] = rij["categorie"]

    opnames = [(s, p) for s in ("T2.2", "T2.2M")
               for p in sorted((opnamemap / s / "d10").glob("*.wav"))]
    ruis = [lees_wav(p) for p in blokken]
    print(f"DEEL 2 - {len(opnames)} opnames van 1,0 m door de keten")
    print("=" * 80)

    for naam, met_ruis, stiltefilter in (("schoon (stille kamer)", False, False),
                                         ("met nachtruis, geen poort", True, False),
                                         ("met nachtruis + stiltefilter", True, True)):
        fouten, niets, acties, per_stijl = [], 0, {}, {}
        for setnaam, pad in opnames:
            audio = lees_wav(pad)
            if met_ruis:
                audio = meng(audio, ruis)
            segmenten, _ = model.transcribe(audio, language="nl", beam_size=5,
                                            vad_filter=stiltefilter)
            hypothese = " ".join(s.text.strip() for s in segmenten).strip()
            niets += not hypothese
            f = wer(referentie[(setnaam, pad.stem)], hypothese)
            fouten.append(f)
            per_stijl.setdefault(stijl[(setnaam, pad.stem)], []).append(f)
            if pad.stem[0] == "N":
                c = besluit(hypothese, REGELBOOM_NACHTZORG).categorie if hypothese else "(stil)"
                acties[c] = acties.get(c, 0) + 1
        print(f"  {naam}")
        print(f"    WER gemiddeld {np.mean(fouten):5.2f} %   mediaan {np.median(fouten):5.2f} %"
              f"   niets herkend: {niets}/{len(opnames)}")
        for k in sorted(per_stijl):
            print(f"       {k:12s} WER {np.mean(per_stijl[k]):5.2f} %")
        print(f"    de noodsituaties -> {acties}")
        print(flush=True)


def main() -> None:
    nachtmap = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                            else r"D:\Loods WP3\nachtmeting\steekproef")
    opnamemap = pathlib.Path(sys.argv[2] if len(sys.argv) > 2
                             else r"D:\Loods WP3\lattepanda_pakket\corpus\opnames\gepaard")
    voskmodel = sys.argv[3] if len(sys.argv) > 3 else None
    blokken = sorted(nachtmap.glob("*.wav"))
    print(f"{len(blokken)} nachtblokken uit {nachtmap}\n")

    if voskmodel:
        deel1_vosk(blokken, voskmodel)

    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    deel1_whisper(blokken, model)
    deel2(opnamemap, blokken, model)


if __name__ == "__main__":
    main()
