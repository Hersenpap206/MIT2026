"""
Laptop-side publicatieklare figuren over de masterdataset (testplan WP3).

Genereert standaard wetenschappelijke vergelijkingsfiguren als PNG + SVG (vector, voor een
artikel-supplement), met vaste DPI/stijl zodat alle figuren in een publicatie consistent ogen:
    1. WER vs. afstand (lijnplot per engine) — testplan T1.x/T2.x.
    2. WER-boxplot per engine (spreiding, uitschieters) — over alle platforms/devices heen.
    3. Heatmap gemiddelde WER per platform x engine — snel overzicht welke combinatie het beste
       presteert (relevant voor de discussiesectie van een artikel én voor de EFRO-vervolgkeuze
       welk platform door te ontwikkelen).
    4. Latentie-histogram per platform — vergelijking real-time-geschiktheid.

Gebruik:
    python publication_figures.py --master ../../data/master_dataset.csv --out ../../data/analysis_output/figures
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import matplotlib

    matplotlib.use("Agg")  # geen GUI-backend nodig; werkt ook headless op een SBC of in CI
    import matplotlib.pyplot as plt
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError("pandas/matplotlib ontbreken — installeer met: pip install pandas matplotlib") from exc

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.3,
})

NUMERIEKE_KOLOMMEN = ["afstand_m", "wer_pct", "cer_pct", "frr_pct", "latentie_ms"]


def laad_master(master_path: str | Path) -> "pd.DataFrame":
    df = pd.read_csv(master_path, dtype=str)
    for kolom in NUMERIEKE_KOLOMMEN:
        if kolom in df.columns:
            df[kolom] = pd.to_numeric(df[kolom], errors="coerce")
    return df


def _bewaar(fig: "plt.Figure", out_dir: Path, naam: str) -> None:
    fig.tight_layout()
    fig.savefig(out_dir / f"{naam}.png")
    fig.savefig(out_dir / f"{naam}.svg")
    plt.close(fig)
    print(f"  figuur opgeslagen: {naam}.png / {naam}.svg")


def figuur_wer_vs_afstand(df: "pd.DataFrame", out_dir: Path) -> None:
    subset = df.dropna(subset=["wer_pct", "afstand_m", "engine"])
    if subset.empty:
        print("  WER-vs-afstand overgeslagen: geen rijen met zowel wer_pct als afstand_m")
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    for engine, groep in subset.groupby("engine"):
        gem = groep.groupby("afstand_m")["wer_pct"].mean().sort_index()
        ax.plot(gem.index, gem.values, marker="o", label=engine)
    ax.set_xlabel("Afstand (m)")
    ax.set_ylabel("WER (%)")
    ax.set_title("Word Error Rate vs. afstand tot microfoon")
    ax.legend()
    _bewaar(fig, out_dir, "wer_vs_afstand")


def figuur_wer_boxplot(df: "pd.DataFrame", out_dir: Path) -> None:
    subset = df.dropna(subset=["wer_pct", "engine"])
    if subset.empty:
        print("  WER-boxplot overgeslagen: geen rijen met wer_pct")
        return

    engines = sorted(subset["engine"].unique())
    data = [subset[subset["engine"] == e]["wer_pct"].values for e in engines]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.boxplot(data, tick_labels=engines)
    ax.set_ylabel("WER (%)")
    ax.set_title("Spreiding WER per spraakherkenningsengine")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    _bewaar(fig, out_dir, "wer_boxplot_per_engine")


def figuur_heatmap_platform_engine(df: "pd.DataFrame", out_dir: Path) -> None:
    subset = df.dropna(subset=["wer_pct", "platform", "engine"])
    if subset.empty:
        print("  Heatmap overgeslagen: geen rijen met wer_pct/platform/engine")
        return

    pivot = subset.pivot_table(values="wer_pct", index="platform", columns="engine", aggfunc="mean")

    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(pivot.values, cmap="RdYlGn_r", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            waarde = pivot.values[i, j]
            if waarde == waarde:  # niet-NaN
                ax.text(j, i, f"{waarde:.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="Gemiddelde WER (%)")
    ax.set_title("Gemiddelde WER per platform x engine")
    _bewaar(fig, out_dir, "heatmap_wer_platform_engine")


def figuur_latentie_histogram(df: "pd.DataFrame", out_dir: Path) -> None:
    subset = df.dropna(subset=["latentie_ms", "platform"])
    if subset.empty:
        print("  Latentie-histogram overgeslagen: geen rijen met latentie_ms")
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    for platform, groep in subset.groupby("platform"):
        ax.hist(groep["latentie_ms"], bins=30, alpha=0.5, label=platform)
    ax.set_xlabel("Latentie (ms)")
    ax.set_ylabel("Aantal metingen")
    ax.set_title("Verdeling latentie per platform")
    ax.legend()
    _bewaar(fig, out_dir, "latentie_histogram_per_platform")


def genereer_alle_figuren(master_path: str | Path, out_dir: str | Path) -> None:
    df = laad_master(master_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Genereer figuren uit {len(df)} rijen -> {out_dir}")
    figuur_wer_vs_afstand(df, out_dir)
    figuur_wer_boxplot(df, out_dir)
    figuur_heatmap_platform_engine(df, out_dir)
    figuur_latentie_histogram(df, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genereer publicatieklare figuren uit de masterdataset")
    parser.add_argument("--master", default="data/master_dataset.csv")
    parser.add_argument("--out", default="data/analysis_output/figures")
    args = parser.parse_args()
    genereer_alle_figuren(args.master, args.out)


if __name__ == "__main__":
    main()
