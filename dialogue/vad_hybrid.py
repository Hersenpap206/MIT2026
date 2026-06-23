"""
Hybride VAD (Voice Activity Detection) — testplan T4.2: "betrouwbaar onderscheid spraak/stilte
in een stille nachtzorg-omgeving, inclusief gefluisterde uitingen".

Waarom hybride: pure energie-thresholding geeft valse positieven op omgevingsgeluid (bv. een
zacht zoemend apparaat) en pure WebRTC-VAD (ontworpen voor telefonie/normale spraakniveaus) mist
soms zachte/gefluisterde uitingen in een stille kamer. Dit script combineert beide:
    1. WebRTC-VAD (agressiviteitsniveau instelbaar, --aggressiveness 0-3) als primaire detector.
    2. Een laagdrempelige RMS-energiecheck als tweede stem — een frame geldt als spraak zodra
       BEIDE detectors het oneens zijn vermijden we niet automatisch fout-negatieven, dus
       standaard telt een frame als spraak bij een logische OF (WebRTC-VAD-positief OF
       RMS boven --rms-drempel) om gefluister niet te missen; pas --modus aan naar 'and' voor een
       striktere/conservatievere detectie (minder valse positieven, risico op missen van gefluister).

Verwerkt WAV-bestanden (16-bit PCM, mono, 16kHz — conform MIC_SAMPLE_RATE_HZ in common/config.py;
WebRTC-VAD ondersteunt alleen 8/16/32/48kHz) in vaste frames van 30ms.

Gebruik (analyseer één bestand, print segmenten):
    python vad_hybrid.py --wav opname.wav

Gebruik (testcorpus met verwachte spraakstart, gelogde detectielatentie):
    python vad_hybrid.py --manifest corpus/T4.2_manifest.csv --test-id T4.2
"""

from __future__ import annotations

import argparse
import array
import csv
import math
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.logging_utils import TestLogger

try:
    import webrtcvad
except ImportError as exc:  # pragma: no cover
    raise ImportError("webrtcvad ontbreekt — installeer met: pip install webrtcvad") from exc

FRAME_DUUR_MS = 30  # WebRTC-VAD vereist 10/20/30ms-frames


@dataclass(frozen=True)
class Segment:
    start_s: float
    eind_s: float


def _rms_van_frame(frame: bytes) -> float:
    """RMS van 16-bit PCM-samples, zonder de in Python 3.13+ verwijderde `audioop`-module."""
    samples = array.array("h")  # signed 16-bit
    samples.frombytes(frame)
    if not samples:
        return 0.0
    kwadraatsom = sum(s * s for s in samples)
    return math.sqrt(kwadraatsom / len(samples))


def detecteer_spraak_segmenten(
    wav_path: str | Path,
    aggressiveness: int = 2,
    rms_drempel: int = 250,
    modus: str = "or",
) -> list[Segment]:
    """Leest het WAV-bestand frame-voor-frame en geeft een lijst spraaksegmenten terug."""
    vad = webrtcvad.Vad(aggressiveness)

    with wave.open(str(wav_path), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError(f"{wav_path}: vereist mono 16-bit PCM, kreeg "
                              f"{wf.getnchannels()}ch/{wf.getsampwidth() * 8}bit")
        samplerate = wf.getframerate()
        if samplerate not in (8000, 16000, 32000, 48000):
            raise ValueError(f"{wav_path}: samplerate {samplerate}Hz niet ondersteund door WebRTC-VAD")

        frame_len = int(samplerate * FRAME_DUUR_MS / 1000)
        frame_bytes = frame_len * 2  # 16-bit = 2 bytes/sample

        segmenten: list[Segment] = []
        in_segment = False
        segment_start_s = 0.0
        frame_idx = 0

        while True:
            data = wf.readframes(frame_len)
            if len(data) < frame_bytes:
                break

            webrtc_spraak = vad.is_speech(data, samplerate)
            rms_spraak = _rms_van_frame(data) > rms_drempel
            is_spraak = (webrtc_spraak or rms_spraak) if modus == "or" else (webrtc_spraak and rms_spraak)

            t_s = frame_idx * FRAME_DUUR_MS / 1000
            if is_spraak and not in_segment:
                in_segment = True
                segment_start_s = t_s
            elif not is_spraak and in_segment:
                in_segment = False
                segmenten.append(Segment(segment_start_s, t_s))

            frame_idx += 1

        if in_segment:
            segmenten.append(Segment(segment_start_s, frame_idx * FRAME_DUUR_MS / 1000))

    return segmenten


def run_corpus(
    manifest_path: str | Path,
    test_id: str,
    fase: str = "vad_detectie",
    aggressiveness: int = 2,
    rms_drempel: int = 250,
    modus: str = "or",
) -> None:
    """Manifest-CSV: uiting_id,wav_path,onset_verwacht_s — onset_verwacht_s is het moment (in
    seconden vanaf het begin van de opname) waarop de spraak daadwerkelijk begint (handmatig
    geannoteerd vooraf). detectielatentie_ms = (gedetecteerde_start - onset_verwacht) * 1000."""
    manifest_path = Path(manifest_path)

    with TestLogger(test_id=test_id, fase=fase) as logger, manifest_path.open(encoding="utf-8") as fh:
        for rij in csv.DictReader(fh):
            wav_path = manifest_path.parent / rij["wav_path"]
            onset_verwacht_s = float(rij["onset_verwacht_s"])

            segmenten = detecteer_spraak_segmenten(wav_path, aggressiveness, rms_drempel, modus)
            eerste_segment = next((s for s in segmenten if s.eind_s > onset_verwacht_s), None)

            if eerste_segment is None:
                detectielatentie_ms = float("nan")  # gemiste detectie -> telt mee als FRR-achtig geval
                opmerking = "GEEN_SEGMENT_GEDETECTEERD"
            else:
                detectielatentie_ms = (eerste_segment.start_s - onset_verwacht_s) * 1000
                opmerking = f"gedetecteerde_start_s={eerste_segment.start_s:.3f}; n_segmenten={len(segmenten)}"

            logger.log_run(
                testcorpus_uiting_id=rij["uiting_id"],
                latentie_ms=detectielatentie_ms,
                opmerkingen=f"onset_verwacht_s={onset_verwacht_s}; modus={modus}; {opmerking}",
            )
            print(f"{rij['uiting_id']}: detectielatentie={detectielatentie_ms:.1f}ms ({opmerking})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybride VAD (WebRTC + RMS) — testplan T4.2")
    groep = parser.add_mutually_exclusive_group(required=True)
    groep.add_argument("--wav", help="analyseer één WAV-bestand, print segmenten (geen logging)")
    groep.add_argument("--manifest", help="CSV met uiting_id,wav_path,onset_verwacht_s voor een gelogde testrun")
    parser.add_argument("--test-id", default="T4.2")
    parser.add_argument("--fase", default="vad_detectie")
    parser.add_argument("--aggressiveness", type=int, default=2, choices=[0, 1, 2, 3])
    parser.add_argument("--rms-drempel", type=int, default=250, help="RMS-drempel voor de energiecheck")
    parser.add_argument("--modus", default="or", choices=["or", "and"])
    args = parser.parse_args()

    if args.wav:
        segmenten = detecteer_spraak_segmenten(args.wav, args.aggressiveness, args.rms_drempel, args.modus)
        if not segmenten:
            print("Geen spraaksegmenten gedetecteerd.")
        for s in segmenten:
            print(f"  spraak: {s.start_s:.2f}s - {s.eind_s:.2f}s (duur {s.eind_s - s.start_s:.2f}s)")
    else:
        run_corpus(args.manifest, args.test_id, args.fase, args.aggressiveness, args.rms_drempel, args.modus)


if __name__ == "__main__":
    main()
