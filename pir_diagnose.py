"""Onderscheidt nagloeien van een defecte PIR-module.

Een PIR houdt zijn uitgang na beweging enkele seconden hoog. Detecties vlak na de laatste
beweging zeggen dus niets; detecties die blijven komen terwijl er niets gebeurt, wijzen op een
defect - dat was het beeld bij de module op RASP2, die zelfs onder karton bleef melden.

Deze test meet alleen iets zinnigs als er in de ruimte werkelijk niets beweegt. De sluitende
variant is de sensor afdekken (--afgedekt): dan kan de omgeving het resultaat niet vertroebelen.
"""

import argparse
import sys
import time

sys.path.insert(0, r"D:\Loods WP3\MIT2026")

from windows_lattepanda.sensor_reader import LattePandaSensorSet  # type: ignore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duur", type=float, default=90.0, help="totale rustmeting")
    ap.add_argument("--uitdemp", type=float, default=30.0, help="begin dat genegeerd wordt")
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--afgedekt", action="store_true",
                    help="de sensor is afgedekt; dan is elke detectie na de uitdemptijd fout")
    args = ap.parse_args()

    kop = " - sensor afgedekt" if args.afgedekt else " - niet bewegen"
    print(f"RUSTMETING {args.duur:.0f} s{kop}")
    print(f"De eerste {args.uitdemp:.0f} s gelden als uitdemptijd en tellen niet mee.")
    print("", flush=True)

    rijen = []
    sensors = LattePandaSensorSet()
    try:
        start = time.monotonic()
        while time.monotonic() - start < args.duur:
            t = time.monotonic() - start
            try:
                m = sensors.read_all()
            except Exception:
                time.sleep(args.interval)
                continue
            rijen.append((t, int(m["pir_detect"])))
            time.sleep(args.interval)
    finally:
        sensors.close()

    if not rijen:
        raise SystemExit("Geen metingen gelukt.")

    print("tijdlijn (elk teken is een meting; X = detectie, . = rust):")
    blok = 5.0
    for b in range(int(args.duur / blok) + 1):
        in_blok = [d for t, d in rijen if b * blok <= t < (b + 1) * blok]
        if not in_blok:
            continue
        merk = " (uitdemp)" if (b + 1) * blok <= args.uitdemp else ""
        lijn = "".join("X" if d else "." for d in in_blok)
        print(f"  {b*blok:5.0f}-{(b+1)*blok:5.0f}s  {lijn}{merk}")

    na = [(t, d) for t, d in rijen if t >= args.uitdemp]
    detecties = sum(d for _, d in na)
    aandeel = detecties / len(na) if na else 0.0
    print("")
    print(f"na de uitdemptijd: {detecties} detecties in {len(na)} metingen ({aandeel*100:.0f} %)")
    print("")

    if args.afgedekt:
        print("--- sensor was afgedekt: elke detectie hierna is onterecht ---")
        if detecties == 0:
            print("OORDEEL: module in orde. Afgedekt geen enkele detectie, zoals het hoort.")
        elif aandeel <= 0.05:
            print("OORDEEL: vrijwel in orde. Een losse detectie kan door een kier in de")
            print("afdekking komen. Herhaal volledig afgedekt als je zekerheid wilt.")
        else:
            print("OORDEEL: module DEFECT. Afgedekt blijft hij beweging melden - hetzelfde")
            print("beeld als de PIR op RASP2. Vervangen is dan de enige oplossing.")
        return

    print("Let op: deze meting zegt alleen iets als er werkelijk niets bewoog in de ruimte.")
    print("Liep er iemand rond, dan meet hij die persoon en is over de module niets vastgesteld.")
    if detecties == 0:
        print("")
        print("OORDEEL: geen enkele detectie in rust. De module werkt normaal; eerdere")
        print("detecties waren nagloeien van de beweging ervoor.")
    elif aandeel <= 0.05:
        print("")
        print("OORDEEL: vrijwel geen detecties. Module werkt vermoedelijk normaal.")
    else:
        print("")
        print(f"OORDEEL: {aandeel*100:.0f} % detecties in rust - hiermee is nog niets vastgesteld.")
        print("  Was de ruimte echt leeg, dan is de module verdacht.")
        print("  Was dat niet zo, dan meet dit vooral de aanwezigheid.")
        print("  Herhaal met --afgedekt en de sensor onder karton; dat is sluitend.")


if __name__ == "__main__":
    main()
