"""
Microfoonopname (ReSpeaker USB-array) voor project Loods WP3 — Linux (RPi5) en Windows (LattePanda).

LET OP — ReSpeaker-aanschaf is niet bevestigd via een factuur in de projectmap (geen Farnell-
factuur aangetroffen, zie reconciliatietabel in WP3 Testplan v2/Testplan_WP3_Gedetailleerd_v2.docx).
Verifieer fysiek vóór de eerste testdag en pas MIC_DEVICE_NAME_HINT in scripts/common/config.py
aan indien een ander device wordt gebruikt.

TERMUX/ANDROID (STM32MP257F-EV1): dit script werkt daar NIET out-of-the-box. Termux heeft geen
gegarandeerde ALSA-toegang tot USB-audioklasse-microfoons. Gebruik in plaats daarvan:
    1. Termux:API `termux-microphone-record` voor de interne telefoonmicrofoon (niet de ReSpeaker), of
    2. Een kleine Android-opname-app (bv. via een eenvoudige AudioRecord-intent) die de ReSpeaker
       als USB-audio-input gebruikt en een .wav-bestand produceert, of
    3. Handmatige overdracht: neem op via PC, speel af in de testopstelling (alleen geschikt voor
       T2.3 cloud-benchmark, NIET voor far-field hardwaretests T1.x).
    In alle drie gevallen: verwerk het resulterende .wav-bestand met dezelfde
    scripts/speech/*.py-runners — die zijn bestand-gebaseerd en dus platform-onafhankelijk.

Gebruik:
    python mic_capture.py --out opname.wav --duur 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.config import MIC_CHANNELS, MIC_DEVICE_NAME_HINT, MIC_SAMPLE_RATE_HZ

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "sounddevice/soundfile ontbreken — installeer met: pip install sounddevice soundfile"
    ) from exc


def vind_respeaker_device_index() -> int | None:
    """Zoekt in de sounddevice device-lijst naar een naam die MIC_DEVICE_NAME_HINT bevat."""
    for idx, device in enumerate(sd.query_devices()):
        if MIC_DEVICE_NAME_HINT.lower() in device["name"].lower() and device["max_input_channels"] > 0:
            return idx
    return None


def neem_op(out_path: str | Path, duur_s: float, device_index: int | None = None) -> Path:
    """Neem `duur_s` seconden audio op en sla op als WAV (16-bit PCM, mono, 16kHz default)."""
    if device_index is None:
        device_index = vind_respeaker_device_index()
        if device_index is None:
            beschikbaar = "\n".join(f"  [{i}] {d['name']}" for i, d in enumerate(sd.query_devices()))
            raise IOError(
                f"Geen device gevonden met '{MIC_DEVICE_NAME_HINT}' in de naam. "
                f"Beschikbare devices:\n{beschikbaar}\n"
                "Geef handmatig --device-index op, of pas MIC_DEVICE_NAME_HINT aan in config.py."
            )

    print(f"Opname gestart op device [{device_index}] '{sd.query_devices()[device_index]['name']}' "
          f"({duur_s}s, {MIC_SAMPLE_RATE_HZ}Hz, {MIC_CHANNELS}ch)...")
    opname = sd.rec(
        int(duur_s * MIC_SAMPLE_RATE_HZ),
        samplerate=MIC_SAMPLE_RATE_HZ,
        channels=MIC_CHANNELS,
        device=device_index,
        dtype="int16",
    )
    sd.wait()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, opname, MIC_SAMPLE_RATE_HZ, subtype="PCM_16")
    print(f"Opname opgeslagen: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Microfoonopname (ReSpeaker) voor project Loods")
    parser.add_argument("--out", required=True, help="pad naar uitvoer .wav-bestand")
    parser.add_argument("--duur", type=float, default=5.0, help="opnameduur in seconden")
    parser.add_argument("--device-index", type=int, default=None, help="forceer een specifiek device")
    args = parser.parse_args()
    neem_op(args.out, args.duur, args.device_index)


if __name__ == "__main__":
    main()
