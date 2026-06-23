"""
Whisper-batchrunner (lokale inferentie, testplan T2.1 — "kleine modellen op SBC").

Gebruikt de officiële `openai-whisper`-package (CPU- of GPU-inferentie, geen cloud-call — dat is
precies waarom dit los staat van azure_speech.py). Draait op alle drie platforms zolang Python +
ffmpeg beschikbaar zijn (Linux/Windows zonder probleem; op Termux/Android is dit zwaar voor de
STM32MP257F — verwacht lange latenties of gebruik het "tiny"-model, zie testplan-risicoparagraaf
over modelgrootte vs. SBC-rekenkracht).

Gebruik:
    python whisper_runner.py --manifest corpus/T2.1_manifest.csv --test-id T2.1 --model small
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.engine_runner import run_engine_batch

try:
    import whisper
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "openai-whisper ontbreekt — installeer met: pip install openai-whisper "
        "(vereist ook ffmpeg op het PATH)"
    ) from exc

_MODEL_CACHE: dict[str, "whisper.Whisper"] = {}


def _laad_model(model_naam: str) -> "whisper.Whisper":
    if model_naam not in _MODEL_CACHE:
        print(f"Whisper-model '{model_naam}' laden (eenmalig, kan even duren)...")
        _MODEL_CACHE[model_naam] = whisper.load_model(model_naam)
    return _MODEL_CACHE[model_naam]


def maak_transcribe_fn(model_naam: str, taal: str = "nl"):
    """Geeft een transcribe_fn(wav_path) -> str terug, gebonden aan het opgegeven modelformaat."""
    model = _laad_model(model_naam)

    def transcribe_fn(wav_path: Path) -> str:
        resultaat = model.transcribe(str(wav_path), language=taal, fp16=False)
        return resultaat["text"].strip()

    return transcribe_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper-batchrunner voor het testcorpus")
    parser.add_argument("--manifest", required=True, help="pad naar manifest-CSV (zie common/engine_runner.py)")
    parser.add_argument("--test-id", required=True, help="bv. T2.1")
    parser.add_argument("--fase", default="spraakherkenning")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--taal", default="nl")
    parser.add_argument("--mic-config", default="ReSpeaker-default")
    parser.add_argument("--afstand-m", type=float, default=None)
    parser.add_argument("--herhalingen", type=int, default=1)
    args = parser.parse_args()

    transcribe_fn = maak_transcribe_fn(args.model, args.taal)
    samenvatting = run_engine_batch(
        test_id=args.test_id,
        fase=args.fase,
        engine_naam=f"whisper-{args.model}",
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
