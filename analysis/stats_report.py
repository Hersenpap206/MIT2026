"""
Laptop-side statistiekrapport over de masterdataset (testplan WP3 — toetst de in
common/config.py vastgelegde drempelwaarden uit het testplan).

Berekent:
    1. Beschrijvende statistiek (gemiddelde/std/p95) van WER/CER/FRR/latentie per
       platform x engine x fase.
    2. De replicatie-check (<5%, REPLICATIE_DREMPEL_PCT): verschil in gemiddelde WER tussen
       Device A en Device B, per platform x engine x fase x afstand_m-combinatie.
    3. Drempeltoetsen: WER_BASELINE_DREMPEL_PCT, WER_NACHTZORG_DREMPEL_PCT, FRR_DREMPEL_PCT,
       LATENTIE_DREMPEL_MS, CROSS_DEVICE_LATENTIE_DREMPEL_MS — elke combinatie die een drempel
       overschrijdt wordt apart vermeld zodat dit direct in de WBSO/MIT-rapportage en een
       artikel overgenomen kan worden.

Schrijft een leesbaar Markdown-rapport (geen losse tool nodig om te lezen) plus print een
samenvatting naar de console.

Gebruik:
    python stats_report.py --master ../../data/master_dataset.csv --out ../../data/analysis_output
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError("pandas ontbreekt — installeer met: pip install pandas") from exc

from common.config import (
    CROSS_DEVICE_LATENTIE_DREMPEL_MS,
    FRR_DREMPEL_PCT,
    LATENTIE_DREMPEL_MS,
    REPLICATIE_DREMPEL_PCT,
    WER_BASELINE_DREMPEL_PCT,
    WER_NACHTZORG_DREMPEL_PCT,
)

NUMERIEKE_KOLOMMEN = [
    "afstand_m", "spl_db", "temp_c", "vocht_pct", "light_adc_raw", "light_voltage",
    "light_lux_est", "wer_pct", "cer_pct", "frr_pct", "latentie_ms", "latentie_ms_gem",
    "latentie_ms_max", "cpu_pct", "ram_mb", "watt", "wh_run", "repl_diff_pct", "network_kb",
]


def laad_master(master_path: str | Path) -> "pd.DataFrame":
    df = pd.read_csv(master_path, dtype=str)
    for kolom in NUMERIEKE_KOLOMMEN:
        if kolom in df.columns:
            df[kolom] = pd.to_numeric(df[kolom], errors="coerce")
    return df


def beschrijvende_statistiek(df: "pd.DataFrame") -> "pd.DataFrame":
    groep_kolommen = ["platform", "fase", "engine"]
    metriek_kolommen = ["wer_pct", "cer_pct", "frr_pct", "latentie_ms"]
    beschikbare_metrieken = [m for m in metriek_kolommen if df[m].notna().any()]
    if not beschikbare_metrieken:
        return pd.DataFrame()
    return (
        df.groupby(groep_kolommen)[beschikbare_metrieken]
        .agg(["mean", "std", "count", lambda s: s.quantile(0.95)])
        .round(2)
    )


def replicatie_check(df: "pd.DataFrame") -> "pd.DataFrame":
    """Vergelijkt gemiddelde WER tussen Device A en B per platform x engine x fase x afstand_m."""
    if "wer_pct" not in df.columns or df["wer_pct"].notna().sum() == 0:
        return pd.DataFrame()

    groep_kolommen = ["platform", "fase", "engine", "afstand_m"]
    gem_per_device = (
        df.dropna(subset=["wer_pct"])
        .groupby(groep_kolommen + ["device"])["wer_pct"]
        .mean()
        .unstack("device")
    )
    if "A" not in gem_per_device.columns or "B" not in gem_per_device.columns:
        print("Replicatie-check overgeslagen: niet beide devices A en B aangetroffen in de data.")
        return pd.DataFrame()

    gem_per_device["repl_diff_pct"] = (gem_per_device["A"] - gem_per_device["B"]).abs()
    gem_per_device["boven_drempel"] = gem_per_device["repl_diff_pct"] > REPLICATIE_DREMPEL_PCT
    return gem_per_device.round(2)


def drempeltoetsen(df: "pd.DataFrame") -> list[str]:
    """Geeft een lijst leesbare bevindingen terug — elke regel een drempeloverschrijding of
    een 'binnen drempel'-bevestiging, gegroepeerd per relevante drempel uit het testplan."""
    bevindingen: list[str] = []

    if "wer_pct" in df.columns and df["wer_pct"].notna().any():
        for fase_naam, drempel in (("baseline", WER_BASELINE_DREMPEL_PCT), ("nachtzorg", WER_NACHTZORG_DREMPEL_PCT)):
            subset = df[df["fase"].str.contains(fase_naam, case=False, na=False)]
            if subset.empty:
                continue
            for (platform, engine), groep in subset.groupby(["platform", "engine"]):
                gem_wer = groep["wer_pct"].mean()
                status = "OVER DREMPEL" if gem_wer > drempel else "binnen drempel"
                bevindingen.append(
                    f"WER ({fase_naam}) {platform}/{engine}: {gem_wer:.1f}% (drempel {drempel}%) — {status}"
                )

    if "frr_pct" in df.columns and df["frr_pct"].notna().any():
        for (platform, engine), groep in df.groupby(["platform", "engine"]):
            gem_frr = groep["frr_pct"].mean()
            if pd.isna(gem_frr):
                continue
            status = "OVER DREMPEL" if gem_frr > FRR_DREMPEL_PCT else "binnen drempel"
            bevindingen.append(f"FRR {platform}/{engine}: {gem_frr:.1f}% (drempel {FRR_DREMPEL_PCT}%) — {status}")

    if "latentie_ms" in df.columns and df["latentie_ms"].notna().any():
        for (platform, engine), groep in df.groupby(["platform", "engine"]):
            gem_lat = groep["latentie_ms"].mean()
            if pd.isna(gem_lat):
                continue
            status = "OVER DREMPEL" if gem_lat > LATENTIE_DREMPEL_MS else "binnen drempel"
            bevindingen.append(
                f"Latentie {platform}/{engine}: {gem_lat:.0f}ms (drempel {LATENTIE_DREMPEL_MS}ms) — {status}"
            )

    cross_device = df[df["fase"].str.contains("cross_device", case=False, na=False)]
    if not cross_device.empty and cross_device["latentie_ms"].notna().any():
        gem_lat = cross_device["latentie_ms"].mean()
        status = "OVER DREMPEL" if gem_lat > CROSS_DEVICE_LATENTIE_DREMPEL_MS else "binnen drempel"
        bevindingen.append(
            f"Cross-device-latentie: {gem_lat:.0f}ms (drempel {CROSS_DEVICE_LATENTIE_DREMPEL_MS}ms) — {status}"
        )

    return bevindingen


def _naar_markdown(df: "pd.DataFrame") -> str:
    """df.to_markdown() vereist het optionele 'tabulate'-pakket; val terug op to_string() als dat
    ontbreekt, zodat het rapport niet faalt op een ontbrekende laptop-only dependency."""
    try:
        return df.to_markdown()
    except ImportError:
        return "```\n" + df.to_string() + "\n```"


def schrijf_rapport(df: "pd.DataFrame", out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rapport_path = out_dir / f"stats_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    beschrijving = beschrijvende_statistiek(df)
    replicatie = replicatie_check(df)
    bevindingen = drempeltoetsen(df)

    with rapport_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# Statistiekrapport WP3 — gegenereerd {datetime.now().isoformat(timespec='seconds')}\n\n")
        fh.write(f"Aantal rijen in masterdataset: {len(df)}\n\n")

        fh.write("## Drempeltoetsen (testplan WP3)\n\n")
        for regel in bevindingen:
            fh.write(f"- {regel}\n")
        if not bevindingen:
            fh.write("- (geen toetsbare data aangetroffen — controleer of de juiste fase-namen gebruikt zijn)\n")

        fh.write("\n## Replicatie-check (Device A vs. B, drempel "
                  f"{REPLICATIE_DREMPEL_PCT}%)\n\n")
        if replicatie.empty:
            fh.write("(geen replicatie-vergelijkbare data aangetroffen)\n")
        else:
            fh.write(_naar_markdown(replicatie))
            fh.write("\n")

        fh.write("\n## Beschrijvende statistiek per platform x fase x engine\n\n")
        if beschrijving.empty:
            fh.write("(geen metriekdata aangetroffen)\n")
        else:
            fh.write(_naar_markdown(beschrijving))
            fh.write("\n")

    return rapport_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Statistiekrapport + drempeltoetsen over de masterdataset")
    parser.add_argument("--master", default="data/master_dataset.csv")
    parser.add_argument("--out", default="data/analysis_output")
    args = parser.parse_args()

    df = laad_master(args.master)
    rapport_path = schrijf_rapport(df, args.out)

    print(f"Rapport geschreven: {rapport_path}\n")
    for regel in drempeltoetsen(df):
        print(f"  {regel}")


if __name__ == "__main__":
    main()
