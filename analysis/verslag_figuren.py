"""Genereert de figuren voor het WP3-werkgroepverslag uit de meetdata.

Leest twee databronnen: de back-up van de Raspberry Pi's (14 oktober) en de verse metingen op de
LattePanda's (16 oktober). Van het Windows-platform worden uitsluitend de metingen van 16 oktober
gebruikt; die van 14 oktober zijn systematisch te traag doordat zes engines aaneengesloten
draaiden (zie platformdocument 2 §7) en dienen alleen nog om dat volgorde-effect te tonen.

Gebruik:
    py -3.12 analysis/verslag_figuren.py <pi-data-dir> <lp-data-dir> <uitvoermap>
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PI_BRON, LP_BRON, UIT = (Path(a) for a in sys.argv[1:4])
UIT.mkdir(parents=True, exist_ok=True)

BLAUW, GROEN, ROOD, GRIJS, ORANJE = "#1f4e79", "#2e7d32", "#c62828", "#757575", "#ef6c00"
plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.grid": True, "grid.alpha": 0.25,
    "grid.linestyle": "-", "axes.axisbelow": True,
})
NUMERIEK = ("wer_pct", "cer_pct", "latentie_ms", "latentie_ms_gem", "latentie_ms_max",
            "watt", "afstand_m")


def lees(basis: Path) -> pd.DataFrame:
    frames = []
    for pad in basis.rglob("*.csv"):
        try:
            d = pd.read_csv(pad, dtype=str)
        except Exception:
            continue
        d["bron"] = pad.name
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    for kol in NUMERIEK:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")
    df["dag"] = pd.to_datetime(df["datum"], errors="coerce").dt.day
    return df


pi = lees(PI_BRON)
# De back-upmap bevat ook een LattePanda-map; op platform filteren houdt de Pi-data zuiver
# en zorgt dat beide devices (RASP1 en RASP2) meekomen, wat de replicatiefiguur nodig heeft.
pi = pi[pi["platform"] == "Linux"]
lp = lees(LP_BRON)
lp_vers = lp[lp["dag"] == 16]
print(f"Pi: {len(pi)} rijen ({sorted(pi['device'].dropna().unique())}); "
      f"LattePanda: {len(lp)} rijen, waarvan {len(lp_vers)} vers (16 okt)")


def per_engine(df, test_ids):
    """Gemiddelde WER en latentie per engine, uit de losse meetrijen (niet de samenvattingsrij)."""
    d = df[df["test_id"].isin(test_ids) & df["wer_pct"].notna() & df["latentie_ms"].notna()]
    return d.groupby("engine").agg(wer=("wer_pct", "mean"), lat=("latentie_ms", "mean"),
                                   lat_med=("latentie_ms", "median"), n=("wer_pct", "size"))


def kort(naam):
    return (naam.replace("faster-whisper-small-", "faster-whisper ")
                .replace("whisper-", "whisper ")
                .replace("vosk", "Vosk"))


# ---------------------------------------------------------------- figuur 1
# De kernvraag: haalt iets de responsie-eis? Twee platforms naast elkaar.
pi_e = per_engine(pi, ["T2.1"])          # Pi: engines gemeten op 1,0 m
lp_e = per_engine(lp_vers, ["T2.2"])     # LattePanda: engines gemeten op 4,0 m

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.4), sharex=True)
for ax, d, titel, onderschrift in (
    (ax1, pi_e.sort_values("lat"), "Raspberry Pi 5 (ARM)", "baselinecondities, 1,0 m"),
    (ax2, lp_e.sort_values("lat"), "LattePanda 3 Delta (x86)", "nachtzorgcondities, 4,0 m"),
):
    namen = [kort(n) for n in d.index]
    kleuren = [GROEN if v < 2000 else (ORANJE if v < 8000 else ROOD) for v in d["lat"]]
    balken = ax.barh(namen, d["lat"] / 1000, color=kleuren, height=0.6)
    ax.axvline(2.0, color=ROOD, linestyle="--", linewidth=2)
    for b, v in zip(balken, d["lat"]):
        ax.text(v / 1000 + 0.6, b.get_y() + b.get_height() / 2, f"{v/1000:.1f} s",
                va="center", fontsize=9.5,
                fontweight="bold" if v < 2000 else "normal")
    ax.set_title(f"{titel}\n{onderschrift}", fontsize=11)
    ax.set_xlabel("gemiddelde latentie per uiting (s)")
    ax.set_xlim(0, 38)

ax1.text(2.3, len(pi_e) - 0.4, "eis: 2,0 s", color=ROOD, fontweight="bold", fontsize=9.5)
fig.suptitle("Vosk op de Raspberry Pi haalt de responsie-eis — als enige combinatie",
             fontsize=13, fontweight="bold", y=0.99)
fig.tight_layout(rect=(0, 0.03, 1, 0.94))
fig.text(0.5, 0.005, "Let op: de twee platforms zijn onder verschillende condities gemeten "
                     "(1,0 m tegen 4,0 m); de vergelijking is indicatief.",
         ha="center", fontsize=8.5, style="italic", color=GRIJS)
fig.savefig(UIT / "fig1_latentie_per_engine.png", dpi=200)
plt.close(fig)
print("fig1 klaar")

# ---------------------------------------------------------------- figuur 2
# Kwaliteit tegen snelheid: waar ligt het haalbare gebied?
fig, ax = plt.subplots(figsize=(9, 6))
ax.axhspan(0, 25, xmin=0, xmax=2.0 / 14, color=GROEN, alpha=0.10, zorder=0)
for d, merk, kleur, label in ((pi_e, "o", BLAUW, "Raspberry Pi (1,0 m)"),
                              (lp_e, "s", ORANJE, "LattePanda (4,0 m)")):
    for naam, r in d.iterrows():
        haalt = r["lat"] < 2000 and r["wer"] < 25
        ax.scatter(r["lat"] / 1000, r["wer"], s=230 if haalt else 110, marker=merk,
                   color=GROEN if haalt else kleur, zorder=3, edgecolor="white", linewidth=1.5,
                   label=label if naam == d.index[0] else None)
        ax.annotate(kort(naam), (r["lat"] / 1000, r["wer"]), textcoords="offset points",
                    xytext=(10, 6), fontsize=8.5, fontweight="bold" if haalt else "normal")
ax.axhline(25, color=ROOD, linestyle="--", linewidth=1.6)
ax.axvline(2.0, color=ROOD, linestyle="--", linewidth=1.6)
ax.text(0.15, 27, "WER-eis: 25%", color=ROOD, fontsize=9, fontweight="bold")
ax.text(2.2, 70, "latentie-eis: 2 s", color=ROOD, fontsize=9, fontweight="bold", rotation=90)
ax.text(0.15, 3, "haalbaar", color=GROEN, fontsize=11, fontweight="bold")
ax.set_xlabel("latentie (seconden, lager is beter)")
ax.set_ylabel("WER (%, lager is beter)")
ax.set_xlim(0, 14)
ax.set_ylim(0, 80)
ax.legend(loc="upper right", frameon=False)
ax.set_title("Eén combinatie valt in het haalbare gebied\nVosk op de Pi: 1,9 s bij 6,6% WER")
fig.tight_layout()
fig.savefig(UIT / "fig2_kwaliteit_vs_snelheid.png", dpi=200)
plt.close(fig)
print("fig2 klaar")

# ---------------------------------------------------------------- figuur 3
# ARM tegen x86, met de gecorrigeerde cijfers en beide maten.
r_lat = pi[(pi["test_id"] == "T2.2") & (pi["engine"] == "whisper-small")
           & (pi["afstand_m"] == 4.0) & pi["latentie_ms"].notna()]["latentie_ms"]
l_lat = lp_vers[(lp_vers["device"] == "LP1") & (lp_vers["engine"] == "whisper-small")
                & lp_vers["latentie_ms"].notna()]["latentie_ms"]

fig, ax = plt.subplots(figsize=(8.4, 5.4))
x = [0, 1]
breedte = 0.34
gem = [r_lat.mean() / 1000, l_lat.mean() / 1000]
med = [r_lat.median() / 1000, l_lat.median() / 1000]
b1 = ax.bar([i - breedte / 2 for i in x], gem, breedte, label="gemiddelde", color=BLAUW)
b2 = ax.bar([i + breedte / 2 for i in x], med, breedte, label="mediaan", color=GROEN)
for balken, waarden in ((b1, gem), (b2, med)):
    for b, v in zip(balken, waarden):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.25, f"{v:.1f} s",
                ha="center", fontweight="bold", fontsize=10)
ax.set_xticks(x)
ax.set_xticklabels(["Raspberry Pi 5\nARM Cortex-A76", "LattePanda 3 Delta\nIntel Celeron N5105"])
ax.axhline(2.0, color=ROOD, linestyle="--", linewidth=1.6)
ax.text(0.5, 2.35, "eis: 2 s", color=ROOD, fontsize=9.5, fontweight="bold", ha="center")
ax.set_ylabel("latentie per uiting (s)")
ax.set_ylim(0, max(gem) * 1.42)
ax.legend(frameon=False, loc="upper left")
verschil_gem = (gem[1] / gem[0] - 1) * 100
verschil_med = (med[1] / med[0] - 1) * 100
ax.set_title(f"x86 is {verschil_gem:.0f}% langzamer op het gemiddelde, "
             f"{verschil_med:.0f}% op de mediaan\nwhisper small, 4,0 m — eerder gerapporteerd als 67%")
fig.tight_layout()
fig.savefig(UIT / "fig3_arm_vs_x86.png", dpi=200)
plt.close(fig)
print("fig3 klaar")

# ---------------------------------------------------------------- figuur 4
# Energie: rust tegen last, en het gewicht van rust in een nacht.
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5))
labels = ["Raspberry Pi 5\n(RASP1)", "LattePanda\n(LP1)"]
rust = [3.4, 7.76]
last = [12.4, None]
x = range(len(labels))
ax1.bar([i - 0.2 for i in x], rust, 0.4, label="rust", color=GROEN)
ax1.bar([0.2], [last[0]], 0.4, label="volle last", color=ROOD)
for i, v in enumerate(rust):
    ax1.text(i - 0.2, v + 0.25, f"{v:.2f} W", ha="center", fontweight="bold")
ax1.text(0.2, last[0] + 0.25, f"{last[0]:.1f} W", ha="center", fontweight="bold")
ax1.text(1.2, 0.6, "nog niet\ngemeten", ha="center", fontsize=9, style="italic", color=GRIJS)
ax1.set_xticks(list(x))
ax1.set_xticklabels(labels)
ax1.set_ylabel("vermogen (W)")
ax1.set_ylim(0, 14.5)
ax1.legend(frameon=False)
ax1.set_title("De LattePanda verbruikt in rust ruim het dubbele")

# rechterpaneel: waar gaat de energie van een nacht heen?
uren_rust, wh_rekenwerk = 8, 0.5
wh_rust = 3.4 * uren_rust
ax2.bar(["8 uur wachten", "50 hulpvragen"], [wh_rust, wh_rekenwerk], color=[GRIJS, BLAUW], width=0.5)
ax2.text(0, wh_rust + 0.7, f"{wh_rust:.1f} Wh", ha="center", fontweight="bold", fontsize=12)
ax2.text(1, wh_rekenwerk + 0.7, f"{wh_rekenwerk:.1f} Wh", ha="center", fontweight="bold", fontsize=12)
ax2.set_ylabel("energie per nacht (Wh)")
ax2.set_ylim(0, wh_rust * 1.25)
ax2.set_title("Rustverbruik weegt ongeveer 50x zwaarder\ndan al het rekenwerk van een nacht (Pi 5)")
fig.tight_layout()
fig.savefig(UIT / "fig4_energie.png", dpi=200)
plt.close(fig)
print("fig4 klaar")

# ---------------------------------------------------------------- figuur 5
# Het volgorde-effect: waarom de eerdere cijfers te hoog waren.
oud = lp[(lp["dag"] == 14) & lp["latentie_ms"].notna()].groupby("engine")["latentie_ms"].mean()
nieuw = lp_vers[(lp_vers["device"] == "LP1")
                & lp_vers["latentie_ms"].notna()].groupby("engine")["latentie_ms"].mean()
v = pd.DataFrame({"oud": oud, "nieuw": nieuw}).dropna().sort_values("oud")
fig, ax = plt.subplots(figsize=(10, 5.4))
y = range(len(v))
ax.barh([i + 0.2 for i in y], v["oud"] / 1000, 0.38, label="14 okt: zes engines aaneengesloten",
        color=ROOD, alpha=0.85)
ax.barh([i - 0.2 for i in y], v["nieuw"] / 1000, 0.38, label="16 okt: verse runs met rust ertussen",
        color=GROEN)
for i, (_, r) in enumerate(v.iterrows()):
    pct = (r["nieuw"] / r["oud"] - 1) * 100
    ax.text(r["oud"] / 1000 + 0.35, i + 0.2, f"{r['oud']/1000:.1f} s", va="center", fontsize=9)
    ax.text(r["nieuw"] / 1000 + 0.35, i - 0.2, f"{r['nieuw']/1000:.1f} s  ({pct:+.0f}%)",
            va="center", fontsize=9, fontweight="bold", color=GROEN)
ax.set_yticks(list(y))
ax.set_yticklabels([kort(n) for n in v.index])
ax.set_xlabel("gemiddelde latentie per uiting (s)")
ax.set_xlim(0, v["oud"].max() / 1000 * 1.3)
ax.legend(frameon=False, loc="lower right")
ax.set_title("De meetvolgorde beïnvloedt de latentie tot 34%\neen aaneengesloten reeks geeft "
             "systematisch te trage cijfers")
fig.tight_layout()
fig.savefig(UIT / "fig5_volgorde_effect.png", dpi=200)
plt.close(fig)
print("fig5 klaar")

# ---------------------------------------------------------------- figuur 6
# Replicatie: hoe goed komen twee identieke devices overeen?
paren = []
pi_w = pi[pi["wer_pct"].notna()]
for (tid, afst), g in pi_w[pi_w["engine"] == "whisper-small"].groupby(["test_id", "afstand_m"]):
    d = g.groupby("device")["wer_pct"].mean()
    if {"RASP1", "RASP2"}.issubset(d.index):
        paren.append((f"Pi {tid} {afst:.1f}m", abs(d["RASP1"] - d["RASP2"])))
lpw = lp_vers[(lp_vers["engine"] == "whisper-small") & lp_vers["wer_pct"].notna()]
d = lpw.groupby("device")["wer_pct"].mean()
if {"LP1", "LP2"}.issubset(d.index):
    paren.append(("LattePanda T2.2 4,0m", abs(d["LP1"] - d["LP2"])))

paren.sort(key=lambda t: t[1])
fig, ax = plt.subplots(figsize=(10.5, 5.6))
namen = [p[0] for p in paren]
waarden = [p[1] for p in paren]
kleuren = [GROEN if w <= 5 else ROOD for w in waarden]
# Een verschil van 0,00 pp levert een onzichtbare balk; een minimumlengte houdt de rij leesbaar.
getekend = [max(w, 0.06) for w in waarden]
balken = ax.barh(namen, getekend, color=kleuren, height=0.6)
ax.axvline(5.0, color=ROOD, linestyle="--", linewidth=2)
ax.text(5.2, -0.45, "drempel: 5 pp", color=ROOD, fontweight="bold", fontsize=9.5)
for b, w in zip(balken, waarden):
    ax.text(max(w, 0.06) + 0.25, b.get_y() + b.get_height() / 2, f"{w:.2f} pp",
            va="center", fontsize=9.5, fontweight="bold" if w <= 5 else "normal")
ax.set_xlabel("verschil in gemiddelde WER tussen de twee devices (procentpunt)")
ax.set_xlim(0, max(waarden) * 1.22)
ax.set_title("Replicatie slaagt op de LattePanda's, niet overal op de Pi's\n"
             "de afwijkingen zitten waar maar één meetronde is gedaan")
fig.tight_layout()
fig.savefig(UIT / "fig6_replicatie.png", dpi=200)
plt.close(fig)
print("fig6 klaar")

print(f"\nAlle figuren in {UIT}")
