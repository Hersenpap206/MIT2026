"""Toetst de sensoreisen T-2, T-3 en T-4 uit Addendum A in een doorlopende meetreeks.

T-2  temperatuur en vocht uitleesbaar, binnen bereik en plausibel
T-3  de ADC reageert aantoonbaar: ten minste 0,5 V verschil tussen afgedekt en onafgedekt
T-4  ten minste drie bewegingsdetecties in een reeks van twintig seconden met beweging

De operator hoeft niet op een signaal te wachten: dek de lichtsensor ergens tijdens de meting
een paar seconden af en beweeg af en toe voor de PIR. Het script zoekt achteraf het hoogste en
laagste lichtniveau en telt de detecties, zodat timing geen rol speelt.

Gebruik:
    py -3.12 t5_2_sensoren.py --duur 30
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\Loods WP3\MIT2026")

from windows_lattepanda.sensor_reader import LattePandaSensorSet  # type: ignore

T3_MIN_VERSCHIL_V = 0.5
T4_MIN_DETECTIES = 3
T4_VENSTER_S = 20.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duur", type=float, default=30.0)
    ap.add_argument("--interval", type=float, default=0.5)
    args = ap.parse_args()

    print(f"Meting van {args.duur:.0f} s gestart.")
    print("  - dek de lichtsensor ergens tussendoor een paar seconden af")
    print("  - beweeg af en toe voor de bewegingssensor\n", flush=True)

    metingen = []
    sensors = LattePandaSensorSet()
    try:
        start = time.monotonic()
        while time.monotonic() - start < args.duur:
            t = time.monotonic() - start
            try:
                m = sensors.read_all()
            except Exception as exc:
                print(f"  {t:5.1f}s  uitlezen mislukt: {type(exc).__name__}: {exc}")
                time.sleep(args.interval)
                continue
            metingen.append((t, m))
            print(f"  {t:5.1f}s  temp {m.get('temp_c'):5.2f}  vocht {m.get('vocht_pct'):5.2f}  "
                  f"licht {m.get('light_voltage'):7.4f} V  pir {m.get('pir_detect')}", flush=True)
            time.sleep(args.interval)
    finally:
        sensors.close()

    if not metingen:
        raise SystemExit("Geen enkele meting gelukt.")

    temps = [m["temp_c"] for _, m in metingen if m.get("temp_c") is not None]
    vocht = [m["vocht_pct"] for _, m in metingen if m.get("vocht_pct") is not None]
    licht = [m["light_voltage"] for _, m in metingen if m.get("light_voltage") is not None]
    pir = [(t, m.get("pir_detect")) for t, m in metingen]

    print(f"\n{len(metingen)} metingen\n")

    # ---- T-2
    t2 = bool(temps and vocht
              and 0 <= min(temps) and max(temps) <= 80
              and 0 <= min(vocht) and max(vocht) <= 100)
    print(f"T-2  temperatuur {min(temps):.2f} - {max(temps):.2f} C, "
          f"vocht {min(vocht):.2f} - {max(vocht):.2f} %")
    print(f"     binnen bereik en plausibel : {'ja' if t2 else 'NEE'}")

    # ---- T-3
    verschil = (max(licht) - min(licht)) if licht else 0.0
    t3 = verschil >= T3_MIN_VERSCHIL_V
    print(f"\nT-3  licht {min(licht):.4f} - {max(licht):.4f} V, verschil {verschil:.4f} V")
    print(f"     verschil >= {T3_MIN_VERSCHIL_V} V          : {'ja' if t3 else 'NEE'}")
    if not t3:
        print("     (is de sensor wel echt afgedekt geweest? het verschil moet van donker "
              "naar licht gaan)")

    # ---- T-4: beste aaneengesloten venster van 20 s
    beste = 0
    for i, (t0, _) in enumerate(pir):
        in_venster = [d for t, d in pir[i:] if t - t0 <= T4_VENSTER_S]
        beste = max(beste, sum(1 for d in in_venster if d))
    t4 = beste >= T4_MIN_DETECTIES
    totaal = sum(1 for _, d in pir if d)
    print(f"\nT-4  detecties totaal {totaal} van {len(pir)} metingen; "
          f"beste venster van {T4_VENSTER_S:.0f} s: {beste}")
    print(f"     >= {T4_MIN_DETECTIES} detecties in 20 s      : {'ja' if t4 else 'NEE'}")

    print("\n--- uitkomst ---")
    for naam, ok in (("T-2 temperatuur en vocht", t2), ("T-3 analoge lichtmeting", t3),
                     ("T-4 bewegingsdetectie", t4)):
        print(f"  {naam:28s} {'BEHAALD' if ok else 'NIET BEHAALD'}")


if __name__ == "__main__":
    main()
