"""Lichte MQTT-broker voor T3.2 op het Windows-platform.

Op het Linux-platform draaide Mosquitto 2.0.21 op RASP1. Die Pi's zijn opgeborgen en Mosquitto
vergt op Windows een systeeminstallatie; deze broker draait in Python en vereist alleen een
pip-pakket. Dat verschil hoort in de verantwoording, maar raakt de meting nauwelijks: de
round-trip van 0,57 ms op de Pi's werd gedomineerd door het netwerkpad, niet door de broker.

Luistert op alle interfaces, poort 1883, anonieme toegang - zoals de Mosquitto-configuratie op
RASP1 (`/etc/mosquitto/conf.d/loods_wp3.conf`). Alleen ping/pong-verkeer van het testplan.
"""

import asyncio
import logging
import sys

from amqtt.broker import Broker

logging.basicConfig(level=logging.WARNING)

CONFIG = {
    "listeners": {
        "default": {"type": "tcp", "bind": "0.0.0.0:1883", "max_connections": 10},
    },
    "sys_interval": 0,
    "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
}


async def main() -> None:
    broker = Broker(CONFIG)
    await broker.start()
    print("broker draait op 0.0.0.0:1883 - afsluiten met Ctrl-C", flush=True)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("broker gestopt")
        sys.exit(0)
