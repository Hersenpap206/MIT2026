"""
Azure Speech-to-Text batchrunner (cloud-engine, testplan T2.3 — "cloud-benchmark"-vergelijking
t.o.v. de lokale Whisper/Vosk-engines op T2.1/T2.2).

Vereist een Azure Speech-resource (key + region). Geef deze door via --key/--region of via de
omgevingsvariabelen AZURE_SPEECH_KEY / AZURE_SPEECH_REGION (voorkeur — voorkomt dat een sleutel in
shell-historie of een script terechtkomt).

LET OP kosten/netwerk: elke uiting wordt naar de Azure-cloud gestuurd. Gebruik dit alleen voor de
T2.3-cloud-vergelijking, niet als dagelijkse smoke-test (zie testplan WP3 §kostenbeheersing).

Gebruik:
    set AZURE_SPEECH_KEY=...        (Windows)  /  export AZURE_SPEECH_KEY=... (Linux/Termux)
    set AZURE_SPEECH_REGION=westeurope
    python azure_speech.py --manifest corpus/T2.3_manifest.csv --test-id T2.3
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.engine_runner import run_engine_batch

try:
    import azure.cognitiveservices.speech as speechsdk
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "azure-cognitiveservices-speech ontbreekt — installeer met: "
        "pip install azure-cognitiveservices-speech "
        "(op Termux/ARM is dit pakket mogelijk niet beschikbaar; gebruik in dat geval de "
        "REST Speech-to-Text API i.p.v. de SDK, of voer T2.3 uit vanaf de laptop)"
    ) from exc


def maak_transcribe_fn(key: str, region: str, taal: str = "nl-NL"):
    """Geeft een transcribe_fn(wav_path) -> str terug die telkens 1 Azure-call per uiting doet
    (recognize_once_async — past bij losse, korte testcorpus-uitingen, geen continue stream)."""
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = taal

    def transcribe_fn(wav_path: Path) -> str:
        audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        resultaat = recognizer.recognize_once()

        if resultaat.reason == speechsdk.ResultReason.RecognizedSpeech:
            return resultaat.text.strip()
        if resultaat.reason == speechsdk.ResultReason.NoMatch:
            return ""  # telt mee als lege transcriptie -> FRR, niet als script-fout
        raise RuntimeError(f"Azure Speech-fout ({resultaat.reason}) bij {wav_path}: {resultaat.cancellation_details}")

    return transcribe_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Azure Speech-batchrunner voor het testcorpus")
    parser.add_argument("--manifest", required=True, help="pad naar manifest-CSV (zie common/engine_runner.py)")
    parser.add_argument("--test-id", required=True, help="bv. T2.3")
    parser.add_argument("--fase", default="cloud_benchmark")
    parser.add_argument("--key", default=os.environ.get("AZURE_SPEECH_KEY"), help="Azure Speech-key")
    parser.add_argument("--region", default=os.environ.get("AZURE_SPEECH_REGION"), help="bv. westeurope")
    parser.add_argument("--taal", default="nl-NL")
    parser.add_argument("--mic-config", default="ReSpeaker-default")
    parser.add_argument("--afstand-m", type=float, default=None)
    parser.add_argument("--herhalingen", type=int, default=1)
    args = parser.parse_args()

    if not args.key or not args.region:
        parser.error(
            "Azure-key/region ontbreken. Geef --key/--region op of zet "
            "AZURE_SPEECH_KEY/AZURE_SPEECH_REGION als omgevingsvariabele."
        )

    transcribe_fn = maak_transcribe_fn(args.key, args.region, args.taal)
    samenvatting = run_engine_batch(
        test_id=args.test_id,
        fase=args.fase,
        engine_naam="azure-speech",
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
