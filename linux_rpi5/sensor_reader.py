"""
Sensoruitlezing op Raspberry Pi 5 (Linux, Raspberry Pi OS 64-bit Bookworm).

Bedrading (zie scripts/common/config.py — RPi5Pins, en WP3 Testplan v2/Testplan_WP3_Gedetailleerd_v2.docx):
- I2C1: SDA = GPIO2 (pin 3), SCL = GPIO3 (pin 5)
    - DHT20 (Grove temp/vocht)  @ I2C-adres 0x38
    - ADS1115 (ADC)             @ I2C-adres 0x48, kanaal A0 = Grove Light Sensor v1.2
- PIR (Grove Bewegingssensor) digitale uitgang -> GPIO17 (pin 11)
- Voeding sensoren: 3.3V (pin 1) + GND (pin 9) — GEEN 5V, RPi5 GPIO is 3.3V-only!

Installatie:
    sudo apt update && sudo apt install -y python3-smbus i2c-tools python3-lgpio
    pip install smbus2 gpiozero   # gpiozero gebruikt op RPi5 de lgpio-backend (RPi.GPIO werkt niet op RPi5)
    sudo raspi-config  # Interface Options -> I2C -> enable
    i2cdetect -y 1     # verwacht: 0x38 (DHT20) en 0x48 (ADS1115) zichtbaar in de tabel

Gebruik (los uitvoeren, of importeren vanuit een testscript):
    python sensor_reader.py                 # smoke test: 5 metingen, 1s interval
    python sensor_reader.py --diagnose      # stap-voor-stap bedradingscheck (eerste keer aansluiten)
    python sensor_reader.py -n 60 -i 2      # 60 metingen met 2s interval
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # zodat 'common' importeerbaar is

from common.config import I2C_ADDR_ADS1115, I2C_ADDR_DHT20, ADS1115_CHANNEL_LIGHT, PINS_LINUX
from common.sensors import Ads1115Driver, Dht20Driver, I2CBus

try:
    from smbus2 import SMBus, i2c_msg
except ImportError as exc:  # pragma: no cover
    raise ImportError("smbus2 ontbreekt — installeer met: pip install smbus2") from exc

try:
    from gpiozero import MotionSensor
except ImportError as exc:  # pragma: no cover
    raise ImportError("gpiozero ontbreekt — installeer met: pip install gpiozero") from exc


class Smbus2Adapter:
    """Implementeert de I2CBus-interface (common/sensors.py) bovenop smbus2.SMBus.

    Gebruikt ruwe I2C-transacties (i2c_rdwr) i.p.v. SMBus-blockreads: read_i2c_block_data stuurt
    eerst een registerbyte, wat de DHT20 (AHT20-protocol, plain read zonder register) niet verwacht.
    """

    def __init__(self, bus_number: int) -> None:
        self._bus = SMBus(bus_number)

    def write(self, address: int, data: bytes) -> None:
        self._bus.i2c_rdwr(i2c_msg.write(address, data))

    def read(self, address: int, length: int) -> bytes:
        msg = i2c_msg.read(address, length)
        self._bus.i2c_rdwr(msg)
        return bytes(list(msg))

    def probe(self, address: int) -> bool:
        """True als een apparaat op dit adres een ACK geeft (zoals i2cdetect)."""
        try:
            self.read(address, 1)
            return True
        except OSError:
            return False

    def close(self) -> None:
        self._bus.close()


class Rpi5SensorSet:
    """Bundelt DHT20 + Grove Light (via ADS1115) + PIR voor één RPi5-device."""

    def __init__(self) -> None:
        self._i2c_adapter = Smbus2Adapter(PINS_LINUX.i2c_bus)
        self.dht20 = Dht20Driver(self._i2c_adapter, I2C_ADDR_DHT20)
        self.light = Ads1115Driver(self._i2c_adapter, I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT)
        self.pir = MotionSensor(PINS_LINUX.pir_gpio)

    def read_all(self) -> dict:
        """Eén momentopname van alle drie sensoren — direct geschikt voor logging_utils.log_run()."""
        dht = self.dht20.read()
        light = self.light.read_light()
        return {
            "temp_c": dht.temp_c,
            "vocht_pct": dht.vocht_pct,
            "light_adc_raw": light.adc_raw,
            "light_voltage": light.voltage,
            "light_lux_est": light.lux_est,
            "pir_detect": int(self.pir.motion_detected),
        }

    def close(self) -> None:
        self._i2c_adapter.close()
        self.pir.close()


def diagnose() -> int:
    """Stap-voor-stap bedradingscheck. Elke sensor apart, zodat één kapotte aansluiting niet de
    rest verbergt. Geeft exitcode 0 als alles OK is, anders 1."""
    fouten = 0

    def ok(msg: str) -> None:
        print(f"  [OK]   {msg}")

    def fout(msg: str, hint: str) -> None:
        nonlocal fouten
        fouten += 1
        print(f"  [FOUT] {msg}\n         -> {hint}")

    print("1. I2C-bus")
    dev = Path(f"/dev/i2c-{PINS_LINUX.i2c_bus}")
    if not dev.exists():
        fout(f"{dev} bestaat niet", "I2C staat uit: sudo raspi-config nonint do_i2c 0 && sudo reboot")
        print(f"\nDiagnose afgebroken ({fouten} fout).")
        return 1
    ok(f"{dev} aanwezig")
    adapter = Smbus2Adapter(PINS_LINUX.i2c_bus)

    try:
        print("2. DHT20 (temp/vocht) @ 0x%02X" % I2C_ADDR_DHT20)
        if not adapter.probe(I2C_ADDR_DHT20):
            fout("geen ACK", "controleer SDA=pin3, SCL=pin5, 3V3=pin1, GND=pin9 en of SDA/SCL niet verwisseld zijn")
        else:
            try:
                r = Dht20Driver(adapter, I2C_ADDR_DHT20).read()
                if not (-10 <= r.temp_c <= 50 and 0 < r.vocht_pct <= 100):
                    fout(f"onwaarschijnlijke waarde: {r}", "sensor defect of verkeerd type op 0x38")
                else:
                    ok(f"{r.temp_c} °C, {r.vocht_pct} %RV")
            except OSError as exc:
                fout(str(exc), "herhaal; blijft dit, check kabel en voeding")

        print("3. ADS1115 + Grove Light @ 0x%02X, kanaal A%d" % (I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT))
        if not adapter.probe(I2C_ADDR_ADS1115):
            fout("geen ACK", "ADS1115 los op de I2C-bus (niet via GrovePi+ analoge poort); ADDR-pin op GND = 0x48")
        else:
            try:
                r = Ads1115Driver(adapter, I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT).read_light()
                if r.voltage < 0.01:
                    fout(f"{r.voltage} V — vrijwel 0", "Grove Light zit niet op A0, of heeft geen voeding (3V3/GND)")
                elif r.voltage > 3.35:
                    fout(f"{r.voltage} V — boven 3.3V", "sensor op 5V gevoed? Gebruik 3V3 (pin 1)")
                else:
                    ok(f"{r.voltage} V (raw {r.adc_raw}, ~{r.lux_est} lux ongekalibreerd) — "
                       "dek de sensor af: spanning moet dalen")
            except OSError as exc:
                fout(str(exc), "herhaal; blijft dit, check kabel en voeding")
    finally:
        adapter.close()

    print(f"4. PIR op GPIO{PINS_LINUX.pir_gpio} (pin 11) — beweeg 10 s voor de sensor")
    try:
        pir = MotionSensor(PINS_LINUX.pir_gpio)
    except Exception as exc:  # gpiozero geeft uiteenlopende pin-factory-fouten
        fout(f"GPIO niet te openen: {exc}", "sudo apt install python3-lgpio (RPi5 heeft de lgpio-backend nodig)")
    else:
        detecties, vorige, einde = 0, pir.motion_detected, time.monotonic() + 10
        while time.monotonic() < einde:
            nu = pir.motion_detected
            if nu and not vorige:
                detecties += 1
                print(f"         beweging gedetecteerd ({detecties})")
            vorige = nu
            time.sleep(0.05)
        pir.close()
        if detecties:
            ok(f"{detecties} detectie(s)")
        else:
            fout("geen beweging gezien", "signaaldraad op GPIO17/pin 11? Grove PIR heeft na inschakelen ~30 s opwarmtijd")

    print(f"\nDiagnose klaar: {'alles OK' if fouten == 0 else f'{fouten} fout(en)'}.")
    return 0 if fouten == 0 else 1


def main() -> None:
    """Smoke test: print N metingen. Verifieer hiermee de bedrading on-site vóór de eerste echte
    testrun (zie README.md, sectie 'Eerste testrun-checklist'). Gebruik --diagnose als iets faalt."""
    parser = argparse.ArgumentParser(description="Sensoruitlezing RPi5 (DHT20, Grove Light, PIR)")
    parser.add_argument("--diagnose", action="store_true", help="stap-voor-stap bedradingscheck")
    parser.add_argument("-n", "--aantal", type=int, default=5, help="aantal metingen (default 5)")
    parser.add_argument("-i", "--interval", type=float, default=1.0, help="seconden tussen metingen")
    args = parser.parse_args()

    if args.diagnose:
        sys.exit(diagnose())

    sensors = Rpi5SensorSet()
    try:
        for i in range(args.aantal):
            print(f"[{i + 1}/{args.aantal}]", sensors.read_all())
            time.sleep(args.interval)
    finally:
        sensors.close()


if __name__ == "__main__":
    main()
