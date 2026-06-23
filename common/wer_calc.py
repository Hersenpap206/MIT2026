"""
WER/CER/FRR-berekening voor project Loods WP3 — wrapper rond `jiwer`.

Installeer met: pip install jiwer  (zie scripts/requirements_*.txt)

FRR (False Rejection Rate) is hier gedefinieerd als het percentage testuitingen waarvoor de
engine GEEN transcript opleverde (lege/ontbrekende hypothese) — dit is de definitie die in het
testplan WP3 wordt gebruikt voor "cliënt wordt niet gehoord".
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import jiwer
except ImportError as exc:  # pragma: no cover - duidelijke foutmelding i.p.v. cryptische trace
    raise ImportError(
        "jiwer is niet geïnstalleerd. Run: pip install jiwer "
        "(zie scripts/requirements_linux.txt / requirements_windows.txt / requirements_termux.txt)"
    ) from exc


_NORMALIZE = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.RemovePunctuation(),
        jiwer.ReduceToListOfListOfWords(),
    ]
)

_NORMALIZE_CHARS = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ReduceToListOfListOfChars(),
    ]
)


@dataclass
class WerResult:
    wer_pct: float
    cer_pct: float
    n_referentie_woorden: int
    is_leeg_transcript: bool  # True => telt mee voor FRR


def score_utterance(reference: str, hypothesis: str) -> WerResult:
    """Score één testuiting. `hypothesis` mag een lege string zijn (= niet herkend)."""
    is_leeg = hypothesis.strip() == ""
    # jiwer kan niet rekenen met een lege hypothese-lijst; gebruik een placeholder-token
    # zodat de WER voor deze uiting als 100% wordt geteld in plaats van een crash te geven.
    hyp_for_calc = hypothesis if not is_leeg else "[GEEN_TRANSCRIPT]"

    wer = jiwer.wer(reference, hyp_for_calc, reference_transform=_NORMALIZE, hypothesis_transform=_NORMALIZE)
    cer = jiwer.cer(
        reference, hyp_for_calc, reference_transform=_NORMALIZE_CHARS, hypothesis_transform=_NORMALIZE_CHARS
    )
    n_words = len(reference.split())

    return WerResult(
        wer_pct=round(wer * 100, 2),
        cer_pct=round(cer * 100, 2),
        n_referentie_woorden=n_words,
        is_leeg_transcript=is_leeg,
    )


@dataclass
class BatchResult:
    wer_pct_gem: float
    cer_pct_gem: float
    frr_pct: float
    n_uitingen: int
    per_uiting: list[WerResult]


def score_batch(referenties: list[str], hypotheses: list[str]) -> BatchResult:
    """Score een volledig testcorpus (bv. de 50 GGZ-nachtzorguitingen, zie testcorpus v1.0).

    referenties en hypotheses moeten gelijke lengte hebben en 1-op-1 corresponderen.
    """
    if len(referenties) != len(hypotheses):
        raise ValueError(
            f"Lengte referenties ({len(referenties)}) en hypotheses ({len(hypotheses)}) moet gelijk zijn"
        )
    if not referenties:
        raise ValueError("Lege batch — geen uitingen om te scoren")

    resultaten = [score_utterance(ref, hyp) for ref, hyp in zip(referenties, hypotheses)]

    n = len(resultaten)
    wer_gem = sum(r.wer_pct for r in resultaten) / n
    cer_gem = sum(r.cer_pct for r in resultaten) / n
    n_leeg = sum(1 for r in resultaten if r.is_leeg_transcript)
    frr = (n_leeg / n) * 100

    return BatchResult(
        wer_pct_gem=round(wer_gem, 2),
        cer_pct_gem=round(cer_gem, 2),
        frr_pct=round(frr, 2),
        n_uitingen=n,
        per_uiting=resultaten,
    )


def replicatie_verschil_pct(wer_device_a: float, wer_device_b: float) -> float:
    """Replicatieverschil A vs. B conform testplan §9.1 (eis: < 5%)."""
    if wer_device_a == 0 and wer_device_b == 0:
        return 0.0
    noemer = max(wer_device_a, wer_device_b, 1e-9)
    return round(abs(wer_device_a - wer_device_b) / noemer * 100, 2)


def load_testcorpus(path: str) -> list[str]:
    """Laad het testcorpus (één referentie-uiting per regel, UTF-8 .txt)."""
    with open(path, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]
