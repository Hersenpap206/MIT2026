"""
Manual-assisted logging voor de Naova USB-powermeters (AVHzY-achtig type, bol.com-order).

Er is geen bevestigde publieke API/protocol voor dit apparaat aangetroffen (het is een
consumentengadget met Bluetooth-app, geen gedocumenteerde GATT-service). Dit script doet daarom
NIET alsof het automatisch kan uitlezen — het ondersteunt de operator met getimede prompts zodat
de afgelezen waarde toch consistent, op het juiste moment en met het juiste test_id gelogd wordt.

Als je later een werkend uitleesprotocol vindt (bv. via reverse-engineering van de BLE-app),
vervang dan lees_vermogen() door een echte uitlezing — de rest van de pipeline blijft identiek.

Gebruik:
    python power_monitor.py --test-id T1.1 --duur 600
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.logging_utils import TestLogger


def lees_vermogen_interactief() -> tuple[float, float]:
    """Vraagt de operator om de huidige aflezing van het Naova-display over te typen.

    Geeft (watt, wh_cumulatief) terug. Laat het veld leeg + Enter om een meting over te slaan
    (wordt dan als None gelogd in plaats van een verzonnen 0.0)."""
    watt_str = input("  Vermogen nu (W) van display, of Enter om over te slaan: ").strip()
    wh_str = input("  Cumulatieve energie (Wh) van display, of Enter: ").strip()
    watt = float(watt_str) if watt_str else float("nan")
    wh = float(wh_str) if wh_str else float("nan")
    return watt, wh


def run_power_session(test_id: str, fase: str, duur_s: int, interval_s: int = 30) -> None:
    """Loopt `duur_s` seconden, vraagt elke `interval_s` seconden een aflezing.

    Aanbevolen voor T1.1/T2.1/T2.2/T4.1/T4.2 (continue energiemeting, zie testplan WP3 §4)."""
    print(f"Powermonitor-sessie gestart voor {test_id} ({fase}). Duur: {duur_s}s, interval: {interval_s}s.")
    print("Lees bij elke prompt het Naova/AVHzY-display af en typ de waarde over.\n")

    with TestLogger(test_id=test_id, fase=fase) as logger:
        start = time.monotonic()
        volgende = start
        einde = start + duur_s
        while time.monotonic() < einde:
            wachttijd = volgende - time.monotonic()
            if wachttijd > 0:
                time.sleep(wachttijd)
            verstreken = round(time.monotonic() - start, 1)
            print(f"-- t={verstreken}s --")
            watt, wh = lees_vermogen_interactief()
            logger.log_run(watt=watt, wh_run=wh, opmerkingen=f"powermeter-aflezing t={verstreken}s")
            volgende += interval_s
    print("Powermonitor-sessie afgerond. Zie de CSV in data/<platform>/<device>/<fase>/.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual-assisted powermeter-logging (Naova/AVHzY)")
    parser.add_argument("--test-id", required=True, help="bv. T1.1, T4.1")
    parser.add_argument("--fase", default="energiemeting")
    parser.add_argument("--duur", type=int, default=600, help="sessieduur in seconden (default 600 = 10 min)")
    parser.add_argument("--interval", type=int, default=30, help="prompt-interval in seconden")
    args = parser.parse_args()
    run_power_session(args.test_id, args.fase, args.duur, args.interval)


if __name__ == "__main__":
    main()
