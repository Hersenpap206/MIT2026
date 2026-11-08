"""Neemt het testcorpus gepaard op: dezelfde uitingen op elke afstand.

Waarom gepaard. In bron_T2.2.csv kreeg elke afstand andere uitingen - 1,5 m de gefluisterde
variant, 2,5 m de emotionele, 4,0 m de incomplete. De variatie tussen uitingen is met een
standaardafwijking van 28,1 procentpunt veel groter dan het effect van afstand, waardoor de
afstandsreeks van 8 november geen afstandseffect kon aantonen (zie PLATFORM 2 par. 2b). Door
dezelfde uitingen op elke afstand op te nemen valt die variatie volledig weg.

Bijkomend resultaat: het moment waarop het afspelen begint wordt per opname vastgelegd als
onset_verwacht_s. Daarmee levert deze sessie tevens het manifest voor T4.2 (VAD-detectielatentie),
dat tot nu toe handmatige annotatie vergde en daarom nooit is uitgevoerd.

Opzet per uiting: opname starten, voorloopstilte, mp3 via de speaker afspelen, nalooopstilte,
opslaan. Afspelen en opnemen gebruiken expliciete streams; de gemaksfuncties sd.play en sd.rec
delen intern een stream en zouden elkaar afbreken.

Gebruik (vanuit de repo-root, op het device met de ReSpeaker):
    python corpus/opnemen_gepaard.py --bron corpus/bron_T2.2.csv --mp3-map corpus/tts_bronnen/T2.2 --afstand-m 1.5
    python corpus/opnemen_gepaard.py --bron corpus/bron_T2.2.csv --mp3-map corpus/tts_bronnen/T2.2 --afstand-m 1.5 --alleen 2   (proefrun)
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

OPNAME_SR = 16000
RMS_DREMPEL_DBFS = -45.0


def dbfs(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))
    return -999.0 if r <= 0 else 20.0 * np.log10(r / 32768.0)


def zoek_device(hint: str, invoer: bool) -> int:
    veld = "max_input_channels" if invoer else "max_output_channels"
    for i, d in enumerate(sd.query_devices()):
        if hint.lower() in d["name"].lower() and d[veld] > 0:
            return i
    raise SystemExit(f"geen {'invoer' if invoer else 'uitvoer'}apparaat gevonden voor hint {hint!r}")


def neem_op(mp3: Path, in_dev: int, out_dev: int, voorloop: float, naloop: float):
    """Speelt mp3 af en neemt gelijktijdig op. Geeft (opname, onset_s) terug."""
    data, sr = sf.read(str(mp3), dtype="float32", always_2d=True)
    out_kanalen = sd.query_devices(out_dev)["max_output_channels"]
    if data.shape[1] == 1 and out_kanalen >= 2:
        data = np.repeat(data, 2, axis=1)
    data = data[:, :out_kanalen]

    blokken = []
    def cb(indata, frames, tijd, status):
        blokken.append(indata.copy())

    with sd.InputStream(samplerate=OPNAME_SR, channels=1, dtype="int16",
                        device=in_dev, callback=cb):
        t_start = time.monotonic()
        time.sleep(voorloop)
        onset = time.monotonic() - t_start
        with sd.OutputStream(samplerate=sr, channels=out_kanalen,
                             dtype="float32", device=out_dev) as uit:
            uit.write(data)
        time.sleep(naloop)

    if not blokken:
        raise RuntimeError("geen audio opgenomen")
    return np.concatenate(blokken, axis=0), onset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bron", required=True)
    ap.add_argument("--mp3-map", required=True)
    ap.add_argument("--afstand-m", required=True, type=float)
    ap.add_argument("--uit", default="corpus/opnames/gepaard")
    ap.add_argument("--voorloop", type=float, default=1.0)
    ap.add_argument("--naloop", type=float, default=0.8)
    ap.add_argument("--invoer-hint", default="ReSpeaker")
    ap.add_argument("--uitvoer-hint", default="Realtek")
    ap.add_argument("--alleen", type=int, default=0, help="beperk tot de eerste N uitingen (proefrun)")
    args = ap.parse_args()

    in_dev = zoek_device(args.invoer_hint, invoer=True)
    out_dev = zoek_device(args.uitvoer_hint, invoer=False)
    print(f"opnemen via  : {sd.query_devices(in_dev)['name'].strip()}")
    print(f"afspelen via : {sd.query_devices(out_dev)['name'].strip()}")

    code = "d" + f"{args.afstand_m:.1f}".replace(".", "")
    doel = Path(args.uit) / code
    doel.mkdir(parents=True, exist_ok=True)

    with open(args.bron, newline="", encoding="utf-8") as fh:
        rijen = list(csv.DictReader(fh))
    if args.alleen:
        rijen = rijen[:args.alleen]
    print(f"{len(rijen)} uitingen op {args.afstand_m} m naar {doel}")
    print()

    manifest, stil = [], []
    for n, rij in enumerate(rijen, 1):
        uid = rij["uiting_id"]
        mp3 = Path(args.mp3_map) / f"{uid}.mp3"
        if not mp3.is_file():
            print(f"  {n:3d}/{len(rijen)} {uid:8s} mp3 ONTBREEKT - overgeslagen")
            continue
        opname, onset = neem_op(mp3, in_dev, out_dev, args.voorloop, args.naloop)
        wav = doel / f"{uid}.wav"
        sf.write(str(wav), opname, OPNAME_SR, subtype="PCM_16")
        niveau = dbfs(opname)
        vlag = ""
        if niveau < RMS_DREMPEL_DBFS:
            vlag = "  << TE STIL"
            stil.append(uid)
        print(f"  {n:3d}/{len(rijen)} {uid:8s} {len(opname)/OPNAME_SR:5.2f}s  "
              f"{niveau:7.2f} dBFS  onset {onset:.3f}s{vlag}")
        manifest.append({
            "uiting_id": uid,
            "wav_path": f"opnames/gepaard/{code}/{uid}.wav",
            "referentietekst": rij["tekst"],
            "categorie": rij.get("categorie", ""),
            "afstand_m": f"{args.afstand_m}",
            "onset_verwacht_s": f"{onset:.3f}",
        })

    if not manifest:
        raise SystemExit("niets opgenomen")

    naam = Path(args.bron).stem.replace("bron_", "")
    mpad = Path(f"corpus/{naam}_gepaard_{code}_manifest.csv")
    with open(mpad, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0].keys()))
        w.writeheader()
        w.writerows(manifest)

    print()
    print(f"manifest: {mpad} ({len(manifest)} regels)")
    if stil:
        print()
        print(f"WAARSCHUWING: {len(stil)} opname(s) onder {RMS_DREMPEL_DBFS} dBFS: {', '.join(stil[:8])}")
        print("Staat de speaker aan en op de juiste uitgang? Een te stille opname meet niets.")
        sys.exit(1)


if __name__ == "__main__":
    main()
