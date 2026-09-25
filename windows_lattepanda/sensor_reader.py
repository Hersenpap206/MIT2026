"""
Sensoruitlezing op LattePanda 3 Delta (Windows 10 Enterprise) via een MCP2221A USB-I2C/GPIO-
bridge. Native I2C (smbus2) werkt NIET op Windows — vandaar de MCP2221A-bridge (zie
boodschappenlijst WP3, sectie 7 "Sensor-compatibiliteit & extra adapters per SBC").

Bedrading (zie scripts/common/config.py — LattePandaPins):
- MCP2221A SDA/SCL  -> DHT20 @ 0x38 en ADS1115 @ 0x48 (kanaal A0 = Grove Light Sensor v1.2)
- MCP2221A GP0       -> Grove PIR digitale uitgang
- MCP2221A 3V/5V/GND -> voeding sensoren (gebruik de 3V-uitgang voor I2C-niveau-consistentie)

Installatie:
    pip install adafruit-blinka hidapi
    (Windows: sluit de Adafruit MCP2221A breakout aan via USB; geen extra driver nodig op Win10+)

Gebruik (vanuit de scripts-map, bv. de Google Drive-map — of via loods.ps1, zie README):
    python windows_lattepanda/sensor_reader.py              # smoke test: 5 metingen, 1s interval
    python windows_lattepanda/sensor_reader.py --diagnose   # stap-voor-stap bedradingscheck
    python windows_lattepanda/sensor_reader.py -n 60 -i 2   # 60 metingen met 2s interval
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# MCP2221A-backend van Adafruit Blinka activeren VOORDAT board/busio worden geïmporteerd.
os.environ.setdefault("BLINKA_MCP2221", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # zodat 'common' importeerbaar is

from common.config import I2C_ADDR_ADS1115, I2C_ADDR_DHT20, ADS1115_CHANNEL_LIGHT, PINS_WINDOWS
from common.sensors import Ads1115Driver, Dht20Driver

MCP2221A_USB_VID = 0x04D8  # Microchip
MCP2221A_USB_PID = 0x00DD


def _import_blinka():
    """Importeert board/busio/digitalio pas bij gebruik: Blinka zoekt bij `import board` direct de
    MCP2221A en crasht met een onduidelijke fout als die niet is aangesloten. Zo kan --diagnose eerst
    zelf controleren of de chip zichtbaar is."""
    try:
        import board
        import busio
        import digitalio
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "adafruit-blinka ontbreekt — installeer met: pip install adafruit-blinka hidapi"
        ) from exc
    return board, busio, digitalio


class BlinkaI2CAdapter:
    """Implementeert de I2CBus-interface (common/sensors.py) bovenop Adafruit Blinka's busio.I2C."""

    def __init__(self, i2c) -> None:
        self._i2c = i2c
        while not self._i2c.try_lock():
            time.sleep(0.01)

    def write(self, address: int, data: bytes) -> None:
        self._i2c.writeto(address, bytes(data))

    def read(self, address: int, length: int) -> bytes:
        buf = bytearray(length)
        self._i2c.readfrom_into(address, buf)
        return bytes(buf)

    def close(self) -> None:
        self._i2c.unlock()


class LattePandaSensorSet:
    """Bundelt DHT20 + Grove Light (via ADS1115) + PIR voor één LattePanda-device."""

    def __init__(self) -> None:
        board, busio, digitalio = _import_blinka()
        i2c = busio.I2C(board.SCL, board.SDA)
        self._i2c_adapter = BlinkaI2CAdapter(i2c)
        self.dht20 = Dht20Driver(self._i2c_adapter, I2C_ADDR_DHT20)
        self.light = Ads1115Driver(self._i2c_adapter, I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT)

        self._pir_pin = digitalio.DigitalInOut(getattr(board, PINS_WINDOWS.mcp2221a_pir_gpio))
        self._pir_pin.direction = digitalio.Direction.INPUT

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
            "pir_detect": int(self._pir_pin.value),
        }

    def close(self) -> None:
        self._i2c_adapter.close()
        self._pir_pin.deinit()


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

    def afbreken() -> int:
        print(f"\nDiagnose afgebroken ({fouten} fout(en)) — los dit eerst op.")
        return 1

    print("1. MCP2221A via USB")
    try:
        import hid
    except ImportError:
        fout("hidapi ontbreekt", "pip install hidapi (of draai setup_windows_lattepanda.ps1 opnieuw)")
        return afbreken()
    if not hid.enumerate(MCP2221A_USB_VID, MCP2221A_USB_PID):
        fout("geen MCP2221A gevonden (USB 04D8:00DD)",
             "andere USB-kabel proberen (laadkabels hebben geen datalijnen), andere poort, of check "
             "Apparaatbeheer > Human Interface Devices")
        return afbreken()
    ok("MCP2221A gevonden")

    print("2. I2C-bus openen en scannen")
    try:
        board, busio, digitalio = _import_blinka()
        i2c = busio.I2C(board.SCL, board.SDA)
    except Exception as exc:  # Blinka geeft uiteenlopende fouttypes
        fout(f"I2C niet te openen: {exc}",
             "staat BLINKA_MCP2221=1? Houdt een ander programma de MCP2221A vast? USB eruit/erin")
        return afbreken()
    while not i2c.try_lock():
        time.sleep(0.01)
    try:
        gevonden = i2c.scan()
    finally:
        i2c.unlock()
    ok("adressen op de bus: " + (", ".join(f"0x{a:02X}" for a in gevonden) or "geen"))
    if not gevonden:
        fout("geen enkel I2C-apparaat",
             "SDA/SCL verwisseld? Voeding: sensoren op de 3V-pin van de MCP2221A + GND")
    adapter = BlinkaI2CAdapter(i2c)

    try:
        print("3. DHT20 (temp/vocht) @ 0x%02X" % I2C_ADDR_DHT20)
        if I2C_ADDR_DHT20 not in gevonden:
            fout("niet gevonden op de bus", "check de Grove-kabel van de DHT20 (SDA, SCL, 3V, GND)")
        else:
            try:
                r = Dht20Driver(adapter, I2C_ADDR_DHT20).read()
                if not (-10 <= r.temp_c <= 50 and 0 < r.vocht_pct <= 100):
                    fout(f"onwaarschijnlijke waarde: {r}", "sensor defect of verkeerd type op 0x38")
                else:
                    ok(f"{r.temp_c} °C, {r.vocht_pct} %RV")
            except OSError as exc:
                fout(str(exc), "herhaal; blijft dit, check kabel en voeding")

        print("4. ADS1115 + Grove Light @ 0x%02X, kanaal A%d" % (I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT))
        if I2C_ADDR_ADS1115 not in gevonden:
            fout("niet gevonden op de bus", "check ADS1115-bedrading; ADDR-pin op GND = 0x48")
        else:
            try:
                r = Ads1115Driver(adapter, I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT).read_light()
                if r.voltage < 0.01:
                    fout(f"{r.voltage} V — vrijwel 0", "Grove Light zit niet op A0, of heeft geen voeding")
                elif r.voltage > 3.35:
                    fout(f"{r.voltage} V — boven 3.3V", "sensor op 5V gevoed? Gebruik de 3V-pin")
                else:
                    ok(f"{r.voltage} V (raw {r.adc_raw}, ~{r.lux_est} lux ongekalibreerd) — "
                       "dek de sensor af: spanning moet dalen")
            except OSError as exc:
                fout(str(exc), "herhaal; blijft dit, check kabel en voeding")
    finally:
        adapter.close()

    pin_naam = PINS_WINDOWS.mcp2221a_pir_gpio
    print(f"5. PIR op MCP2221A {pin_naam} — beweeg 10 s voor de sensor")
    try:
        pir = digitalio.DigitalInOut(getattr(board, pin_naam))
        pir.direction = digitalio.Direction.INPUT
    except Exception as exc:
        fout(f"{pin_naam} niet te openen: {exc}", "check PINS_WINDOWS in common/config.py")
    else:
        detecties, vorige, einde = 0, pir.value, time.monotonic() + 10
        while time.monotonic() < einde:
            nu = pir.value
            if nu and not vorige:
                detecties += 1
                print(f"         beweging gedetecteerd ({detecties})")
            vorige = nu
            time.sleep(0.05)
        pir.deinit()
        if detecties:
            ok(f"{detecties} detectie(s)")
        else:
            fout("geen beweging gezien",
                 f"signaaldraad op {pin_naam}? Grove PIR heeft na inschakelen ~30 s opwarmtijd")

    print(f"\nDiagnose klaar: {'alles OK' if fouten == 0 else f'{fouten} fout(en)'}.")
    return 0 if fouten == 0 else 1


def main() -> None:
    """Smoke test: print N metingen. Verifieer hiermee de bedrading on-site vóór de eerste echte
    testrun (zie README.md, sectie 'Eerste testrun-checklist'). Gebruik --diagnose als iets faalt."""
    parser = argparse.ArgumentParser(description="Sensoruitlezing LattePanda (DHT20, Grove Light, PIR via MCP2221A)")
    parser.add_argument("--diagnose", action="store_true", help="stap-voor-stap bedradingscheck")
    parser.add_argument("-n", "--aantal", type=int, default=5, help="aantal metingen (default 5)")
    parser.add_argument("-i", "--interval", type=float, default=1.0, help="seconden tussen metingen")
    args = parser.parse_args()

    if args.diagnose:
        sys.exit(diagnose())

    sensors = LattePandaSensorSet()
    try:
        for i in range(args.aantal):
            print(f"[{i + 1}/{args.aantal}]", sensors.read_all())
            time.sleep(args.interval)
    finally:
        sensors.close()


if __name__ == "__main__":
    main()
