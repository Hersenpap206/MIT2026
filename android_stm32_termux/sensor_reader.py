"""
Sensoruitlezing op STM32MP257F-EV1 (Android/AOSP) via Termux.

Dit platform is het meest onzekere bedradingspad in project Loods (zie risicoparagraaf in
WP3 Testplan v2/Testplan_WP3_Gedetailleerd_v2.docx) — dit script probeert daarom EERST het
primaire pad en valt automatisch terug op het secundaire pad.

PAD 1 — PRIMAIR: directe I2C via het 40-pin GPIO-expansion-connector (CN5)
    UM3359 §8.16 vermeldt dat CN5 pin-compatibel is met Raspberry Pi shields: I2C8 SDA = pin 3
    (PZ3), SCL = pin 5 (PZ4) — zelfde pinnummers als de RPi5. Dit werkt ALLEEN als Android
    /dev/i2c-* blootstelt aan een Termux-proces (root, of een vendor-config die de groep
    'i2c' leesbaar/schrijfbaar maakt voor de shell-user). Controleer dit on-site met:
        ls -l /dev/i2c-*
    De Linux-kernel nummert I2C-adapters naar device-tree-volgorde, niet noodzakelijk gelijk aan
    de STM32-naam "I2C8" — dit script SCANT daarom alle /dev/i2c-* bussen op de bekende adressen
    (0x38 DHT20, 0x48 ADS1115) in plaats van een bus-nummer te hardcoden.

PAD 2 — FALLBACK: MCP2221A-over-USB, via de USB-OTG-hub (zie boodschappenlijst WP3 §8), met
    `termux-usb` voor de permissie-grant. Vereist: `pkg install termux-api libusb`, de
    Termux:API-app geïnstalleerd, en de gebruiker moet bij de eerste keer USB-permissie
    bevestigen in een Android-dialoog (kan niet headless/silent).

Installatie (Termux):
    pkg update && pkg install python termux-api libusb
    pip install pyusb

PIR: zelfde bron als het gekozen I2C-pad (CN5 digitale pin, of MCP2221A GP0).
"""

from __future__ import annotations

import glob
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # zodat 'common' importeerbaar is

from common.config import I2C_ADDR_ADS1115, I2C_ADDR_DHT20, ADS1115_CHANNEL_LIGHT
from common.sensors import Ads1115Driver, Dht20Driver, I2CBus


class DirectI2CAdapter:
    """PAD 1: leest/schrijft rechtstreeks naar /dev/i2c-N via de Linux i2c-dev ioctl-interface.

    Gebruikt geen smbus2 (vaak niet beschikbaar/compileerbaar in Termux zonder root); implementeert
    de benodigde ioctl-aanroep zelf met de standaard `fcntl`/`struct`-modules.
    """

    I2C_SLAVE = 0x0703  # ioctl-constante uit linux/i2c-dev.h

    def __init__(self, bus_number: int) -> None:
        import os

        self._fd = os.open(f"/dev/i2c-{bus_number}", os.O_RDWR)
        self._bus_number = bus_number

    def _set_slave(self, address: int) -> None:
        import fcntl

        fcntl.ioctl(self._fd, self.I2C_SLAVE, address)

    def write(self, address: int, data: bytes) -> None:
        import os

        self._set_slave(address)
        os.write(self._fd, bytes(data))

    def read(self, address: int, length: int) -> bytes:
        import os

        self._set_slave(address)
        return os.read(self._fd, length)

    def close(self) -> None:
        import os

        os.close(self._fd)

    @staticmethod
    def probe_voor_adres(address: int) -> int | None:
        """Scan alle /dev/i2c-* bussen en geef het busnummer terug waarop `address` reageert,
        of None als geen enkele bus dat adres heeft (zie module-docstring: STM32 'I2C8' komt
        niet noodzakelijk overeen met hetzelfde /dev/i2c-N nummer)."""
        for path in sorted(glob.glob("/dev/i2c-*")):
            bus_number = int(path.rsplit("-", 1)[-1])
            try:
                adapter = DirectI2CAdapter(bus_number)
            except PermissionError:
                continue  # geen rechten op deze bus -> volgende proberen
            except FileNotFoundError:
                continue
            try:
                adapter._set_slave(address)
                import os

                os.read(adapter._fd, 1)
                return bus_number
            except OSError:
                continue
            finally:
                adapter.close()
        return None


class Mcp2221UsbAdapter:
    """PAD 2 (fallback): MCP2221A over USB, via termux-usb permissie + pyusb.

    Vereist dat de gebruiker eenmalig de USB-permissie-dialoog bevestigt (niet automatiseerbaar).
    Zie scripts/README.md, sectie 'Termux USB-fallback' voor de volledige procedure.
    """

    MCP2221A_VID = 0x04D8
    MCP2221A_PID = 0x00DD

    def __init__(self) -> None:
        try:
            import usb.core  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "pyusb ontbreekt — installeer met: pkg install libusb && pip install pyusb"
            ) from exc

        self._usb = usb.core
        device = usb.core.find(idVendor=self.MCP2221A_VID, idProduct=self.MCP2221A_PID)
        if device is None:
            raise IOError(
                "MCP2221A niet gevonden via USB. Geef eerst USB-permissie met "
                "'termux-usb -l' en 'termux-usb -r <devicepath>' (zie scripts/README.md)."
            )
        self._device = device

    def write(self, address: int, data: bytes) -> None:
        raise NotImplementedError(
            "MCP2221A HID-commandoset (I2C write) nog te implementeren/valideren on-site — "
            "zie MCP2221A datasheet AN1: I2C Write Data command (0x90/0x91/0x92)."
        )

    def read(self, address: int, length: int) -> bytes:
        raise NotImplementedError(
            "MCP2221A HID-commandoset (I2C read) nog te implementeren/valideren on-site — "
            "zie MCP2221A datasheet AN1: I2C Read Data command (0x91/0x93)."
        )

    def close(self) -> None:
        pass


def _maak_i2c_adapter() -> I2CBus:
    """Probeert PAD 1, valt terug op PAD 2. Print duidelijk welk pad actief is."""
    bus_nummer = DirectI2CAdapter.probe_voor_adres(I2C_ADDR_DHT20)
    if bus_nummer is not None:
        print(f"[sensor_reader] PAD 1 actief: directe I2C op /dev/i2c-{bus_nummer}")
        return DirectI2CAdapter(bus_nummer)

    print("[sensor_reader] PAD 1 (directe I2C) niet beschikbaar — val terug op PAD 2 (MCP2221A/USB)")
    return Mcp2221UsbAdapter()


def _pir_status_via_termux_api() -> int | None:
    """Best-effort PIR-uitlezing als losse digitale GPIO niet bereikbaar is: niet ondersteund
    zonder root op dit platform. Geeft None terug zodat de aanroeper dit als 'onbekend' logt
    i.p.v. een verkeerde 0/1-waarde te verzinnen."""
    return None


class Stm32SensorSet:
    def __init__(self) -> None:
        self._i2c_adapter = _maak_i2c_adapter()
        self.dht20 = Dht20Driver(self._i2c_adapter, I2C_ADDR_DHT20)
        self.light = Ads1115Driver(self._i2c_adapter, I2C_ADDR_ADS1115, ADS1115_CHANNEL_LIGHT)

    def read_all(self) -> dict:
        dht = self.dht20.read()
        light = self.light.read_light()
        pir = _pir_status_via_termux_api()
        return {
            "temp_c": dht.temp_c,
            "vocht_pct": dht.vocht_pct,
            "light_adc_raw": light.adc_raw,
            "light_voltage": light.voltage,
            "light_lux_est": light.lux_est,
            "pir_detect": pir,  # None = nog niet geverifieerd op dit platform, zie opmerkingen
        }

    def close(self) -> None:
        self._i2c_adapter.close()


def main() -> None:
    """Smoke test: print 5 metingen met 1s interval. Verifieer hiermee de bedrading on-site
    vóór de eerste echte testrun (zie scripts/README.md, sectie 'Eerste testrun-checklist')."""
    sensors = Stm32SensorSet()
    try:
        for i in range(5):
            print(f"[{i + 1}/5]", sensors.read_all())
            time.sleep(1)
    finally:
        sensors.close()


if __name__ == "__main__":
    main()
