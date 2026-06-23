"""
Vosk-batchrunner (lokale, lichte streaming-herkenner, testplan T2.1 — alternatief voor Whisper op
zwakkere SBC's). Vosk draait volledig offline met een klein vooraf gedownload taalmodel en is
geschikt als low-resource-vergelijkingspunt, met name relevant voor het STM32MP257F-EV1-platform.

Modeldownload (NL): https://alphacephei.com/vosk/models — pak uit naar een lokale map en geef het
pad door via --model-path. Dit script downloadt NIETS automatisch (geen netwerk-aanname).

Gebruik:
    python vosk_stream.py --manifest corpus/T2.1_manifest.csv --test-id T2.1 \
        --model-path /pad/naar/vosk-model-nl
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.engine_runner import run_engine_batch

try:
    import vosk
except ImportError as exc:  # pragma: no cover
    raise ImportError("vosk ontbreekt — installeer met: pip install vosk") from exc

vosk.SetLogLevel(-1)  # onderdruk Vosk's eigen stderr-logging, die anders elke run vervuilt

_MODEL_CACHE: dict[str, "vosk.Model"] = {}


def _laad_model(model_path: str) -> "vosk.Model":
    if model_path not in _MODEL_CACHE:
        print(f"Vosk-model laden vanaf '{model_path}' (eenmalig)...")
        _MODEL_CACHE[model_path] = vosk.Model(model_path)
    return _MODEL_CACHE[model_path]


def maak_transcribe_fn(model_path: str):
    """Geeft een transcribe_fn(wav_path) -> str terug. Verwacht 16-bit mono PCM WAV-bestanden
    (zoals geproduceerd door scripts/mic_capture.py — MIC_SAMPLE_RATE_HZ in common/config.py)."""
    model = _laad_model(model_path)

    def transcribe_fn(wav_path: Path) -> str:
        with wave.open(str(wav_path), "rb") as wf:
            if wf.getnchannels() != 1:
                raise ValueError(f"{wav_path}: Vosk vereist mono audio, kreeg {wf.getnchannels()} kanalen")
            recognizer = vosk.KaldiRecognizer(model, wf.getframerate())
            recognizer.SetWords(False)

            stukken: list[str] = []
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                if recognizer.AcceptWaveform(data):
                    stuk = json.loads(recognizer.Result()).get("text", "")
                    if stuk:
                        stukken.append(stuk)
            laatste = json.loads(recognizer.FinalResult()).get("text", "")
            if laatste:
                stukken.append(laatste)

        return " ".join(stukken).strip()

    return transcribe_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Vosk-batchrunner voor het testcorpus")
    parser.add_argument("--manifest", required=True, help="pad naar manifest-CSV (zie common/engine_runner.py)")
    parser.add_argument("--test-id", required=True, help="bv. T2.1")
    parser.add_argument("--fase", default="spraakherkenning")
    parser.add_argument("--model-path", required=True, help="pad naar uitgepakt Vosk-taalmodel (NL)")
    parser.add_argument("--mic-config", default="ReSpeaker-default")
    parser.add_argument("--afstand-m", type=float, default=None)
    parser.add_argument("--herhalingen", type=int, default=1)
    args = parser.parse_args()

    transcribe_fn = maak_transcribe_fn(args.model_path)
    samenvatting = run_engine_batch(
        test_id=args.test_id,
        fase=args.fase,
        engine_naam="vosk",
        transcribe_fn=transcribe_fn,
        manifest_path=args.manifest,
        mic_config=args.mic_config,
        afstand_m=args.afstand_m,
        herhalingen=args.herhalingen,
    )
    print(
        f"Klaar: {samenvatting.engine} — WER={samenvatting.wer_pct_gem}% "
        f"CER={samenvatting.cer_pct_gem}% FRR={samenvatting.frr_pct}% "
        f"latentie_gem={samenvatting.latentie_ms_gem:.0f}ms over {samenvatting.n_uitingen} uitingen"
    )


if __name__ == "__main__":
    main()
