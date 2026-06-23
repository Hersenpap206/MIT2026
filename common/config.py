"""
Centrale configuratie voor project Loods WP3 — Project Loods MITH26010 / WBSO LOODS-2026-TWO.

Alle platform-scripts importeren hardware-adressen en pinnen uitsluitend van hieruit.
Wijzig bedrading hier op één plek; verspreid geen hardcoded pinnen/adressen in de losse
sensor_reader.py-bestanden.

Bedrading is gebaseerd op de daadwerkelijk bestelde sensoren (facturen Kiwi Electronics +
TinyTronics, juni 2026), niet op de oorspronkelijke generieke testplan-tekst (BME688/KSL4402/
DM0A1307). Zie WP3 Testplan v2/Testplan_WP3_Gedetailleerd_v2.docx voor de volledige
reconciliatietabel en motivatie.
"""

from __future__ import annotations

import os
import platform as _platform
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Platform / device identificatie
# ---------------------------------------------------------------------------

PLATFORM_LINUX = "Linux"
PLATFORM_WINDOWS = "Windows"
PLATFORM_EMBEDDED = "Embedded"

VALID_PLATFORMS = (PLATFORM_LINUX, PLATFORM_WINDOWS, PLATFORM_EMBEDDED)
VALID_DEVICES = ("A", "B")


def detect_platform() -> str:
    """Best-effort auto-detectie; overschrijf via env var LOODS_PLATFORM indien nodig."""
    override = os.environ.get("LOODS_PLATFORM")
    if override:
        return override
    system = _platform.system()
    if system == "Windows":
        return PLATFORM_WINDOWS
    if system == "Linux":
        # Termux op Android meldt zich ook als "Linux"; onderscheid via env var
        # die in scripts/android_stm32_termux/sensor_reader.py wordt gezet, of
        # via de aanwezigheid van com.termux in het pad.
        if "com.termux" in os.environ.get("PREFIX", ""):
            return PLATFORM_EMBEDDED
        return PLATFORM_LINUX
    return PLATFORM_EMBEDDED


def device_id() -> str:
    """A of B — stel in via env var LOODS_DEVICE=A of LOODS_DEVICE=B per fysiek device."""
    value = os.environ.get("LOODS_DEVICE", "A").strip().upper()
    if value not in VALID_DEVICES:
        raise ValueError(f"LOODS_DEVICE moet 'A' of 'B' zijn, kreeg: {value!r}")
    return value


# ---------------------------------------------------------------------------
# I2C-adressen (gelden voor alle drie platforms, transportlaag verschilt)
# ---------------------------------------------------------------------------

I2C_ADDR_DHT20 = 0x38       # Grove Temperature & Humidity Sensor V2.0 (DHT20)
I2C_ADDR_ADS1115 = 0x48     # ADS1115 16-bit ADC, ADDR-pin op GND (default)
ADS1115_CHANNEL_LIGHT = 0   # Grove Light Sensor v1.2 analoge uitgang -> ADS1115 kanaal A0


# ---------------------------------------------------------------------------
# Linux (Raspberry Pi 5) — direct GPIO/I2C op het 40-pin header
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RPi5Pins:
    i2c_bus: int = 1                 # /dev/i2c-1, SDA=GPIO2 (pin3), SCL=GPIO3 (pin5)
    pir_gpio: int = 17               # Grove PIR digitale uitgang, BCM-nummering (pin 11)
    sensor_power_rail: str = "3V3"   # pin 1 — NIET 5V, RPi5 GPIO is 3.3V-only
    sensor_gnd_pin: int = 9


# ---------------------------------------------------------------------------
# Windows (LattePanda 3 Delta) — via MCP2221A USB-I2C/GPIO-bridge
# (smbus2 werkt niet native op Windows, vandaar de bridge — zie boodschappenlijst WP3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LattePandaPins:
    mcp2221a_pir_gpio: str = "G0"    # MCP2221A GP0 als digitale ingang voor Grove PIR
    # SDA/SCL lopen intern in de MCP2221A-driver; geen los pinnummer nodig voor I2C.


# ---------------------------------------------------------------------------
# Embedded/Edge (STM32MP257F-EV1, Android/Termux) — twee bedradingspaden
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class STM32Pins:
    # Pad 1 (primair): rechtstreeks via GPIO-expansion-connector CN5, die volgens
    # UM3359 §8.16 pin-compatibel is met Raspberry Pi shields:
    #   I2C8 SDA = pin 3 (PZ3), SCL = pin 5 (PZ4)  -- zelfde pinnummers als RPi5!
    # Werkt alleen als Android /dev/i2c-* blootstelt aan Termux (root of vendor-permissie
    # vereist — controleer on-site met `ls /dev/i2c*`).
    direct_i2c_bus: int = 8           # I2C8 op CN5, zie UM3359 Table 29 (GPIO connector pinout)
    direct_i2c_sda_pin: int = 3       # CN5 pin 3 = PZ3 = I2C8.SDA
    direct_i2c_scl_pin: int = 5       # CN5 pin 5 = PZ4 = I2C8.SCL
    direct_pir_pin: int = 26          # CN5 pin 26 = PJ1 / GPIO7 (vrij digitaal pin)

    # Pad 2 (fallback): MCP2221A-over-USB, via de USB-OTG-hub (zie boodschappenlijst WP3,
    # sectie 8 "Android op STM32MP257F-EV1"), aangestuurd met termux-usb voor permissie.
    usb_mcp2221a_pir_gpio: str = "G0"


PINS_LINUX = RPi5Pins()
PINS_WINDOWS = LattePandaPins()
PINS_EMBEDDED = STM32Pins()


# ---------------------------------------------------------------------------
# Microfoon (ReSpeaker USB-array) en overige hardware-constanten
# ---------------------------------------------------------------------------

MIC_SAMPLE_RATE_HZ = 16_000
MIC_CHANNELS = 1
MIC_DEVICE_NAME_HINT = "ReSpeaker"   # substring-match in sounddevice device-lijst

# ReSpeaker-aanschaf is NIET bevestigd via een factuur in de projectmap (geen Farnell-
# factuur aangetroffen). Aangenomen aanwezig per gebruikersinstructie — verifieer dit
# fysiek vóór de eerste testdag en pas MIC_DEVICE_NAME_HINT aan indien een ander device.

REPLICATIE_DREMPEL_PCT = 5.0          # max. toegestaan verschil Device A vs B (testplan §9.1)
WER_BASELINE_DREMPEL_PCT = 10.0       # WBSO/testplan drempelwaarde, stille omgeving
WER_NACHTZORG_DREMPEL_PCT = 25.0      # WBSO/testplan drempelwaarde, nachtzorgcondities
FRR_DREMPEL_PCT = 10.0
LATENTIE_DREMPEL_MS = 2000.0
CROSS_DEVICE_LATENTIE_DREMPEL_MS = 500.0


@dataclass(frozen=True)
class RunContext:
    """Metadata die bij elke meetrun wordt vastgelegd t.b.v. reproduceerbaarheid/publicatie."""

    platform: str = field(default_factory=detect_platform)
    device: str = field(default_factory=device_id)
    operator: str = os.environ.get("LOODS_OPERATOR", "onbekend")
    software_version: str = os.environ.get("LOODS_SW_VERSION", "v1.0-dev")
    device_serial: str = os.environ.get("LOODS_DEVICE_SERIAL", "")

    def validate(self) -> None:
        if self.platform not in VALID_PLATFORMS:
            raise ValueError(f"Onbekend platform: {self.platform!r}")
        if self.device not in VALID_DEVICES:
            raise ValueError(f"Onbekend device: {self.device!r}")
