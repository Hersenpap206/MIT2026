"""
Hardware-onafhankelijke sensordrivers voor DHT20 (temp/vocht) en ADS1115 (ADC voor de Grove
Light Sensor v1.2). De I2C-registerlogica staat hier ÉÉNMAAL; elk platform levert alleen een
kleine "I2CBus"-adapter (zie scripts/linux_rpi5, scripts/windows_lattepanda,
scripts/android_stm32_termux) zodat de sensor-wiskunde niet drie keer apart onderhouden wordt.

Referenties:
- DHT20 (DFRobot Gravity, Grove-behuizing) is een AHT20-compatibele sensor: trigger-commando
  0xAC 0x33 0x00, 80 ms wachten, 7 bytes terug (status + 20-bit vocht + 20-bit temp + CRC).
- ADS1115: 16-bit ADC, single-shot conversie op het geconfigureerde kanaal, gain ±4.096V (PGA=1)
  past bij de 3.3-5V analoge uitgang van de Grove Light Sensor v1.2.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class I2CBus(Protocol):
    """Minimale adapter-interface die elk platform implementeert."""

    def write(self, address: int, data: bytes) -> None: ...

    def read(self, address: int, length: int) -> bytes: ...


# ---------------------------------------------------------------------------
# DHT20 / AHT20-protocol — temperatuur + luchtvochtigheid
# ---------------------------------------------------------------------------

_DHT20_CMD_TRIGGER = bytes([0xAC, 0x33, 0x00])
_DHT20_MEASURE_DELAY_S = 0.090  # datasheet vereist >=80ms; marge voor betrouwbaarheid


@dataclass
class Dht20Reading:
    temp_c: float
    vocht_pct: float


class Dht20Driver:
    def __init__(self, bus: I2CBus, address: int) -> None:
        self._bus = bus
        self._address = address

    def read(self) -> Dht20Reading:
        self._bus.write(self._address, _DHT20_CMD_TRIGGER)
        time.sleep(_DHT20_MEASURE_DELAY_S)
        data = self._bus.read(self._address, 7)
        if len(data) < 7:
            raise IOError(f"DHT20: onvolledig antwoord ({len(data)} bytes, 7 verwacht)")

        status = data[0]
        if status & 0x80:
            raise IOError("DHT20: sensor nog bezig (busy-bit gezet) — meting overgeslagen")

        humidity_raw = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
        temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]

        vocht_pct = (humidity_raw / (1 << 20)) * 100.0
        temp_c = (temp_raw / (1 << 20)) * 200.0 - 50.0

        return Dht20Reading(temp_c=round(temp_c, 2), vocht_pct=round(vocht_pct, 2))


# ---------------------------------------------------------------------------
# ADS1115 — 16-bit ADC voor de analoge Grove Light Sensor v1.2
# ---------------------------------------------------------------------------

_ADS1115_REG_CONVERSION = 0x00
_ADS1115_REG_CONFIG = 0x01

# Config-bits: single-shot, kanaal A0 t.o.v. GND, PGA=±4.096V, 128SPS, comparator uit.
# (zie ADS1115 datasheet Table 8 voor de volledige bit-layout)
_ADS1115_CONFIG_BASE = 0xC1 << 8 | 0x83  # MUX=AIN0/GND, PGA=4.096V, MODE=single-shot, start=1
_ADS1115_FSR_VOLTAGE = 4.096
_ADS1115_CONVERSION_DELAY_S = 0.01  # >8ms bij 128SPS


@dataclass
class LightSensorReading:
    adc_raw: int
    voltage: float
    lux_est: float


def _ads1115_config_for_channel(channel: int) -> int:
    if channel not in (0, 1, 2, 3):
        raise ValueError("ADS1115-kanaal moet 0-3 zijn")
    mux_bits = (0b100 + channel) << 12  # single-ended AINx vs GND, zie datasheet Table 8
    base_without_mux = _ADS1115_CONFIG_BASE & 0x0FFF
    return mux_bits | base_without_mux


class Ads1115Driver:
    def __init__(self, bus: I2CBus, address: int, channel: int = 0) -> None:
        self._bus = bus
        self._address = address
        self._channel = channel

    def read_light(self) -> LightSensorReading:
        config = _ads1115_config_for_channel(self._channel)
        config_bytes = bytes([_ADS1115_REG_CONFIG, (config >> 8) & 0xFF, config & 0xFF])
        self._bus.write(self._address, config_bytes)
        time.sleep(_ADS1115_CONVERSION_DELAY_S)

        self._bus.write(self._address, bytes([_ADS1115_REG_CONVERSION]))
        raw = self._bus.read(self._address, 2)
        adc_raw = (raw[0] << 8) | raw[1]
        if adc_raw & 0x8000:  # negatief (two's complement op 16 bit)
            adc_raw -= 1 << 16

        voltage = (adc_raw / 32768.0) * _ADS1115_FSR_VOLTAGE

        # Benaderde lux-conversie (NIET fabriekskalibreerd): Seeed's eigen toepassingsnota voor
        # de Grove Light Sensor v1.2 geeft als vuistformule Lux ~ 10^((Vout/Vcc * Rload-factor)).
        # Hier gebruiken we de eenvoudige, in de Seeed-wiki gepubliceerde benadering. Documenteer
        # bij publicatie ALTIJD dat dit een ongekalibreerde schatting is — log daarom ook altijd
        # adc_raw en voltage zodat herkalibratie achteraf mogelijk is (zie Data_Codebook.md).
        lux_est = round((voltage / 3.3) * 10000, 1) if voltage > 0 else 0.0

        return LightSensorReading(adc_raw=adc_raw, voltage=round(voltage, 4), lux_est=lux_est)
