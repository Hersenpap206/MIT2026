"""Scant de I2C-bus van de MCP2221A: welke adressen reageren?

Verwacht: 0x38 (DHT20) en 0x48 (ADS1115). Ontbreekt er een, dan zit daar een bedradingsfout.
"""
import os
import sys
sys.path.insert(0, r"D:\Loods WP3\MIT2026")
# Blinka spreekt de MCP2221A alleen aan als deze variabele staat; zonder dit
# denkt het dat het op de Windows-host zelf draait en faalt de import.
os.environ.setdefault("BLINKA_MCP2221", "1")
import board, busio

i2c = busio.I2C(board.SCL, board.SDA)
while not i2c.try_lock():
    pass
try:
    gevonden = i2c.scan()
finally:
    i2c.unlock()

print("gevonden I2C-adressen:", [hex(a) for a in gevonden] or "(geen)")
verwacht = {0x38: "DHT20 (temp/vocht)", 0x48: "ADS1115 (ADC/licht)"}
for adres, naam in verwacht.items():
    status = "AANWEZIG" if adres in gevonden else "ONTBREEKT"
    print(f"  {hex(adres)}  {naam:24s} {status}")
extra = [a for a in gevonden if a not in verwacht]
if extra:
    print("  onverwacht:", [hex(a) for a in extra])
    if any(a in (0x49, 0x4a, 0x4b) for a in extra):
        print("  -> een ADS1115 op 0x49/0x4a/0x4b betekent dat ADDR niet aan GND ligt")
