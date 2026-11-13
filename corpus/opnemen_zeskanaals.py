"""Neemt het corpus op over alle zes kanalen, om de werkelijke verhouding spraak/ruis te meten.

Waarom dit script er is. De meetnacht van 12 op 13 november liet zien dat kanaal 0 voor dezelfde
stille kamer een bereik van bijna 29 dB beslaat, afhankelijk van de stand van de AGC. Daarmee is
elke verhouding die uit kanaal 0 is afgeleid onbruikbaar, en dat was precies de 2,5 dB waarop de
WER-meting onder nachtruis rustte. De gevoeligheidscurve (analysis/kanaalnacht_analyse.py) laat
zien dat de eis van 25 % wordt gehaald vanaf ongeveer 7,5 dB. De openstaande vraag is dus niet of
de transcriptie werkt, maar hoeveel gefluisterde spraak werkelijk boven de nachtruis uitkomt.

Wat dit script anders doet dan opnemen_gepaard.py:

1. **Zes kanalen in plaats van een.** De ruwe microfoons (1 tot en met 4) hebben een constante
   versterking, dus daar is de verhouding wel betrouwbaar te meten.
2. **De voorloopstilte telt mee als meting.** Het stuk stilte vóór het afspelen is de ruisvloer,
   opgenomen in hetzelfde bestand en bij exact dezelfde versterking als de spraak erna. Dat is de
   vergelijking die op kanaal 0 niet te maken was, omdat achtergrond en spraak daar bij
   verschillende versterking zijn gemeten.
3. **Per AGC-conditie.** Zodat zichtbaar wordt hoeveel de regeling de verhouding vertekent.

LET OP - het afspeelniveau bepaalt de uitkomst. Een luidspreker die harder staat geeft een betere
verhouding; dat zegt niets over de werkelijkheid. Daarom eerst ijken: het niveau zo instellen dat
de spraak op kanaal 0 even hard binnenkomt als in de bestaande opnames van 8 november, want die
leverden de WER van 14,10 % waar alles op gebaseerd is. Pas daarna meten.

Gebruik (op het device met de ReSpeaker Mic Array v2.0):

    # 1. IJKEN: speelt een uiting in herhaling en toont het niveau tegen het doel.
    py -3.11 corpus/opnemen_zeskanaals.py ijken --mp3-map corpus/tts_bronnen/T2.2 \
        --referentie "D:/Loods WP3/lattepanda_pakket/corpus/opnames/gepaard/T2.2/d10"

    # 2. METEN: neemt het corpus op in twee AGC-condities.
    py -3.11 corpus/opnemen_zeskanaals.py meten --bron corpus/bron_T2.2.csv \
        --mp3-map corpus/tts_bronnen/T2.2 --uit ~/zeskanaals \
        --tuning ~/respeaker_tuning/tuning.py --categorie gefluisterd
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

OPNAME_SR = 16000
KANALEN = 6
BEWERKT = 0
RUW = (1, 2, 3, 4)

CONDITIES: dict[str, tuple[tuple[str, str], ...]] = {
    "agc-aan": (("AGCONOFF", "1"),),                       # fabrieksstand, zoals 8 november
    "gain-1": (("AGCONOFF", "0"), ("AGCGAIN", "1.0")),     # constante versterking
}


def dbfs(x: np.ndarray) -> float:
    """Niveau in dBFS. Let op de normalisatie: de opnames zijn int16, dus delen door 32768,
    anders komt het niveau 90,3 dB te hoog uit (zelfde vorm als in opnemen_gepaard.py)."""
    r = float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))
    return -999.0 if r <= 0 else 20.0 * np.log10(r / 32768.0)


def zoek_device(hint: str, invoer: bool) -> int:
    veld = "max_input_channels" if invoer else "max_output_channels"
    passend = [(i, d) for i, d in enumerate(sd.query_devices())
               if hint.lower() in d["name"].lower() and d[veld] > 0]
    if invoer:
        passend = [(i, d) for i, d in passend if d["max_input_channels"] >= KANALEN]
    if not passend:
        regels = "\n".join(f"  [{i}] {d['name'].strip()}  in={d['max_input_channels']} "
                           f"uit={d['max_output_channels']}"
                           for i, d in enumerate(sd.query_devices()))
        raise SystemExit(f"geen {'invoer' if invoer else 'uitvoer'}apparaat voor {hint!r}"
                         + (f" met {KANALEN} kanalen" if invoer else "") + f":\n{regels}")
    return passend[0][0]


def controleer_uitvoer(in_dev: int, out_dev: int, toch: bool) -> None:
    """Weigert afspelen via de ReSpeaker zelf, want dan sloopt de echo-onderdrukking de meting.

    De XVF-3000 doet akoestische echo-onderdrukking met het afspeelsignaal als referentie
    (kanaal 5 is die referentie). Speelt de luidspreker via datzelfde bord, dan herkent de DSP de
    uitgespeelde spraak als echo en haalt hij haar uit het microfoonsignaal - precies de spraak
    die we willen meten. De opnames van 8 november zijn afgespeeld via een los uitvoerapparaat,
    dus dat is ook de situatie die gereproduceerd moet worden.
    """
    in_naam = sd.query_devices(in_dev)["name"].strip()
    uit_naam = sd.query_devices(out_dev)["name"].strip()
    if in_naam.split(":")[0] != uit_naam.split(":")[0]:
        return
    melding = (
        f"\nAfspelen en opnemen zitten op hetzelfde apparaat: {uit_naam!r}.\n"
        "De echo-onderdrukking van de XVF-3000 zal de afgespeelde spraak dan uit het\n"
        "microfoonsignaal halen, en de meting is onbruikbaar.\n\n"
        "Gebruik een los uitvoerapparaat: een USB-geluidskaartje op de Pi, of voer deze sessie\n"
        "uit op een LattePanda met --uitvoer-hint Realtek, zoals op 8 november.\n"
        "Beschikbare uitvoerapparaten:\n"
        + "\n".join(f"  [{i}] {d['name'].strip()}" for i, d in enumerate(sd.query_devices())
                    if d["max_output_channels"] > 0))
    if not toch:
        raise SystemExit(melding + "\n\n(--toch-afspelen negeert deze controle)")
    print(melding + "\n\nGENEGEERD met --toch-afspelen; de uitkomst is niet te vertrouwen.\n",
          flush=True)


def aanloopstilte_s(mp3: Path) -> float:
    """Stilte aan het begin van de mp3, zodat het spraakvenster de spraak is en niet het bestand."""
    x, sr = sf.read(str(mp3), dtype="float32", always_2d=True)
    x = x[:, 0]
    drempel = max(float(np.max(np.abs(x))) * 0.02, 1e-4)
    boven = np.flatnonzero(np.abs(x) > drempel)
    return float(boven[0]) / sr if len(boven) else 0.0


def tuning_aanroep(tuning: Path, argumenten: list[str]):
    opdracht = [sys.executable, "-I", str(tuning), *argumenten]
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        opdracht = ["sudo", *opdracht]
    return subprocess.run(opdracht, capture_output=True, text=True, timeout=30)


def zet_conditie(tuning: Path | None, naam: str) -> str:
    if tuning is None:
        return "niet geregeld (geen --tuning)"
    for parameter, waarde in CONDITIES[naam]:
        uit = tuning_aanroep(tuning, [parameter, waarde])
        if uit.returncode != 0:
            return f"MISLUKT bij {parameter}: {uit.stderr.strip()[:60]}"
    return ", ".join(f"{p}={w}" for p, w in CONDITIES[naam])


def neem_op(mp3: Path, in_dev: int, out_dev: int, voorloop: float, naloop: float,
            demping_db: float = 0.0) -> tuple[np.ndarray, float]:
    """Speelt mp3 af en neemt gelijktijdig op over alle kanalen. Geeft (opname, onset) terug."""
    data, sr = sf.read(str(mp3), dtype="float32", always_2d=True)
    out_kanalen = sd.query_devices(out_dev)["max_output_channels"]
    if data.shape[1] == 1 and out_kanalen >= 2:
        data = np.repeat(data, 2, axis=1)
    data = data[:, :out_kanalen]
    if demping_db:
        data = data * (10.0 ** (-abs(demping_db) / 20.0))

    blokken: list[np.ndarray] = []

    def cb(indata, frames, tijd, status):      # noqa: ANN001, ARG001
        blokken.append(indata.copy())

    with sd.InputStream(samplerate=OPNAME_SR, channels=KANALEN, dtype="int16",
                        device=in_dev, callback=cb):
        t0 = time.monotonic()
        time.sleep(voorloop)
        onset = time.monotonic() - t0
        with sd.OutputStream(samplerate=sr, channels=out_kanalen, dtype="float32",
                             device=out_dev) as uit:
            uit.write(data)
        time.sleep(naloop)

    if not blokken:
        raise RuntimeError("geen audio opgenomen")
    return np.concatenate(blokken, axis=0), onset


def meet_niveaus(opname: np.ndarray, onset_s: float, aanloop_s: float,
                 marge_s: float = 0.15) -> dict:
    """Ruisvloer uit de voorloopstilte en spraakniveau uit het spraakvenster, per kanaal.

    Beide uit hetzelfde bestand, dus bij dezelfde stand van de versterking. Dat is precies wat
    op kanaal 0 niet te doen was toen achtergrond en spraak los van elkaar zijn gemeten.
    """
    start_spraak = int((onset_s + aanloop_s + marge_s) * OPNAME_SR)
    eind_stilte = max(int((onset_s - marge_s) * OPNAME_SR), 1)
    uit = {}
    for k in range(opname.shape[1]):
        ruis = dbfs(opname[:eind_stilte, k])
        spraak = dbfs(opname[start_spraak:, k])
        uit[k] = {"ruis": ruis, "spraak": spraak, "snr": spraak - ruis}
    return uit


def uitingen_uit_bron(bron: Path, mp3_map: Path | None, categorie: str | None,
                      alleen: int) -> list[tuple[str, Path | None, str, str]]:
    """Leest de uitingen uit het bronbestand. Zonder mp3-map (fluistermodus) vervalt de
    controle of er een geluidsbestand bij hoort."""
    rijen = []
    with bron.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if categorie and r["categorie"] != categorie:
                continue
            mp3 = None
            if mp3_map is not None:
                mp3 = mp3_map / f"{r['uiting_id']}.mp3"
                if not mp3.is_file():
                    print(f"  overgeslagen, geen mp3: {mp3}", flush=True)
                    continue
            rijen.append((r["uiting_id"], mp3, r["tekst"], r["categorie"]))
    return rijen[:alleen] if alleen else rijen


def doelniveau(referentiemap: Path) -> float:
    """Spraakniveau in de bestaande opnames van 1,0 m, als ijkpunt voor de luidspreker."""
    waarden = []
    for p in sorted(referentiemap.glob("*.wav")):
        x, sr = sf.read(str(p), dtype="float32", always_2d=True)
        kern = x[int(1.2 * sr):max(int(1.2 * sr) + 1, len(x) - int(0.5 * sr)), 0]
        if len(kern):
            waarden.append(dbfs(kern))
    if not waarden:
        raise SystemExit(f"geen referentieopnames in {referentiemap}")
    return float(np.mean(waarden))


def ijken(args) -> None:
    doel = doelniveau(Path(args.referentie))
    mp3s = sorted(Path(args.mp3_map).glob("*.mp3"))
    if not mp3s:
        raise SystemExit(f"geen mp3's in {args.mp3_map}")
    mp3 = mp3s[0]
    aanloop = aanloopstilte_s(mp3)
    in_dev = zoek_device(args.invoer_hint, True)
    out_dev = zoek_device(args.uitvoer_hint, False)
    controleer_uitvoer(in_dev, out_dev, args.toch_afspelen)
    print(f"invoer : {sd.query_devices(in_dev)['name'].strip()}")
    print(f"uitvoer: {sd.query_devices(out_dev)['name'].strip()}")
    print(f"uiting : {mp3.name}\n")
    print(f"DOEL op kanaal 0: {doel:.2f} dBFS "
          f"(gemiddeld spraakniveau in {Path(args.referentie).name})")
    print("Draai de luidspreker tot het gemeten niveau daar binnen 1 dB van zit. Ctrl-C stopt.\n")
    print(f"{'poging':>6s} {'kanaal 0':>10s} {'verschil':>9s} {'ruwe mics':>10s} {'SNR ruw':>8s}")
    print("-" * 52)
    poging = 0
    try:
        while True:
            poging += 1
            opname, onset = neem_op(mp3, in_dev, out_dev, args.voorloop, args.naloop,
                                    args.demping_db)
            n = meet_niveaus(opname, onset, aanloop)
            k0 = n[BEWERKT]["spraak"]
            ruw_spraak = float(np.mean([n[k]["spraak"] for k in RUW]))
            ruw_snr = float(np.mean([n[k]["snr"] for k in RUW]))
            vlag = "  <-- goed" if abs(k0 - doel) <= 1.0 else ""
            print(f"{poging:6d} {k0:9.2f} {k0 - doel:+8.2f} {ruw_spraak:10.2f} "
                  f"{ruw_snr:7.2f} dB{vlag}")
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\ngestopt")


def meten(args) -> None:
    uit = Path(args.uit).expanduser()
    uit.mkdir(parents=True, exist_ok=True)
    rijen = uitingen_uit_bron(Path(args.bron), Path(args.mp3_map), args.categorie, args.alleen)
    if not rijen:
        raise SystemExit("geen uitingen geselecteerd")
    in_dev = zoek_device(args.invoer_hint, True)
    out_dev = zoek_device(args.uitvoer_hint, False)
    controleer_uitvoer(in_dev, out_dev, args.toch_afspelen)
    condities = [c.strip() for c in args.condities.split(",") if c.strip()]
    print(f"invoer : {sd.query_devices(in_dev)['name'].strip()}")
    print(f"uitvoer: {sd.query_devices(out_dev)['name'].strip()}")
    print(f"{len(rijen)} uitingen x {len(condities)} condities\n", flush=True)

    log = uit / "zeskanaals_manifest.csv"
    velden = (["conditie", "uiting_id", "categorie", "referentietekst", "wav_path",
               "onset_s", "aanloop_s"]
              + [f"k{k}_{veld}" for k in range(KANALEN) for veld in ("ruis", "spraak", "snr")])
    with log.open("w", newline="", encoding="utf-8") as fh:
        schrijver = csv.DictWriter(fh, fieldnames=velden)
        schrijver.writeheader()
        for conditie in condities:
            stand = zet_conditie(Path(args.tuning) if args.tuning else None, conditie)
            print(f"=== {conditie} ({stand}) ===", flush=True)
            time.sleep(args.rust_s)        # de regeling laten inregelen
            snrs_ruw, snrs_k0 = [], []
            for uid, mp3, tekst, categorie in rijen:
                aanloop = aanloopstilte_s(mp3)
                opname, onset = neem_op(mp3, in_dev, out_dev, args.voorloop, args.naloop,
                                        args.demping_db)
                niveau = meet_niveaus(opname, onset, aanloop)
                naam = f"{conditie}_{uid}.wav"
                sf.write(str(uit / naam), opname, OPNAME_SR, subtype="PCM_16")
                rij = {"conditie": conditie, "uiting_id": uid, "categorie": categorie,
                       "referentietekst": tekst, "wav_path": naam,
                       "onset_s": round(onset, 3), "aanloop_s": round(aanloop, 3)}
                for k in range(KANALEN):
                    for veld in ("ruis", "spraak", "snr"):
                        rij[f"k{k}_{veld}"] = round(niveau[k][veld], 2)
                schrijver.writerow(rij)
                fh.flush()
                ruw_snr = float(np.mean([niveau[k]["snr"] for k in RUW]))
                snrs_ruw.append(ruw_snr)
                snrs_k0.append(niveau[BEWERKT]["snr"])
                print(f"  {uid:6s} {categorie:12s} k0 {niveau[BEWERKT]['snr']:6.2f} dB   "
                      f"ruw {ruw_snr:6.2f} dB", flush=True)
            print(f"  -> gemiddeld: kanaal 0 {np.mean(snrs_k0):.2f} dB, "
                  f"ruwe mics {np.mean(snrs_ruw):.2f} dB\n", flush=True)

    if args.tuning:
        print("fabrieksstand terugzetten:", zet_conditie(Path(args.tuning), "agc-aan"))
    print(f"KLAAR; manifest: {log}")
    print("Vervolg: analysis/nacht_keten.py of de WER-berekening per kanaal draaien, en de")
    print("gemeten verhouding leggen naast de curve uit analysis/kanaalnacht_analyse.py.")


def fluisteren(args) -> None:
    """Neemt een mens op die de corpuszinnen fluistert, in plaats van een luidspreker.

    Dit is de zuiverste vorm van de meting. Een luidspreker laat de uitkomst afhangen van de
    volumeknop; een mens die op 1,0 meter fluistert is het verschijnsel zelf. Bijkomend is dit
    de eerste meting in het project met een echte stem - alle bestaande opnames komen uit
    Edge TTS.
    """
    rijen = uitingen_uit_bron(Path(args.bron), None, args.categorie, args.alleen)
    if not rijen:
        raise SystemExit("geen uitingen geselecteerd")
    uit = Path(args.uit).expanduser()
    uit.mkdir(parents=True, exist_ok=True)
    in_dev = zoek_device(args.invoer_hint, True)
    condities = [c.strip() for c in args.condities.split(",") if c.strip()]

    print(f"opnemen via {sd.query_devices(in_dev)['name'].strip()}")
    print(f"{len(rijen)} zinnen x {len(condities)} condities\n")
    print("Ga op ongeveer 1,0 meter van de microfoon zitten en fluister de zin zoals een client")
    print("dat 's nachts zou doen. Tijdens 'stil' mag er geen geluid zijn: dat stuk is de")
    print("ruismeting. Na afloop kun je een opname overdoen met r.\n")

    log = uit / "fluister_manifest.csv"
    velden = (["conditie", "uiting_id", "categorie", "referentietekst", "wav_path"]
              + [f"k{k}_{veld}" for k in range(KANALEN) for veld in ("ruis", "spraak", "snr")])
    with log.open("w", newline="", encoding="utf-8") as fh:
        schrijver = csv.DictWriter(fh, fieldnames=velden)
        schrijver.writeheader()
        for conditie in condities:
            stand = zet_conditie(Path(args.tuning) if args.tuning else None, conditie)
            print(f"\n=== conditie {conditie} ({stand}) ===", flush=True)
            time.sleep(args.rust_s)
            snrs_ruw, snrs_k0 = [], []
            for nr, (uid, _mp3, tekst, categorie) in enumerate(rijen, 1):
                while True:
                    print(f"\n[{nr}/{len(rijen)}] {uid} ({categorie})")
                    print(f'    "{tekst}"')
                    input("    Enter = beginnen ")
                    print(f"    stil... ({args.voorloop:.0f} s)", flush=True)
                    opname = sd.rec(int((args.voorloop + args.spreek_s) * OPNAME_SR),
                                    samplerate=OPNAME_SR, channels=KANALEN,
                                    dtype="int16", device=in_dev)
                    time.sleep(args.voorloop)
                    print(f"    >>> FLUISTER NU <<<  ({args.spreek_s:.0f} s)", flush=True)
                    sd.wait()

                    niveau = meet_niveaus(opname, args.voorloop, 0.0, marge_s=0.2)
                    ruw_snr = float(np.mean([niveau[k]["snr"] for k in RUW]))
                    ruw_ruis = float(np.mean([niveau[k]["ruis"] for k in RUW]))
                    afwijking = abs(ruw_ruis - args.ruis_referentie)
                    vlag = "" if afwijking <= 3.0 else f"  LET OP: ruisvloer wijkt {afwijking:.1f} dB af"
                    print(f"    kanaal 0 SNR {niveau[BEWERKT]['snr']:6.2f} dB   "
                          f"ruw {ruw_snr:6.2f} dB   ruisvloer ruw {ruw_ruis:6.2f} dBFS{vlag}")
                    if input("    Enter = goed, r = overdoen ").strip().lower() != "r":
                        break

                naam = f"{conditie}_{uid}.wav"
                sf.write(str(uit / naam), opname, OPNAME_SR, subtype="PCM_16")
                rij = {"conditie": conditie, "uiting_id": uid, "categorie": categorie,
                       "referentietekst": tekst, "wav_path": naam}
                for k in range(KANALEN):
                    for veld in ("ruis", "spraak", "snr"):
                        rij[f"k{k}_{veld}"] = round(niveau[k][veld], 2)
                schrijver.writerow(rij)
                fh.flush()
                snrs_ruw.append(ruw_snr)
                snrs_k0.append(niveau[BEWERKT]["snr"])

            print(f"\n  -> {conditie}: kanaal 0 {np.mean(snrs_k0):.2f} dB, "
                  f"ruwe microfoons {np.mean(snrs_ruw):.2f} dB", flush=True)

    if args.tuning:
        print("\nfabrieksstand terugzetten:", zet_conditie(Path(args.tuning), "agc-aan"))
    print(f"KLAAR; manifest: {log}")
    print("\nDe ruwe microfoons geven het eerlijke getal, want daar is de versterking constant.")
    print("Ligt dat op of boven 7,5 dB, dan haalt de transcriptie de eis van 25 % WER")
    print("(zie de curve in analysis/kanaalnacht_analyse.py).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="opdracht", required=True)

    gemeenschappelijk = {
        "--voorloop": dict(type=float, default=2.0,
                           help="stilte vóór het afspelen; dit is de ruismeting"),
        "--naloop": dict(type=float, default=0.8),
        "--invoer-hint": dict(default="ReSpeaker"),
        "--uitvoer-hint": dict(default="Realtek"),
        "--demping-db": dict(type=float, default=0.0,
                             help="afspelen zachter zetten, in dB"),
        "--toch-afspelen": dict(action="store_true",
                                help="negeer de controle op echo-onderdrukking"),
    }

    pi = sub.add_parser("ijken", help="luidsprekerniveau afstellen op de bestaande opnames")
    pi.add_argument("--mp3-map", required=True)
    pi.add_argument("--referentie", required=True,
                    help="map met de bestaande opnames van 1,0 m")

    pm = sub.add_parser("meten", help="het corpus opnemen over zes kanalen")
    pm.add_argument("--bron", required=True)
    pm.add_argument("--mp3-map", required=True)
    pm.add_argument("--uit", default="opnames/zeskanaals")
    pm.add_argument("--tuning", default=None, help="pad naar tuning.py")
    pm.add_argument("--condities", default="agc-aan,gain-1")
    pm.add_argument("--categorie", default=None,
                    help="beperk tot een spreekstijl, bv. gefluisterd")
    pm.add_argument("--alleen", type=int, default=0, help="eerste N uitingen (proefrun)")
    pm.add_argument("--rust-s", type=float, default=5.0,
                    help="wachttijd na het wisselen van conditie")

    pf = sub.add_parser("fluisteren",
                        help="een mens opnemen die de zinnen fluistert (geen luidspreker)")
    pf.add_argument("--bron", required=True)
    pf.add_argument("--uit", default="opnames/fluister")
    pf.add_argument("--tuning", default=None, help="pad naar tuning.py")
    pf.add_argument("--condities", default="agc-aan,gain-1")
    pf.add_argument("--categorie", default=None, help="bv. gefluisterd")
    pf.add_argument("--alleen", type=int, default=0, help="eerste N zinnen (proefrun)")
    pf.add_argument("--spreek-s", type=float, default=5.0, help="opnametijd voor de zin")
    pf.add_argument("--rust-s", type=float, default=5.0)
    pf.add_argument("--ruis-referentie", type=float, default=-60.7,
                    help="ruisvloer op de ruwe microfoons in de meetnacht van 12-13 november; "
                         "wijkt de meting daar ver vanaf, dan is de kamer niet op nachtniveau")

    for p in (pi, pm, pf):
        for vlag, opties in gemeenschappelijk.items():
            if vlag in ("--uitvoer-hint", "--demping-db", "--toch-afspelen",
                        "--naloop") and p is pf:
                continue           # die gelden alleen bij afspelen
            p.add_argument(vlag, **opties)

    args = ap.parse_args()
    {"ijken": ijken, "meten": meten, "fluisteren": fluisteren}[args.opdracht](args)


if __name__ == "__main__":
    main()
