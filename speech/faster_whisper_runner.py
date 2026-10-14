"""Batchrunner voor faster-whisper (CTranslate2) — zelfde modellen, andere implementatie.

Reden voor deze runner: op 14 oktober bleek dat geen enkele geteste engine de responsiedrempel
van 2000 ms haalt. Whisper small levert de beste herkenning (18,97% WER) maar doet er 18,9 s over
op de LattePanda en 11,3 s op de Raspberry Pi; Vosk is met 4,1 s het snelst maar blijft met 27,8%
net boven de nachtzorgdrempel. faster-whisper draait dezelfde Whisper-modellen op CTranslate2 en
haalt doorgaans een factor 4 tot 8, en is daarmee de enige kandidaat die beide eisen tegelijk
binnen bereik kan brengen: de nauwkeurigheid van small met een latentie in de orde van Vosk.

De engine wordt gelogd als `faster-whisper-<model>`, zodat de meetdata naast `whisper-<model>`
staat en het verschil tussen implementaties zichtbaar blijft in dezelfde dataset.

Gebruik:
    python speech/faster_whisper_runner.py --manifest corpus/T2.2_manifest_d40.csv \
        --test-id T2.2 --model small --afstand-m 4.0

    # int8-kwantisatie is op een CPU zonder AVX512 vaak sneller dan float32:
    python speech/faster_whisper_runner.py --manifest ... --compute-type int8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import LOODS_MODEL_DIR
from common.engine_runner import run_engine_batch

try:
    from faster_whisper import WhisperModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "faster-whisper ontbreekt — installeer met: pip install faster-whisper"
    ) from exc

_MODEL_CACHE: dict[tuple[str, str], "WhisperModel"] = {}


def _laad_model(model_naam: str, compute_type: str) -> "WhisperModel":
    sleutel = (model_naam, compute_type)
    if sleutel not in _MODEL_CACHE:
        print(f"faster-whisper '{model_naam}' laden ({compute_type}, eenmalig)...")
        model_dir = LOODS_MODEL_DIR / "faster-whisper"
        model_dir.mkdir(parents=True, exist_ok=True)
        # Eigen modelmap: CTranslate2 gebruikt een ander formaat dan de .pt-bestanden van
        # openai-whisper, dus die twee mogen niet in dezelfde map belanden.
        _MODEL_CACHE[sleutel] = WhisperModel(
            model_naam,
            device="cpu",
            compute_type=compute_type,
            download_root=str(model_dir),
        )
    return _MODEL_CACHE[sleutel]


def maak_transcribe_fn(model_naam: str, taal: str = "nl", compute_type: str = "int8"):
    """Geeft een transcribe_fn(wav_path) -> str terug, gebonden aan model en rekenformaat."""
    model = _laad_model(model_naam, compute_type)

    def transcribe_fn(wav_path: Path) -> str:
        segmenten, _info = model.transcribe(str(wav_path), language=taal)
        # transcribe() levert een generator: pas bij het uitlezen wordt er gerekend, dus dit
        # moet binnen de gemeten functie gebeuren en niet erbuiten.
        return " ".join(s.text.strip() for s in segmenten).strip()

    return transcribe_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="faster-whisper-batchrunner voor het testcorpus")
    parser.add_argument("--manifest", required=True, help="pad naar manifest-CSV")
    parser.add_argument("--test-id", required=True, help="bv. T2.1")
    parser.add_argument("--fase", default="spraakherkenning")
    parser.add_argument("--model", default="small",
                        choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--compute-type", default="int8",
                        choices=["int8", "int8_float32", "float32"],
                        help="int8 is op een CPU zonder AVX512 doorgaans het snelst")
    parser.add_argument("--taal", default="nl")
    parser.add_argument("--mic-config", default="ReSpeaker-default")
    parser.add_argument("--afstand-m", type=float, default=None)
    parser.add_argument("--herhalingen", type=int, default=1)
    args = parser.parse_args()

    transcribe_fn = maak_transcribe_fn(args.model, args.taal, args.compute_type)
    samenvatting = run_engine_batch(
        test_id=args.test_id,
        fase=args.fase,
        engine_naam=f"faster-whisper-{args.model}-{args.compute_type}",
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
