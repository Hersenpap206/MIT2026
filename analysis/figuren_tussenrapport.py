"""Figuren voor de tussenrapportage en de werkgroeppresentatie van 9 november 2026.

Vier figuren die de bevindingen van 8 en 9 november dragen en die in de eerdere set ontbraken:
de WER op 1,0 meter met onzekerheidsmarges, het tegengestelde faalpatroon van de engines per
categorie, de valse alarmen over de nacht, en het kanaalverschil van de microfoon.

Gebruik (vanuit scripts/):
    py -3.12 analysis/figuren_tussenrapport.py <data-dir> <nachtmeting-csv> <uitvoermap>
"""

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATA, NACHT, UIT = (Path(a) for a in sys.argv[1:4])
UIT.mkdir(parents=True, exist_ok=True)

BLAUW, GROEN, ROOD, GRIJS, ORANJE = "#1f4e79", "#2e7d32", "#c62828", "#757575", "#ef6c00"
plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.grid": True, "grid.alpha": 0.25,
    "grid.linestyle": "-", "axes.axisbelow": True,
})
KORT = {"faster-whisper-small-float32": "faster-whisper\nfloat32",
        "faster-whisper-small-int8": "faster-whisper\nint8",
        "whisper-small": "whisper-small", "vosk": "vosk",
        "whisper-base": "whisper-base", "whisper-tiny": "whisper-tiny"}


def lees():
    fr = []
    for p in DATA.rglob("*.csv"):
        d = pd.read_csv(p)
        if "run_id" in d.columns:
            fr.append(d)
    df = pd.concat(fr, ignore_index=True).drop_duplicates(subset=["run_id"], keep="first")
    return df[df.testcorpus_uiting_id.notna()].copy()


def interval(s):
    se = s.std(ddof=1) / np.sqrt(len(s))
    return s.mean(), 1.96 * se


df = lees()
df["stem"] = df.device.map({"LP1": "vrouw", "LP2": "man"})
SLEUTEL = ["stem", "testcorpus_uiting_id"]

# categorie per uiting uit de bronbestanden
cat = {}
for s in ("T2.2", "T2.2M"):
    with open(Path("corpus") / f"bron_{s}.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cat[("vrouw" if s == "T2.2" else "man", r["uiting_id"])] = r["categorie"]
df["categorie"] = [cat.get((a, b)) for a, b in zip(df.stem, df.testcorpus_uiting_id)]

d10 = df[(df.test_id == "T2.2") & (df.afstand_m == 1.0)]

# ---- figuur A: WER op 1,0 m met marges -------------------------------------
rijen = []
for eng, g in d10.groupby("engine"):
    m, h = interval(g.groupby(SLEUTEL).wer_pct.mean())
    rijen.append((KORT.get(eng, eng), m, h))
rijen.sort(key=lambda r: r[1])
fig, ax = plt.subplots(figsize=(8.2, 4.4))
y = np.arange(len(rijen))
kleur = [GROEN if m + h < 25 else (ROOD if m - h > 25 else ORANJE) for _, m, h in rijen]
ax.barh(y, [r[1] for r in rijen], xerr=[r[2] for r in rijen], color=kleur,
        error_kw={"ecolor": GRIJS, "capsize": 4, "lw": 1.2}, height=0.62)
ax.axvline(25, color=ROOD, ls="--", lw=1.4)
ax.text(25.8, 0.1, "eis: 25 %", color=ROOD, fontsize=9.5, va="center")
ax.set_yticks(y, [r[0] for r in rijen], fontsize=9)
ax.set_xlabel("woordfoutpercentage (WER) met 95 %-interval")
ax.set_title("Nachtzorgspraak op 1,0 meter, 120 uitingen per engine", loc="left")
ax.set_xlim(0, 85)
fig.tight_layout()
fig.savefig(UIT / "figA_wer_1meter.png", dpi=150)
plt.close(fig)

# ---- figuur B: tegengesteld faalpatroon per categorie ----------------------
CATS = ["gefluisterd", "emotioneel", "incompleet"]
toon = ["vosk", "faster-whisper-small-int8", "whisper-small"]
fig, ax = plt.subplots(figsize=(8.2, 4.2))
b = 0.26
for i, eng in enumerate(toon):
    waarden, marges = [], []
    for c in CATS:
        s = d10[(d10.engine == eng) & (d10.categorie == c)].groupby(SLEUTEL).wer_pct.mean()
        m, h = interval(s)
        waarden.append(m); marges.append(h)
    ax.bar(np.arange(len(CATS)) + (i - 1) * b, waarden, b, yerr=marges,
           label=KORT.get(eng, eng).replace("\n", " "),
           color=[ROOD, BLAUW, GROEN][i], error_kw={"ecolor": GRIJS, "capsize": 3, "lw": 1})
ax.axhline(25, color=ROOD, ls="--", lw=1.4)
ax.text(2.45, 26.5, "eis: 25 %", color=ROOD, fontsize=9.5)
ax.set_xticks(np.arange(len(CATS)), CATS)
ax.set_ylabel("woordfoutpercentage (WER)")
ax.set_ylim(0, None)
ax.set_title("De engines falen op tegengestelde categorieën — 1,0 meter")
ax.legend(frameon=False, fontsize=9.5)
fig.tight_layout()
fig.savefig(UIT / "figB_categorieen.png", dpi=150)
plt.close(fig)

# ---- figuur C: valse alarmen over de nacht --------------------------------
n = pd.read_csv(NACHT)
n["t"] = pd.to_datetime(n.tijd)
fig, ax = plt.subplots(figsize=(8.6, 3.8))
for kol, lab, kl in (("or_250_gebeurtenissen", "drempel 250 (ruim)", ROOD),
                     ("or_600_gebeurtenissen", "drempel 600", ORANJE),
                     ("and_250_gebeurtenissen", "strengste instelling", BLAUW)):
    ax.plot(n.t, n[kol].rolling(10, min_periods=1).mean(), lw=1.6, label=lab, color=kl)
ax.set_ylabel("valse detecties per minuut")
ax.set_xlabel("acht uur in een lege kamer, 8 op 9 november")
ax.set_title("Geen enkele instelling levert een rustige minuut")
ax.legend(frameon=False, fontsize=9.5)
import matplotlib.dates as mdates
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
fig.tight_layout()
fig.savefig(UIT / "figC_nacht.png", dpi=150)
plt.close(fig)

# ---- figuur D: het kanaalverschil van de microfoon ------------------------
# Gemeten op 9 november: een opname van 30 s over alle zes kanalen tegelijk.
kanalen = ["kanaal 0\n(AGC, beamformd)", "ruwe microfoons\n(kanaal 1-4)"]
niveau, detecties = [-39.26, -60.84], [92, 0]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.6, 3.8))
a1.bar(kanalen, niveau, color=[ROOD, GROEN], width=0.55)
a1.set_ylabel("ruisvloer (dBFS) — lager is stiller")
a1.set_title("Zelfde kamer, zelfde moment")
a1.set_ylim(-70, 0)
for i, v in enumerate(niveau):
    a1.text(i, v + 2.5, f"{v:.1f}", ha="center", fontsize=11, fontweight="bold")
a2.bar(kanalen, detecties, color=[ROOD, GROEN], width=0.55)
a2.set_ylabel("valse detecties in 30 s")
a2.set_title("Zelfde detector, zelfde drempel")
for i, v in enumerate(detecties):
    a2.text(i, v + 2, str(v), ha="center", fontsize=11, fontweight="bold")
fig.suptitle("De versterkingsregeling van de microfoon maakt de detectie onbruikbaar",
             fontsize=12, fontweight="bold")
fig.tight_layout()
fig.savefig(UIT / "figD_kanaal.png", dpi=150)
plt.close(fig)

print("figuren geschreven naar", UIT)
for f in sorted(UIT.glob("fig[ABCD]*.png")):
    print(f"  {f.name}  {f.stat().st_size // 1024} kB")
