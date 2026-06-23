"""
Manual-assisted logging voor de UNI-T UT353-BT decibel-meter (bol.com-order).

Net als bij power_monitor.py: er is geen bevestigd publiek BLE-protocol voor dit apparaat
aangetroffen, dus dit script vraagt de operator om de aflezing over te typen in plaats van een
niet-bestaande automatische uitlezing te simuleren.

Gebruik als losse CLI (periodieke controle-metingen, bv. vóór T1.1 om <30 dB te bevestigen):
    python spl_monitor.py --test-id T1.1 --n 5

Of importeer `lees_spl_interactief()` direct in een testscript om één omgevingsgeluid-controle
in te bouwen vóór een testrun start (zie testplan WP3, T1.1 stap 1: 'omgevingsgeluid <30 dB SPL').
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.logging_utils import TestLogger


def lees_spl_interactief(context: str = "") -> float:
    """Vraagt de operator om de huidige UT353-BT-aflezing (dB SPL) over te typen."""
    prompt = f"  SPL-meter aflezing (dB SPL){' — ' + context if context else ''}: "
    waarde = input(prompt).strip()
    return float(waarde) if waarde else float("nan")


def run_spl_check(test_id: str, fase: str, n_metingen: int, interval_s: int = 5) -> list[float]:
    """Doet `n_metingen` losse SPL-controlemetingen, bv. als vooraf-check vóór een testfase."""
    waarden: list[float] = []
    with TestLogger(test_id=test_id, fase=fase) as logger:
        for i in range(n_metingen):
            spl = lees_spl_interactief(context=f"meting {i + 1}/{n_metingen}")
            waarden.append(spl)
            logger.log_run(spl_db=spl, opmerkingen=f"SPL-controlemeting {i + 1}/{n_metingen}")
            if i < n_metingen - 1:
                time.sleep(interval_s)

    geldige = [w for w in waarden if w == w]  # filtert NaN (Enter zonder waarde) eruit
    if geldige:
        print(f"Gemiddeld SPL over {len(geldige)} geldige metingen: {sum(geldige) / len(geldige):.1f} dB")
    return waarden


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual-assisted SPL-logging (UNI-T UT353-BT)")
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--fase", default="omgevingscontrole")
    parser.add_argument("--n", type=int, default=5, help="aantal metingen")
    parser.add_argument("--interval", type=int, default=5, help="seconden tussen metingen")
    args = parser.parse_args()
    run_spl_check(args.test_id, args.fase, args.n, args.interval)


if __name__ == "__main__":
    main()
