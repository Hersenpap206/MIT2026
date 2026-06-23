"""
Latentiemeting voor project Loods WP3 — context-manager rond time.perf_counter().

Gebruik:
    from common.latency_timer import LatencyTimer

    timer = LatencyTimer()
    with timer.measure() as m:
        transcript = engine.transcribe(audio)
    print(m.latentie_ms)            # duur van dit blok
    print(timer.statistieken())     # samenvatting over alle metingen tot nu toe
"""

from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class Meting:
    latentie_ms: float = 0.0
    label: str = ""


@dataclass
class LatentieStatistieken:
    n: int
    gem_ms: float
    max_ms: float
    min_ms: float
    p95_ms: float
    stdev_ms: float


class LatencyTimer:
    """Houdt alle metingen van een testrun bij; gebruik per test_id/engine één instantie."""

    def __init__(self) -> None:
        self._metingen: list[Meting] = []

    @contextmanager
    def measure(self, label: str = "") -> Iterator[Meting]:
        """Meet de duur van het blok in milliseconden. Start telt vanaf binnenkomst van de
        context, conform testplan: 'tijdstip spraak-einde -> tijdstip transcript-output'."""
        meting = Meting(label=label)
        start = time.perf_counter()
        try:
            yield meting
        finally:
            einde = time.perf_counter()
            meting.latentie_ms = round((einde - start) * 1000, 3)
            self._metingen.append(meting)

    def reset(self) -> None:
        self._metingen.clear()

    @property
    def metingen(self) -> list[Meting]:
        return list(self._metingen)

    def statistieken(self) -> LatentieStatistieken:
        if not self._metingen:
            raise ValueError("Geen metingen om te aggregeren — roep eerst measure() aan")
        waarden = [m.latentie_ms for m in self._metingen]
        waarden_sorted = sorted(waarden)
        p95_index = max(0, int(round(0.95 * (len(waarden_sorted) - 1))))
        return LatentieStatistieken(
            n=len(waarden),
            gem_ms=round(statistics.mean(waarden), 3),
            max_ms=round(max(waarden), 3),
            min_ms=round(min(waarden), 3),
            p95_ms=round(waarden_sorted[p95_index], 3),
            stdev_ms=round(statistics.stdev(waarden), 3) if len(waarden) > 1 else 0.0,
        )
