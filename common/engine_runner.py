"""
Gedeelde batch-runner voor spraakherkenningsengines (Whisper/Vosk/Azure — fase T2.x).

Elke engine-specifieke module (scripts/speech/whisper_runner.py etc.) implementeert alleen een
kleine `transcribe_fn(wav_path) -> str` en roept hier `run_engine_batch()` aan. Dat houdt WER-
berekening, latentiemeting en logging op precies één plek consistent over alle drie engines.

Testcorpus-manifest-formaat (CSV, UTF-8, komma-gescheiden, met header):
    uiting_id,wav_path,referentietekst,categorie
    N001,opnames/T2.1/N001.wav,"Ik voel me onveilig",normaal
    N002,opnames/T2.1/N002.wav,"ik heb... pijn",incomplete
    ...
`categorie` is vrije tekst (normaal/incomplete/gefluisterd/emotioneel) — wordt meegelogd in
`opmerkingen` zodat WER per categorie achteraf uitgesplitst kan worden (zie testplan T1.4/T2.1).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .latency_timer import LatencyTimer
from .logging_utils import TestLogger
from .wer_calc import score_utterance


@dataclass
class CorpusItem:
    uiting_id: str
    wav_path: Path
    referentietekst: str
    categorie: str = ""


def load_manifest(manifest_path: str | Path) -> list[CorpusItem]:
    items: list[CorpusItem] = []
    manifest_path = Path(manifest_path)
    with manifest_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            items.append(
                CorpusItem(
                    uiting_id=row["uiting_id"],
                    wav_path=manifest_path.parent / row["wav_path"],
                    referentietekst=row["referentietekst"],
                    categorie=row.get("categorie", ""),
                )
            )
    if not items:
        raise ValueError(f"Manifest {manifest_path} bevat geen rijen")
    return items


@dataclass
class EngineBatchSummary:
    engine: str
    n_uitingen: int
    wer_pct_gem: float
    cer_pct_gem: float
    frr_pct: float
    latentie_ms_gem: float
    latentie_ms_max: float


def run_engine_batch(
    test_id: str,
    fase: str,
    engine_naam: str,
    transcribe_fn: Callable[[Path], str],
    manifest_path: str | Path,
    mic_config: str = "n.v.t.",
    afstand_m: float | None = None,
    herhalingen: int = 1,
) -> EngineBatchSummary:
    """Voert `transcribe_fn` uit op elke regel van het manifest, `herhalingen` keer, en logt elke
    losse uiting + de samenvattende batch-statistieken (conform testplan T2.1-T2.3)."""
    items = load_manifest(manifest_path)
    timer = LatencyTimer()
    n_leeg = 0
    wer_totaal = 0.0
    cer_totaal = 0.0
    n_metingen = 0

    with TestLogger(test_id=test_id, fase=fase) as logger:
        for herhaling in range(herhalingen):
            for item in items:
                with timer.measure(label=item.uiting_id) as m:
                    hypothese = transcribe_fn(item.wav_path)

                score = score_utterance(item.referentietekst, hypothese)
                if score.is_leeg_transcript:
                    n_leeg += 1
                wer_totaal += score.wer_pct
                cer_totaal += score.cer_pct
                n_metingen += 1

                logger.log_run(
                    engine=engine_naam,
                    mic_config=mic_config,
                    afstand_m=afstand_m,
                    testcorpus_uiting_id=item.uiting_id,
                    transcript_ref=item.referentietekst,
                    transcript_hyp=hypothese,
                    wer_pct=score.wer_pct,
                    cer_pct=score.cer_pct,
                    latentie_ms=m.latentie_ms,
                    opmerkingen=f"categorie={item.categorie}; herhaling={herhaling + 1}/{herhalingen}",
                )

        stats = timer.statistieken()
        samenvatting = EngineBatchSummary(
            engine=engine_naam,
            n_uitingen=n_metingen,
            wer_pct_gem=round(wer_totaal / n_metingen, 2),
            cer_pct_gem=round(cer_totaal / n_metingen, 2),
            frr_pct=round((n_leeg / n_metingen) * 100, 2),
            latentie_ms_gem=stats.gem_ms,
            latentie_ms_max=stats.max_ms,
        )

        # Samenvattingsregel apart loggen (test_id ongewijzigd, mic_config bevat de marker
        # "SAMENVATTING" zodat deze rij makkelijk te filteren is in de analysefase)
        logger.log_run(
            engine=engine_naam,
            mic_config=f"SAMENVATTING/{mic_config}",
            afstand_m=afstand_m,
            wer_pct=samenvatting.wer_pct_gem,
            cer_pct=samenvatting.cer_pct_gem,
            frr_pct=samenvatting.frr_pct,
            latentie_ms_gem=samenvatting.latentie_ms_gem,
            latentie_ms_max=samenvatting.latentie_ms_max,
            opmerkingen=f"n_uitingen={samenvatting.n_uitingen}, herhalingen={herhalingen}",
        )

    return samenvatting
