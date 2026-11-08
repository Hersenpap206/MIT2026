"""Meet hoe vaak de spraakdetectie in een stille kamer onterecht afgaat.

T4.2 (zie PLATFORM 2 par. 6b) meet hoe snel de detectie is en haalt de eis met factor zes. Maar
dat valse-alarmcijfer van 2,5 tot 25 % is gemeten op opnames met een seconde kamerstilte ervoor.
Voor een apparaat dat de hele nacht naast een bed staat is de relevante vraag een andere: hoe vaak
gaat de detectie af terwijl er niets gezegd wordt. Dat is het getal dat bepaalt of een
nachtverpleegkundige het apparaat aan laat staan.

Opzet: blokken van een minuut opnemen en elk blok met dezelfde detector beoordelen als T4.2, bij
meerdere instellingen tegelijk. Per blok wordt een regel weggeschreven; een blok met een detectie
wordt als WAV bewaard zodat achteraf te horen is wat de detectie veroorzaakte.

De opnames blijven op de lokale schijf en gaan nergens naartoe. Alleen blokken met een detectie
worden bewaard, de rest wordt weggegooid.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dialogue.vad_hybrid import detecteer_spraak_segmenten  # type: ignore

SR = 16000
# De vier instellingen uit de T4.2-reeks, zodat de cijfers vergelijkbaar zijn.
INSTELLINGEN = (
    ("or_250", {"rms_drempel": 250, "modus": "or"}),
    ("or_400", {"rms_drempel": 400, "modus": "or"}),
    ("or_600", {"rms_drempel": 600, "modus": "or"}),
    ("and_250", {"rms_drempel": 250, "modus": "and"}),
)


def samenvat(segmenten, samenvoeg_gat_s: float = 1.0):
    """Vat segmenten samen in: aantal segmenten, totale gemarkeerde tijd, aantal gebeurtenissen.

    Het aantal segmenten alleen is een misleidende maat. Een hogere RMS-drempel knipt een
    doorlopende detectie in losse stukjes, waardoor hij op meer segmenten uitkomt dan een lagere
    drempel - in de testrun gaf drempel 400 er 46 waar drempel 250 er 14 gaf. Voor de vraag "hoe
    vaak zou het apparaat wakker worden" zijn segmenten die minder dan een seconde uit elkaar
    liggen een gebeurtenis, en dat aantal is wel monotoon in de drempel.
    """
    if not segmenten:
        return 0, 0.0, 0
    totaal = sum(s.eind_s - s.start_s for s in segmenten)
    gebeurtenissen = 1
    vorige_eind = segmenten[0].eind_s
    for s in segmenten[1:]:
        if s.start_s - vorige_eind > samenvoeg_gat_s:
            gebeurtenissen += 1
        vorige_eind = s.eind_s
    return len(segmenten), round(totaal, 2), gebeurtenissen


def dbfs(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))
    return -999.0 if r <= 0 else 20.0 * np.log10(r / 32768.0)


def zoek_invoer(hint: str) -> int:
    for i, d in enumerate(sd.query_devices()):
        if hint.lower() in d["name"].lower() and d["max_input_channels"] > 0:
            return i
    raise SystemExit(f"geen invoerapparaat voor hint {hint!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uren", type=float, default=8.0)
    ap.add_argument("--blok-s", type=float, default=60.0)
    ap.add_argument("--start-om", default="", help="HH:MM; wacht tot dat tijdstip")
    ap.add_argument("--invoer-hint", default="ReSpeaker")
    ap.add_argument("--uit", default="D:/Loods WP3/nachtmeting")
    args = ap.parse_args()

    doel = Path(args.uit)
    (doel / "detecties").mkdir(parents=True, exist_ok=True)
    log = doel / f"nachtmeting_{datetime.now():%Y%m%d_%H%M}.csv"

    if args.start_om:
        u, m = (int(x) for x in args.start_om.split(":"))
        nu = datetime.now()
        start = nu.replace(hour=u, minute=m, second=0, microsecond=0)
        if start <= nu:
            start += timedelta(days=1)
        print(f"wachten tot {start:%Y-%m-%d %H:%M} ({(start - nu).total_seconds() / 60:.0f} min)",
              flush=True)
        time.sleep((start - nu).total_seconds())

    dev = zoek_invoer(args.invoer_hint)
    print(f"opnemen via {sd.query_devices(dev)['name'].strip()}", flush=True)
    print(f"{args.uren} uur in blokken van {args.blok_s:.0f} s; log: {log}", flush=True)

    velden = ["tijd", "blok", "rms_dbfs", "piek_dbfs"]
    for n, _ in INSTELLINGEN:
        velden += [f"{n}_segmenten", f"{n}_seconden", f"{n}_gebeurtenissen"]
    with log.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=velden)
        w.writeheader()
        fh.flush()

        einde = time.monotonic() + args.uren * 3600
        blok = 0
        while time.monotonic() < einde:
            blok += 1
            opname = sd.rec(int(args.blok_s * SR), samplerate=SR, channels=1,
                            dtype="int16", device=dev)
            sd.wait()
            tmp = doel / "_blok.wav"
            sf.write(str(tmp), opname, SR, subtype="PCM_16")

            rij = {"tijd": datetime.now().isoformat(timespec="seconds"), "blok": blok,
                   "rms_dbfs": round(dbfs(opname[:, 0]), 2),
                   "piek_dbfs": round(20 * np.log10(max(
                       float(np.max(np.abs(opname))) / 32768.0, 1e-9)), 2)}
            iets = False
            for naam, kw in INSTELLINGEN:
                n, sec, geb = samenvat(detecteer_spraak_segmenten(tmp, **kw))
                rij[f"{naam}_segmenten"] = n
                rij[f"{naam}_seconden"] = sec
                rij[f"{naam}_gebeurtenissen"] = geb
                iets = iets or n > 0
            w.writerow(rij)
            fh.flush()

            if iets:
                tmp.replace(doel / "detecties" / f"blok{blok:05d}_{datetime.now():%H%M%S}.wav")
            else:
                tmp.unlink(missing_ok=True)

            print(f"  blok {blok:4d} {rij['tijd'][11:]} {rij['rms_dbfs']:7.2f} dBFS  "
                  + "  ".join(f"{n}: {rij[f'{n}_gebeurtenissen']}x/{rij[f'{n}_seconden']:.0f}s"
                              for n, _ in INSTELLINGEN), flush=True)

    print(f"KLAAR na {blok} blokken; log: {log}", flush=True)


if __name__ == "__main__":
    main()
