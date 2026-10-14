"""Logt één handmatige meteraflezing als meetregel, zonder interactie.

`power_monitor.py` vraagt de waarden met input() en kan daarom niet over een niet-interactieve
verbinding draaien (ssh met een commando, of een script). Dit hulpmiddel neemt dezelfde waarden
als argument, zodat een aflezing die de operator telefonisch of per bericht doorgeeft alsnog in
de dataset komt met het juiste test_id, device en tijdstip.

Gebruik:
    python3 log_aflezing.py --test-id T4.1 --watt 12.4 --conditie "volle last, Whisper small"
    python3 log_aflezing.py --test-id T4.1 --watt 3.4 --conditie rust --spl 28
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.logging_utils import TestLogger


def main() -> None:
    parser = argparse.ArgumentParser(description="Eén handmatige aflezing loggen")
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--fase", default="energiemeting")
    parser.add_argument("--watt", type=float, help="momentaan vermogen van het display")
    parser.add_argument("--wh", type=float, help="cumulatieve energie, als die eenduidig af te lezen is")
    parser.add_argument("--spl", type=float, help="aflezing geluidsdrukmeter in dB")
    parser.add_argument("--conditie", default="", help="waaronder is gemeten, bv. 'rust' of 'volle last'")
    args = parser.parse_args()

    with TestLogger(test_id=args.test_id, fase=args.fase) as logger:
        rij = logger.log_run(
            watt=args.watt,
            wh_run=args.wh,
            spl_db=args.spl,
            opmerkingen=(f"handmatige aflezing; conditie={args.conditie}" if args.conditie
                         else "handmatige aflezing"),
        )
        print(f"gelogd in {logger.csv_path}")
        print(f"  device={rij.device} hardware={rij.hardware} watt={rij.watt} conditie={args.conditie}")


if __name__ == "__main__":
    main()
