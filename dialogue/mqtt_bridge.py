"""
Cross-device messaging-bridge (testplan T3.2 — "Device A signaleert, Device B reageert").

Meet de cross-device-latentie (drempel: CROSS_DEVICE_LATENTIE_DREMPEL_MS = 500ms, zie
common/config.py) via MQTT. Vereist een MQTT-broker bereikbaar voor beide devices (bv. lokale
Mosquitto op het netwerk, of een testbroker — geef het adres door via --broker).

BELANGRIJKE ONTWERPKEUZE — klokken zijn niet gesynchroniseerd:
Device A en B hebben geen gegarandeerd gesynchroniseerde klokken (geen NTP-garantie in een
testopstelling). Eén-richting "verzendtijd-op-A vs. ontvangtijd-op-B" zou daardoor klokverschil
meten, niet netwerklatentie. Daarom gebruikt dit script een round-trip-meting:
    1. Device A (--rol initiator) publiceert een "ping" met een lokale timestamp + ID.
    2. Device B (--rol responder) ontvangt de ping en publiceert onmiddellijk een "pong" terug
       met hetzelfde ID (geen klok van B nodig).
    3. Device A ontvangt de pong en berekent: round_trip_ms = (t_ontvangst_A - t_verzending_A) * 1000
       latentie_schatting_ms = round_trip_ms / 2  (aanname: symmetrisch netwerkpad)
Alleen Device A logt dus de uiteindelijke latentiemeting; Device B draait alleen de responder-loop.

Gebruik:
    # Op device B (Windows of de andere RPi5):
    python mqtt_bridge.py --rol responder --broker 192.168.1.50

    # Op device A:
    python mqtt_bridge.py --rol initiator --broker 192.168.1.50 --test-id T3.2 --n 30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import CROSS_DEVICE_LATENTIE_DREMPEL_MS, RunContext
from common.logging_utils import TestLogger

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:  # pragma: no cover
    raise ImportError("paho-mqtt ontbreekt — installeer met: pip install paho-mqtt") from exc

TOPIC_PING = "loods/test/t3_2/ping"
TOPIC_PONG = "loods/test/t3_2/pong"


def run_responder(broker: str, port: int = 1883) -> None:
    """Draait oneindig op Device B: elke ping wordt onmiddellijk teruggestuurd als pong."""

    def on_connect(client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        print(f"Responder verbonden met broker {broker}:{port}, wacht op pings op {TOPIC_PING}...")
        client.subscribe(TOPIC_PING)

    def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        client.publish(TOPIC_PONG, msg.payload)  # payload (incl. ping-ID) ongewijzigd terugsturen
        print(f"Ping ontvangen en teruggestuurd: {msg.payload!r}")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port)
    client.loop_forever()


def run_initiator(broker: str, test_id: str, fase: str, n: int, interval_s: float, port: int = 1883) -> None:
    """Stuurt `n` pings, wacht telkens op de bijbehorende pong, en logt de round-trip-schatting."""
    context = RunContext()
    wachtend: dict[str, float] = {}
    metingen: list[float] = []

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    with TestLogger(test_id=test_id, fase=fase) as logger:

        def on_message(c: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
            t_ontvangst = time.perf_counter()
            data = json.loads(msg.payload.decode("utf-8"))
            ping_id = data["id"]
            t_verzending = wachtend.pop(ping_id, None)
            if t_verzending is None:
                return  # onbekende/verlopen pong, negeren
            round_trip_ms = (t_ontvangst - t_verzending) * 1000
            latentie_schatting_ms = round_trip_ms / 2
            metingen.append(latentie_schatting_ms)
            boven_drempel = latentie_schatting_ms > CROSS_DEVICE_LATENTIE_DREMPEL_MS
            print(
                f"  [{ping_id}] round-trip={round_trip_ms:.1f}ms  "
                f"latentie_schatting={latentie_schatting_ms:.1f}ms"
                f"{'  !!! BOVEN DREMPEL' if boven_drempel else ''}"
            )
            logger.log_run(
                latentie_ms=round(latentie_schatting_ms, 2),
                opmerkingen=(
                    f"round_trip_ms={round_trip_ms:.2f}; ping_id={ping_id}; "
                    f"drempel_ms={CROSS_DEVICE_LATENTIE_DREMPEL_MS}; boven_drempel={boven_drempel}"
                ),
            )

        client.on_message = on_message
        client.connect(broker, port)
        client.subscribe(TOPIC_PONG)
        client.loop_start()

        for i in range(n):
            ping_id = str(uuid.uuid4())
            wachtend[ping_id] = time.perf_counter()
            client.publish(TOPIC_PING, json.dumps({"id": ping_id, "device": context.device}))
            time.sleep(interval_s)

        client.loop_stop()

    if metingen:
        gem = sum(metingen) / len(metingen)
        print(f"\nGemiddelde cross-device-latentieschatting: {gem:.1f}ms over {len(metingen)}/{n} succesvolle metingen")
        print(f"Drempel uit testplan: {CROSS_DEVICE_LATENTIE_DREMPEL_MS}ms")
    else:
        print("Geen enkele pong ontvangen — controleer broker-adres en of de responder draait.")


def main() -> None:
    parser = argparse.ArgumentParser(description="MQTT round-trip cross-device-latentiemeting (T3.2)")
    parser.add_argument("--rol", required=True, choices=["initiator", "responder"])
    parser.add_argument("--broker", required=True, help="IP/hostnaam van de MQTT-broker")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--test-id", default="T3.2", help="alleen relevant voor --rol initiator")
    parser.add_argument("--fase", default="cross_device_latentie")
    parser.add_argument("--n", type=int, default=30, help="aantal ping-metingen (alleen initiator)")
    parser.add_argument("--interval", type=float, default=1.0, help="seconden tussen pings (alleen initiator)")
    args = parser.parse_args()

    if args.rol == "responder":
        run_responder(args.broker, args.port)
    else:
        run_initiator(args.broker, args.test_id, args.fase, args.n, args.interval, args.port)


if __name__ == "__main__":
    main()
