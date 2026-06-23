"""
Sensoruitlezing op Raspberry Pi 5 (Linux, Raspberry Pi OS 64-bit Bookworm).

Bedrading (zie scripts/common/config.py — RPi5Pins, en WP3 Testplan v2/Testplan_WP3_Gedetailleerd_v2.docx):
- I2C1: SDA = GPIO2 (pin 3), SCL = GPIO3 (pin 5)
    - DHT20 (Grove temp/vocht)  @ I2C-adres 0x38
    - ADS1115 (ADC)             @ I2C-adres 0x48, kanaal A0 = Grove Light Sensor v1.2
- PIR (Grove Bewegingssensor) digitale uitgang -> GPIO17 (pin 11)
- Voeding sensoren: 3.3V (pin 1) + GND (pin 9) — GEEN 5V, RPi5 GPIO is 3.3V-only!

Installatie:
    sudo apt update && sudo apt install -y python3-smbus i2c-tools
    pip install smbus2 gpiozero
    sudo raspi-config  # Interface Options -> I2C -> enable
    i2cdetect -y 1     # verwacht: 0x38 (DHT20) en 0x48 (ADS1115) zichtbaar in de tabel

Gebruik (los uitvoeren, of importeren vanuit een testscript):
    python sensor_reader.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # zodat 'common' importeerbaar is

from common.config import I2C_ADDR_ADS1115, I2C_ADDR_DHT20, ADS1115_CHANNEL_LIGHT, PINS_LINUX
from common.sensors import Ads1115Driver, Dht20Driver, I2CBus

try:
    from smbus2 import SMBus
except ImportError as exc:  # pragma: no cover
    raise ImportError("smbus2 ontbreekt — installeer met: pip install smbus2") from exc

try:
    from gpiozero import MotionSensor
except ImportError as exc:  # pragma: no cover
    raise ImportError("gpiozero ontbreekt — installeer met: pip install gpiozero") from exc


class Smbus2Adapter:
    """Implementeert de I2CBus-interface (common/sensors.py) bovenop smbus2.SMBus."""

    def __init__(self, bus_number: int) -> None:
        self._bus = SMBus(bus_number)

    def write(self, address: int, data: bytes) -> None:
        self._bus.write_i2c_block_data(address, data[0], list(data[1:]))

    def read(self, address: int, length: int) -> bytes:
        return bytes(self._bus.read_i2c_block_data(address, 0, length))

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


def main() -> None:
    """Smoke test: print 5 metingen met 1s interval. Verifieer hiermee de bedrading on-site
    vóór de eerste echte testrun (zie scripts/README.md, sectie 'Eerste testrun-checklist')."""
    sensors = Rpi5SensorSet()
    try:
        for i in range(5):
            print(f"[{i + 1}/5]", sensors.read_all())
            time.sleep(1)
    finally:
        sensors.close()


if __name__ == "__main__":
    main()
