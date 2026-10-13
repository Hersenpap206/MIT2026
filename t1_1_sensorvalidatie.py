"""
T1.1 sensorvalidatie (testplan §8) — logt de sensormetingen naar CSV.

`linux_rpi5/sensor_reader.py` is een smoke test: die print naar het scherm en schrijft niets weg.
Dit script doet hetzelfde uitlezen, maar via TestLogger, zodat de metingen in `data/` terechtkomen
en meegaan in `aggregate_data.py`.

De referentiethermometer en de SPL-meter worden handmatig afgelezen (geen protocol beschikbaar voor
de UT353-BT, zie `spl_monitor.py`). Geef die waarden mee als argument; ze komen in `spl_db`
respectievelijk als key=value in `opmerkingen`, conform de conventie in Data_Codebook.md.

Gebruik op de Pi:
    cd ~/MIT2026
    python3 t1_1_sensorvalidatie.py --temp-ref 20.8 --spl 28.5

    # alleen de sensoren, zonder handmatige aflezingen:
    python3 t1_1_sensorvalidatie.py

Controleer vooraf dat LOODS_DEVICE op A of B staat — anders komt de meting onder het verkeerde
device terecht (de standaardwaarde is "A").
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.logging_utils import TestLogger
from linux_rpi5.sensor_reader import Rpi5SensorSet


def main() -> None:
    parser = argparse.ArgumentParser(description="T1.1 sensorvalidatie met CSV-logging")
    parser.add_argument("--aantal", type=int, default=5, help="aantal metingen (testplan: 5)")
    parser.add_argument("--interval", type=float, default=2.0, help="seconden tussen metingen")
    parser.add_argument("--temp-ref", type=float, help="aflezing losse referentiethermometer in °C")
    parser.add_argument("--spl", type=float, help="aflezing UT353-BT in dB (eis T1.1: <30 dB)")
    parser.add_argument("--opmerking", default="", help="vrije aantekening bij deze reeks")
    args = parser.parse_args()

    aantekeningen = []
    if args.temp_ref is not None:
        aantekeningen.append(f"temp_ref_c={args.temp_ref}")
    if args.spl is not None:
        aantekeningen.append("spl_bron=UT353-BT handmatig")
    if args.opmerking:
        aantekeningen.append(args.opmerking)
    opmerkingen = "; ".join(aantekeningen)

    sensors = Rpi5SensorSet()
    try:
        with TestLogger(test_id="T1.1", fase="hardwareonderzoek") as logger:
            print(f"Logt naar: {logger.csv_path}")
            print(f"Device {logger.context.device} / {logger.context.hardware} / {logger.context.os_versie}")
            for i in range(args.aantal):
                waarden = sensors.read_all()
                logger.log_run(spl_db=args.spl, opmerkingen=opmerkingen, **waarden)
                print(
                    f"[{i + 1}/{args.aantal}] "
                    f"{waarden['temp_c']:.1f}°C  {waarden['vocht_pct']:.1f}%RH  "
                    f"{waarden['light_voltage']:.3f}V  PIR={waarden['pir_detect']}"
                )
                if i < args.aantal - 1:
                    time.sleep(args.interval)

            if args.temp_ref is not None:
                gemeten = [r["temp_c"] for r in logger._rows if r["temp_c"] is not None]
                if gemeten:
                    afwijking = sum(gemeten) / len(gemeten) - args.temp_ref
                    print(f"\nAfwijking t.o.v. referentiethermometer: {afwijking:+.2f} °C")
                    print("DHT20-datasheettolerantie is ±0.3 °C; een grotere afwijking hoort in het verslag.")
            if args.spl is not None and args.spl >= 30.0:
                print(f"\nLET OP: {args.spl} dB haalt de T1.1-eis van <30 dB niet.")
    finally:
        sensors.close()


if __name__ == "__main__":
    main()
