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

Gebruik:
    python sensor_reader.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# MCP2221A-backend van Adafruit Blinka activeren VOORDAT board/busio worden geïmporteerd.
os.environ.setdefault("BLINKA_MCP2221", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # zodat 'common' importeerbaar is

from common.config import I2C_ADDR_ADS1115, I2C_ADDR_DHT20, ADS1115_CHANNEL_LIGHT, PINS_WINDOWS
from common.sensors import Ads1115Driver, Dht20Driver

try:
    import board
    import busio
    import digitalio
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "adafruit-blinka ontbreekt — installeer met: pip install adafruit-blinka hidapi"
    ) from exc


class BlinkaI2CAdapter:
    """Implementeert de I2CBus-interface (common/sensors.py) bovenop Adafruit Blinka's busio.I2C."""

    def __init__(self, i2c: "busio.I2C") -> None:
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


def main() -> None:
    """Smoke test: print 5 metingen met 1s interval. Verifieer hiermee de bedrading on-site
    vóór de eerste echte testrun (zie scripts/README.md, sectie 'Eerste testrun-checklist')."""
    sensors = LattePandaSensorSet()
    try:
        for i in range(5):
            print(f"[{i + 1}/5]", sensors.read_all())
            time.sleep(1)
    finally:
        sensors.close()


if __name__ == "__main__":
    main()
