"""Voortoets: is gefluisterde spraak op signaalinhoud te scheiden van het nachtgeluid?

De nachtmeting liet zien dat het achtergrondgeluid in een lege kamer op 2,5 dB van gefluisterde
spraak ligt (PLATFORM 2 par. 6b-bis). Met een energiedrempel is dat niet te scheiden, op geen
enkel microfoonkanaal. De vraag is dan of de *inhoud* van het signaal het verschil wel draagt -
want dat is wat een classificatie op een NPU zou doen (PLATFORM 3 par. 3e).

Opzet. Bewust de eenvoudigst denkbare classificatie: logistische regressie op log-mel-kenmerken,
met de hand geschreven in numpy. Lukt het daarmee, dan lukt het een convolutienetwerk zeker, en is
de uitkomst dus een ondergrens. Lukt het niet, dan is er niets bewezen - een CNN kan dan alsnog
slagen.

**Eerste opzet verworpen.** Aanvankelijk werd spraak uit de testruimte vergeleken met nachtgeluid
uit de slaapkamer. De controle liet zien dat het model dan de *opnamesessie* leert: 97,5 % van de
aanloopstilte van de spraakopnames werd ook als spraak aangemerkt. Twee klassen uit twee
verschillende ruimtes op twee momenten zijn nu eenmaal langs tientallen wegen te onderscheiden die
niets met spraak te maken hebben.

**Huidige opzet: mengen.** Beide klassen krijgen exact dezelfde achtergrond. Van elk nachtvenster
wordt de helft gebruikt zoals het is (geen spraak) en de andere helft met een gefluisterde uiting
erdoorheen gemengd, geschaald op de verhouding die in de kamer is gemeten: spraak 2,5 dB boven het
achtergrondgeluid. Daarmee is de vraag zuiver - kan de inhoud van het signaal spraak aanwijzen die
in dit geluid verstopt zit - en meet de toets precies de situatie waar het om gaat.

Drie dingen zijn met zorg gedaan, omdat de uitkomst anders te mooi wordt:

1. **Splitsen op bestand, niet op venster.** Vensters uit hetzelfde bestand lijken op elkaar;
   zouden ze over train en test verdeeld raken, dan meet de toets geheugen in plaats van kunde.
2. **Splitsen op bron, aan beide kanten.** Een nachtblok en een spraakopname komen elk maar in
   train of in test voor, nooit in allebei.
3. **Gefluisterd apart beoordeeld**, want dat is de categorie waar het om gaat.

Gebruik (vanuit scripts/):
    py -3.12 analysis/voortoets_detectie.py <spraakmap> <nachtmap> <manifestmap> [snr_db]
"""

from __future__ import annotations

import csv
import sys
import wave
from pathlib import Path

import numpy as np

SR = 16000
VENSTER_S = 1.0          # beslisvenster: hoe lang mag de detector luisteren
FFT_N = 512              # 32 ms bij 16 kHz
HOP = 160                # 10 ms
N_MEL = 32
RNG = np.random.default_rng(20261111)


# ---------------------------------------------------------------- audio inlezen

def lees_wav(pad: Path) -> np.ndarray:
    with wave.open(str(pad), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"{pad.name}: verwacht 16-bits PCM")
        ruw = wf.readframes(wf.getnframes())
        x = np.frombuffer(ruw, dtype="<i2").astype(np.float32) / 32768.0
        if wf.getnchannels() > 1:
            x = x.reshape(-1, wf.getnchannels())[:, 0]
        if wf.getframerate() != SR:
            raise ValueError(f"{pad.name}: {wf.getframerate()} Hz, verwacht {SR}")
    return x


# ------------------------------------------------------------------- kenmerken

def mel_filterbank(n_mel: int, fft_n: int, sr: int) -> np.ndarray:
    """Driehoekige mel-filters, zoals een MFE-blok ze gebruikt."""
    def hz_naar_mel(f): return 2595.0 * np.log10(1.0 + f / 700.0)
    def mel_naar_hz(m): return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    randen = mel_naar_hz(np.linspace(hz_naar_mel(60), hz_naar_mel(sr / 2), n_mel + 2))
    bins = np.floor((fft_n + 1) * randen / sr).astype(int)
    fb = np.zeros((n_mel, fft_n // 2 + 1), dtype=np.float32)
    for i in range(n_mel):
        l, m, r = bins[i], bins[i + 1], bins[i + 2]
        if m == l: m = l + 1
        if r == m: r = m + 1
        r = min(r, fb.shape[1] - 1)
        if m >= fb.shape[1]: break
        fb[i, l:m] = np.linspace(0, 1, m - l, endpoint=False)
        fb[i, m:r] = np.linspace(1, 0, r - m, endpoint=False)
    return fb


FB = mel_filterbank(N_MEL, FFT_N, SR)
RAAM = np.hanning(FFT_N).astype(np.float32)


def logmel(x: np.ndarray) -> np.ndarray:
    """Log-mel-energie per tijdstap: (frames, N_MEL)."""
    n = 1 + max(0, (len(x) - FFT_N) // HOP)
    if n < 1:
        return np.zeros((0, N_MEL), dtype=np.float32)
    idx = np.arange(FFT_N)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * RAAM
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    return np.log(spec @ FB.T + 1e-10).astype(np.float32)


def kenmerken(x: np.ndarray) -> np.ndarray:
    """Per beslisvenster: gemiddelde en spreiding van elke mel-band.

    Het gemiddelde vangt de spectrale vorm; de spreiding vangt de modulatie. Spraak wordt sterk
    gemoduleerd, een machine loopt gelijkmatig - dat verschil zit juist in die tweede helft.
    """
    per_venster = int(VENSTER_S * SR)
    uit = []
    for s in range(0, len(x) - per_venster + 1, per_venster):
        lm = logmel(x[s:s + per_venster])
        if len(lm) < 4:
            continue
        uit.append(np.concatenate([lm.mean(axis=0), lm.std(axis=0)]))
    return np.array(uit, dtype=np.float32) if uit else np.zeros((0, 2 * N_MEL), dtype=np.float32)


# --------------------------------------------------------- logistische regressie

def train(X, y, stappen=4000, lr=0.25, l2=1e-3):
    X = np.hstack([X, np.ones((len(X), 1), dtype=np.float32)])
    w = np.zeros(X.shape[1], dtype=np.float32)
    # klassen wegen zodat de grootste klasse het model niet overheerst
    gew = np.where(y == 1, len(y) / (2 * max(y.sum(), 1)),
                   len(y) / (2 * max((1 - y).sum(), 1))).astype(np.float32)
    for _ in range(stappen):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        grad = X.T @ (gew * (p - y)) / len(y) + l2 * w
        w -= lr * grad
    return w


def voorspel(X, w):
    X = np.hstack([X, np.ones((len(X), 1), dtype=np.float32)])
    return 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))


# ------------------------------------------------------------------------ main

def laad_spraak(spraakmappen, manifestmap):
    """Spraakfragmenten van 1 seconde, met hun categorie en bronbestand."""
    meta = {}
    for naam in ("T2.2", "T2.2M"):
        m = manifestmap / f"{naam}_gepaard_d10_manifest.csv"
        if not m.is_file():
            continue
        with open(m, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                meta[(naam, r["uiting_id"])] = (r.get("categorie", ""),
                                                float(r.get("onset_verwacht_s", 1.0)))
    frag, cat, bron = [], [], []
    per = int(VENSTER_S * SR)
    for map_ in spraakmappen:
        setnaam = map_.parts[-2]
        for wav in sorted(map_.glob("*.wav")):
            c, onset = meta.get((setnaam, wav.stem), ("onbekend", 1.0))
            x = lees_wav(wav)
            kern = x[int(onset * SR):max(int(onset * SR), len(x) - int(0.5 * SR))]
            for s in range(0, len(kern) - per + 1, per // 2):   # halve overlap
                stuk = kern[s:s + per]
                if np.sqrt(np.mean(stuk ** 2)) < 1e-4:          # stille staart overslaan
                    continue
                frag.append(stuk); cat.append(c); bron.append(f"{setnaam}/{wav.stem}")
    return frag, np.array(cat), np.array(bron)


def bouw(nachtmap, frag, cat, bron, snr_db):
    """Maakt twee klassen met exact dezelfde achtergrond: ruis, en ruis met spraak erdoorheen."""
    per = int(VENSTER_S * SR)
    X, y, groep_nacht, groep_spraak, categorie = [], [], [], [], []
    idx = RNG.permutation(len(frag))
    teller = 0
    for wav in sorted(nachtmap.glob("*.wav")):
        ruis = lees_wav(wav)
        for s in range(0, len(ruis) - per + 1, per):
            venster = ruis[s:s + per]
            rms_r = float(np.sqrt(np.mean(venster ** 2))) + 1e-9
            if teller % 2 == 0:                      # klasse 0: alleen achtergrond
                X.append(kenmerken_van(venster)); y.append(0)
                groep_nacht.append(wav.stem); groep_spraak.append(""); categorie.append("-")
            else:                                    # klasse 1: achtergrond plus spraak
                j = idx[(teller // 2) % len(idx)]
                sp = frag[j]
                rms_s = float(np.sqrt(np.mean(sp ** 2))) + 1e-9
                schaal = (rms_r * 10 ** (snr_db / 20.0)) / rms_s
                gemengd = np.clip(venster + sp * schaal, -1.0, 1.0)
                X.append(kenmerken_van(gemengd)); y.append(1)
                groep_nacht.append(wav.stem); groep_spraak.append(bron[j]); categorie.append(cat[j])
            teller += 1
    return (np.array(X, dtype=np.float32), np.array(y, dtype=np.float32),
            np.array(groep_nacht), np.array(groep_spraak), np.array(categorie))


def kenmerken_van(x):
    lm = logmel(x)
    return np.concatenate([lm.mean(axis=0), lm.std(axis=0)]).astype(np.float32)


def main() -> None:
    spraakmappen = [Path(sys.argv[1]) / "T2.2" / "d10", Path(sys.argv[1]) / "T2.2M" / "d10"]
    nachtmap = Path(sys.argv[2])
    manifestmap = Path(sys.argv[3])
    snrs = [float(a) for a in sys.argv[4:]] or [2.5]

    frag, cat, bron = laad_spraak(spraakmappen, manifestmap)
    print(f"spraakfragmenten van {VENSTER_S:.0f} s: {len(frag)} uit {len(set(bron))} opnames")
    print(f"nachtblokken: {len(list(nachtmap.glob('*.wav')))}")
    print()
    print("De spraak wordt door het nachtgeluid gemengd, zodat beide klassen exact dezelfde")
    print("achtergrond hebben. 2,5 dB is de in de kamer gemeten verhouding.")
    print()

    for snr in snrs:
        X, y, g_nacht, g_spraak, categorie = bouw(nachtmap, frag, cat, bron, snr)
        blokken = sorted(set(g_nacht)); opnames = sorted(set(b for b in g_spraak if b))
        RNG.shuffle(blokken); RNG.shuffle(opnames)
        test_blok = set(blokken[:max(1, len(blokken) // 3)])
        test_opn = set(opnames[:len(opnames) // 3])
        # een venster hoort bij test als zijn nachtblok OF zijn spraakopname in de testset zit
        is_test = np.isin(g_nacht, list(test_blok)) | np.array(
            [b in test_opn for b in g_spraak])
        tr, te = ~is_test, is_test

        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
        w = train((X[tr] - mu) / sd, y[tr])
        p = voorspel((X[te] - mu) / sd, w)

        spraak, ruis = p[y[te] == 1], p[y[te] == 0]
        print(f"=== spraak {snr:+.1f} dB boven het achtergrondgeluid ===")
        print(f"  getraind op {tr.sum()} vensters, getest op {te.sum()}")
        for drempel in (0.5, 0.9):
            print(f"    drempel {drempel:3.1f}:  spraak herkend {(spraak >= drempel).mean()*100:5.1f} %"
                  f"   vals alarm {(ruis >= drempel).mean()*100:5.1f} %")
        ct = categorie[te][y[te] == 1]
        for c in sorted(set(ct)):
            sel = ct == c
            if sel.sum() > 3:
                print(f"      {c:12s} n={sel.sum():4d}  herkend {(spraak[sel] >= 0.5).mean()*100:5.1f} %")
        print()


if __name__ == "__main__":
    main()
