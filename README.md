# MIT2026 — scripts/ — Project Loods WP3 testtooling

Python-tooling voor de drie hardwareplatforms (Linux/RPi5, Windows/LattePanda, Embedded/STM32
via Termux) + laptop-side analyse. Zie `WP3 Testplan v2/Testplan_WP3_Gedetailleerd_v2.docx` voor
de volledige testprocedures en `WP3 Testplan v2/Data_Codebook.md` voor het CSV-schema.

**Geen van deze scripts is tegen echte hardware getest** (deze codebase is geschreven zonder
hardware-in-loop-toegang). Loop bij de eerste testdag de checklist onderaan dit document door.

## Mapstructuur

```
scripts/
  common/                 gedeelde modules (config, logging, WER, latentie, sensordrivers)
  linux_rpi5/             sensor_reader.py voor Raspberry Pi 5
  windows_lattepanda/     sensor_reader.py voor LattePanda 3 Delta (via MCP2221A)
  android_stm32_termux/   sensor_reader.py voor STM32MP257F-EV1 (Android/Termux)
  speech/                 whisper_runner.py, vosk_stream.py, azure_speech.py
  dialogue/               dialogue_engine.py, mqtt_bridge.py, vad_hybrid.py
  analysis/               aggregate_data.py, stats_report.py, publication_figures.py (laptop)
  power_monitor.py        manual-assisted Naova/AVHzY powermeter-logging
  spl_monitor.py          manual-assisted UNI-T UT353-BT SPL-logging
  mic_capture.py          ReSpeaker-opname (Linux/Windows)
  requirements_*.txt      per platform
```

## Omgevingsvariabelen (vóór elke testrun zetten)

| Variabele | Verplicht | Voorbeeld | Betekenis |
|---|---|---|---|
| `LOODS_DEVICE` | ja | `A` of `B` | Welk device van het A/B-paar dit is (replicatie-eis). |
| `LOODS_PLATFORM` | nee (auto-detect) | `Linux` / `Windows` / `Embedded` | Override als auto-detectie faalt (zie `common/config.py: detect_platform()`). |
| `LOODS_OPERATOR` | aanbevolen | `wim` | Wie de run uitvoert. |
| `LOODS_SW_VERSION` | **sterk aanbevolen** | `v1.0-dev` of een git-commit-hash | Voor reproduceerbaarheid — zie Data_Codebook.md. |
| `LOODS_DEVICE_SERIAL` | optioneel | `RPi5-A-001` | Fysiek label, handig bij RMA/vervanging. |

PowerShell: `$env:LOODS_DEVICE = "A"`. Bash/Termux: `export LOODS_DEVICE=A`.

## Installatie per platform

### Linux (Raspberry Pi 5)

```bash
sudo apt install python3-smbus i2c-tools
sudo raspi-config   # Interface Options -> I2C -> enable, reboot
pip install -r requirements_linux.txt
i2cdetect -y 1       # controleer: 0x38 (DHT20) en 0x48 (ADS1115) moeten zichtbaar zijn
```

### Windows (LattePanda 3 Delta)

```powershell
pip install -r requirements_windows.txt
# Sluit de MCP2221A aan via USB; Windows installeert de HID-driver doorgaans automatisch.
# Als webrtcvad niet compileert: pip install webrtcvad-wheels in plaats daarvan.
```

### Embedded (STM32MP257F-EV1, Termux/Android)

```bash
pkg update && pkg install python termux-api libusb clang
pip install -r requirements_termux.txt
ls -l /dev/i2c-*     # bestaat dit pad? zonder root/permissieve vendor-config typisch NIET zichtbaar
```

Zie de uitgebreide docstring in `android_stm32_termux/sensor_reader.py` voor het twee-paden-plan
(direct I2C vs. MCP2221A-over-USB) — dit moet on-site bevestigd worden welk pad werkt.

### Laptop (analyse)

```bash
pip install -r requirements_laptop.txt
```

## Bedrading-quickref

| Sensor | Linux (RPi5, 40-pin header) | Windows (MCP2221A breakout) | Embedded (CN5-connector / MCP2221A-fallback) |
|---|---|---|---|
| DHT20 (I2C, 0x38) + ADS1115 (I2C, 0x48, Grove Light op kanaal A0) | SDA=pin3 (GPIO2), SCL=pin5 (GPIO3), 3V3=pin1, GND=pin9 | SDA/SCL op MCP2221A, voeding via breakout 3V3-pin | Primair: SDA=pin3 (PZ3), SCL=pin5 (PZ4) op CN5 (zelfde pinnummers als RPi5). Fallback: MCP2221A-over-USB. |
| Grove PIR (digitaal) | GPIO17 (pin 11) | MCP2221A GP0 | Primair: CN5-pin (zie `STM32Pins.direct_pir_pin` in `common/config.py`). Fallback: MCP2221A GP0. |

⚠️ **RPi5 GPIO is 3.3V-only.** Sluit sensoren nooit aan op 5V signaal- of voedingspinnen op dit
platform. Alle exacte pin-/adresconstanten staan in `common/config.py` — wijzig bedrading-
constanten daar, niet in de individuele platformscripts.

## Eén testrun end-to-end (voorbeeld T2.1, lokale spraakherkenning)

```bash
export LOODS_DEVICE=A
export LOODS_SW_VERSION=v1.0-dev

# 1. Sensorcontext vastleggen (optioneel, voor temp/vocht/licht-condities tijdens de test)
python linux_rpi5/sensor_reader.py

# 2. Audiocorpus opnemen (of gebruik een vooraf opgenomen corpus + manifest)
python mic_capture.py --out opnames/T2.1/N001.wav --duur 5

# 3. Spraakherkenning + WER/latentie, gelogd naar data/Linux/A/spraakherkenning/...
python speech/whisper_runner.py --manifest corpus/T2.1_manifest.csv --test-id T2.1 --model small

# (herhaal stap 3 voor vosk_stream.py / azure_speech.py, en op Device B, voor de replicatie-check)
```

## Analyse (op de laptop, na het verzamelen van data van alle devices)

```bash
cd scripts/analysis
python aggregate_data.py --data-dir ../../data --out ../../data/master_dataset.csv
python stats_report.py --master ../../data/master_dataset.csv --out ../../data/analysis_output
python publication_figures.py --master ../../data/master_dataset.csv --out ../../data/analysis_output/figures
```

`stats_report.py` toetst automatisch tegen de drempelwaarden uit `common/config.py`
(replicatie <5%, WER-baseline <10%, WER-nachtzorg <25%, FRR <10%, latentie <2000ms,
cross-device-latentie <500ms) en markeert overschrijdingen in het Markdown-rapport.

## Checklist eerste testdag (on-site validatie, Fase 1)

1. `python -m py_compile` over alle scripts is al gedaan vóór oplevering (geen syntaxfouten) —
   dit bevestigt alleen dat de code geldig Python is, NIET dat de hardwarelogica klopt.
2. Linux: `i2cdetect -y 1` bevestigt 0x38 + 0x48 → draai `linux_rpi5/sensor_reader.py` los.
3. Windows: sluit MCP2221A aan, controleer Apparaatbeheer (HID-apparaat zichtbaar) → draai
   `windows_lattepanda/sensor_reader.py` los.
4. Embedded: `ls -l /dev/i2c-*` → als leeg, ga direct naar het MCP2221A-USB-fallbackpad en
   implementeer de `NotImplementedError`-stubs in `Mcp2221UsbAdapter` (zie datasheet AN1) vóórdat
   je verder gaat — dit IS de bekende, vooraf gevlagde onzekerheid in dit plan.
5. Microfoon: bevestig dat de ReSpeaker daadwerkelijk is aangeschaft/geleverd (factuur ontbrak in
   de projectmap) vóór `mic_capture.py` te gebruiken; test `vind_respeaker_device_index()` los.
6. Powermeter/SPL-meter: er is geen automatische uitlezing — loop één keer `power_monitor.py`
   en `spl_monitor.py` door om te wennen aan het manual-assisted promptritme vóór de echte meting.
7. MQTT-broker: zorg dat beide devices bij dezelfde broker (lokaal IP) kunnen — test eerst met
   `mosquitto_pub`/`mosquitto_sub` handmatig vóór `mqtt_bridge.py` te gebruiken.
