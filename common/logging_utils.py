"""
Gestructureerde datalogging voor project Loods WP3.

Schrijft elke meting als één rij in een CSV-bestand (en optioneel JSON-export) conform het
schema in WP3 Testplan v2/Data_Codebook.md. Eén CSV per testfase per device wordt aanbevolen
(zie scripts/README.md); scripts/analysis/aggregate_data.py voegt ze later samen.

Gebruik:
    from common.logging_utils import TestLogger

    logger = TestLogger(test_id="T1.1", fase="hardwareonderzoek")
    logger.log_run(engine="Whisper-small", afstand_m=1.0, temp_c=21.3, ...)
    logger.close()
"""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, date, time as dtime
from pathlib import Path
from typing import Any

from .config import RunContext

# Volgorde van kolommen = canonieke volgorde uit Data_Codebook.md. Wijzig hier ALLEEN in
# combinatie met een update van het codebook-document, anders lopen schema en data uit elkaar.
CSV_FIELDS = [
    "run_id",
    "datum",
    "tijd",
    "test_id",
    "fase",
    "platform",
    "device",
    "device_serial",
    "engine",
    "mic_config",
    "afstand_m",
    "spl_db",
    "temp_c",
    "vocht_pct",
    "light_adc_raw",
    "light_voltage",
    "light_lux_est",
    "pir_detect",
    "testcorpus_uiting_id",
    "transcript_ref",
    "transcript_hyp",
    "wer_pct",
    "cer_pct",
    "frr_pct",
    "latentie_ms",
    "latentie_ms_gem",
    "latentie_ms_max",
    "cpu_pct",
    "ram_mb",
    "watt",
    "wh_run",
    "repl_diff_pct",
    "network_kb",
    "software_version",
    "operator",
    "opmerkingen",
]


@dataclass
class MeasurementRow:
    """Eén regel in het testlogboek. Alle velden optioneel behalve test_id/fase — vul aan
    naarmate de meting beschikbaar komt (sensors, engine-output, powermeter-aflezing, ...)."""

    test_id: str
    fase: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    datum: str = field(default_factory=lambda: date.today().isoformat())
    tijd: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    platform: str = ""
    device: str = ""
    device_serial: str = ""
    engine: str = ""
    mic_config: str = ""
    afstand_m: float | None = None
    spl_db: float | None = None
    temp_c: float | None = None
    vocht_pct: float | None = None
    light_adc_raw: int | None = None
    light_voltage: float | None = None
    light_lux_est: float | None = None
    pir_detect: int | None = None
    testcorpus_uiting_id: str = ""
    transcript_ref: str = ""
    transcript_hyp: str = ""
    wer_pct: float | None = None
    cer_pct: float | None = None
    frr_pct: float | None = None
    latentie_ms: float | None = None
    latentie_ms_gem: float | None = None
    latentie_ms_max: float | None = None
    cpu_pct: float | None = None
    ram_mb: float | None = None
    watt: float | None = None
    wh_run: float | None = None
    repl_diff_pct: float | None = None
    network_kb: float | None = None
    software_version: str = ""
    operator: str = ""
    opmerkingen: str = ""

    def as_csv_dict(self) -> dict[str, Any]:
        row = asdict(self)
        return {key: row.get(key, "") for key in CSV_FIELDS}


class TestLogger:
    """Eén logger per testsessie (typisch: per test_id + device + dag)."""

    def __init__(
        self,
        test_id: str,
        fase: str,
        out_dir: str | Path = "data",
        context: RunContext | None = None,
    ) -> None:
        self.test_id = test_id
        self.fase = fase
        self.context = context or RunContext()
        self.context.validate()

        self.out_dir = Path(out_dir) / self.context.platform / self.context.device / fase
        self.out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{test_id}_{self.context.platform}_{self.context.device}_{date.today().isoformat()}.csv"
        self.csv_path = self.out_dir / filename
        self._rows: list[dict[str, Any]] = []

        is_new_file = not self.csv_path.exists()
        self._fh = self.csv_path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=CSV_FIELDS)
        if is_new_file:
            self._writer.writeheader()

    def log_run(self, **kwargs: Any) -> MeasurementRow:
        """Maak en schrijf direct één meetregel. Onbekende kwargs worden afgewezen (typo-check)."""
        row = MeasurementRow(
            test_id=self.test_id,
            fase=self.fase,
            platform=self.context.platform,
            device=self.context.device,
            device_serial=self.context.device_serial,
            software_version=self.context.software_version,
            operator=self.context.operator,
            **kwargs,
        )
        self._writer.writerow(row.as_csv_dict())
        self._fh.flush()
        self._rows.append(row.as_csv_dict())
        return row

    def export_json(self, path: str | Path | None = None) -> Path:
        """Exporteer alle tot nu toe gelogde rijen van deze sessie als JSON (metadata + data)."""
        json_path = Path(path) if path else self.csv_path.with_suffix(".json")
        payload = {
            "test_id": self.test_id,
            "fase": self.fase,
            "platform": self.context.platform,
            "device": self.context.device,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "n_rows": len(self._rows),
            "rows": self._rows,
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return json_path

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "TestLogger":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def init_log(test_id: str, fase: str, out_dir: str | Path = "data") -> TestLogger:
    """Backwards-compatible alias — komt overeen met de naam genoemd in de taakomschrijving
    J. Esselink WP3 §6.1 (logging_utils.py: init_log(), log_run(), export_csv(), export_json())."""
    return TestLogger(test_id=test_id, fase=fase, out_dir=out_dir)
