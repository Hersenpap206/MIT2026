"""Maakt de figuren voor de werkgroeppresentatie, gericht op niet-technische lezers.

Uitgangspunt: elke figuur legt één ding uit en bevat zo weinig mogelijk. Geen jargon in de
aslabels, Nederlandse opschriften, en bij elke figuur hoort een conclusieregel in de presentatie
zelf. De data komt uit de metingen van oktober en november 2026; de waarden staan hier expliciet
in de code, zodat de figuren reproduceerbaar zijn zonder de hele meetset.

Gebruik:
    py -3.12 analysis/presentatie_figuren.py "03 Projectplan en WP-documenten/figuren_wp3"
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

INKT = "#16202b"
ZACHT = "#5b6b7c"
BLAUW = "#1f4e79"
GROEN = "#2e7d32"
ROOD = "#c62828"
ORANJE = "#ef6c00"
LIJN = "#dfe5ec"
VLAK = "#f5f8fb"

plt.rcParams.update({
    "font.family": "Segoe UI",
    "font.size": 12,
    "text.color": INKT,
    "axes.labelcolor": INKT,
    "axes.edgecolor": LIJN,
    "xtick.color": ZACHT,
    "ytick.color": ZACHT,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def opslaan(fig, doel: pathlib.Path, naam: str) -> None:
    pad = doel / naam
    fig.savefig(pad, dpi=160, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"  {naam}")


def strip(ax, onder=True):
    for kant in ("top", "right", "left"):
        ax.spines[kant].set_visible(False)
    ax.spines["bottom"].set_visible(onder)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=LIJN, linewidth=0.9)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- 1. de drie lagen
def fig_lagen(doel):
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4.4)
    ax.axis("off")

    lagen = [
        ("1. Poortwachter", "merkt dat er\ngesproken wordt", "de hele nacht aan", BLAUW,
         "werkt"),
        ("2. Transcriptie", "schrijft op\nwat er gezegd is", "alleen als laag 1\nopengaat", ORANJE,
         "knelpunt"),
        ("3. Intentie", "kiest de\njuiste actie", "een keer per\nhulpvraag", ROOD,
         "onopgelost"),
    ]
    breedte, x0 = 2.9, 0.4
    for i, (titel, taak, frequentie, kleur, stand) in enumerate(lagen):
        x = x0 + i * 3.55
        ax.add_patch(Rectangle((x, 1.25), breedte, 2.0, facecolor=VLAK,
                               edgecolor=kleur, linewidth=2.2, zorder=2))
        ax.text(x + breedte / 2, 2.92, titel, ha="center", va="center",
                fontsize=13.5, fontweight="bold", color=kleur, zorder=3)
        ax.text(x + breedte / 2, 2.25, taak, ha="center", va="center",
                fontsize=11.5, color=INKT, zorder=3)
        ax.text(x + breedte / 2, 1.55, frequentie, ha="center", va="center",
                fontsize=10.5, color=ZACHT, style="italic", zorder=3)
        ax.text(x + breedte / 2, 0.82, stand, ha="center", va="center",
                fontsize=12, fontweight="bold", color=kleur, zorder=3)
        if i < 2:
            ax.add_patch(FancyArrowPatch((x + breedte + 0.08, 2.25),
                                         (x + breedte + 0.57, 2.25),
                                         arrowstyle="-|>", mutation_scale=18,
                                         color=ZACHT, linewidth=1.8))

    ax.text(5.5, 3.95, "Wat het apparaat achter elkaar moet doen",
            ha="center", fontsize=15, fontweight="bold", color=INKT)
    ax.text(5.5, 0.28, "Laag 1 draait acht uur per nacht en mag dus bijna niets kosten. "
                       "Laag 2 is duur maar wordt zelden gebruikt.",
            ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p1_drie_lagen.png")


# ------------------------------------------- 2. waarom de volumeregeling de stilte sloopt
def fig_volumeregeling(doel):
    fig, assen = plt.subplots(1, 2, figsize=(11, 4.6))
    fig.suptitle("Waarom de automatische volumeregeling in een stille kamer misgaat",
                 fontsize=15, fontweight="bold", y=1.02)

    scenarios = [
        ("Kamer met geluid", "De regeling doet wat zij moet doen",
         [("achtergrond", 0.34, ZACHT), ("spraak", 0.86, GROEN)], GROEN,
         "spraak komt er\nduidelijk boven uit"),
        ("Stille kamer", "De regeling draait open en tilt de ruis mee",
         [("achtergrond", 0.78, ROOD), ("spraak", 0.92, GROEN)], ROOD,
         "de drempel gaat af\nop de ruis zelf"),
    ]
    for ax, (titel, onder, balken, kleur, note) in zip(assen, scenarios):
        ax.set_xlim(0, 2.4)
        ax.set_ylim(0, 1.32)
        ax.axis("off")
        ax.text(1.2, 1.24, titel, ha="center", fontsize=13.5, fontweight="bold", color=kleur)
        ax.text(1.2, 1.13, onder, ha="center", fontsize=10.5, color=ZACHT)
        for i, (label, hoogte, kl) in enumerate(balken):
            x = 0.55 + i * 0.85
            ax.add_patch(Rectangle((x, 0.08), 0.5, hoogte, facecolor=kl, alpha=0.85,
                                   edgecolor="none"))
            ax.text(x + 0.25, 0.01, label, ha="center", fontsize=11, color=ZACHT)
        ax.axhline(0.72, xmin=0.12, xmax=0.95, color=ROOD, linestyle="--", linewidth=1.8)
        ax.text(2.33, 0.735, "drempel", ha="right", fontsize=10.5, color=ROOD,
                fontweight="bold")
        ax.text(1.2, -0.13, note, ha="center", fontsize=11, color=kleur, fontweight="bold")

    fig.text(0.5, -0.24, "De microfoon versterkt zacht geluid automatisch. Is er niets te horen, "
                         "dan versterkt zij de ruis —\nen slaat een drempel op geluidssterkte "
                         "de hele nacht alarm. Gemeten: 840 keer per uur.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p2_volumeregeling.png")


# --------------------------------------------- 3. sterktedrempel versus inhoudelijke poort
def fig_detectoren(doel):
    fig, ax = plt.subplots(figsize=(10, 4.3))
    condities = ["Regeling aan\n(fabrieksstand)", "Regeling stilgezet", "Versterking op nul",
                 "Onbewerkte\nmicrofoon"]
    sterkte = [23.8, 66.3, 0.0, 0.0]
    inhoud = [0.0, 0.0, 0.0, 0.0]
    y = range(len(condities))
    hoogte = 0.36
    ax.barh([i + hoogte / 2 for i in y], sterkte, height=hoogte, color=ROOD, alpha=0.88,
            label="drempel op geluidssterkte")
    ax.barh([i - hoogte / 2 for i in y], inhoud, height=hoogte, color=GROEN, alpha=0.88,
            label="detector die naar de vorm van het geluid kijkt")
    for i, v in enumerate(sterkte):
        ax.text(v + 1.2, i + hoogte / 2, f"{v:.1f} %".replace(".", ","), va="center",
                fontsize=11.5, color=ROOD, fontweight="bold")
    for i in y:
        ax.text(1.2, i - hoogte / 2, "0 %", va="center", fontsize=11.5, color=GROEN,
                fontweight="bold")
    ax.set_yticks(list(y))
    ax.set_yticklabels(condities, fontsize=11.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 76)
    ax.set_xlabel("deel van de nacht waarin de detector onterecht afgaat")
    ax.set_title("Hetzelfde geluid, twee soorten detector", pad=14)
    strip(ax)
    ax.legend(loc="lower right", frameon=False, fontsize=11)
    fig.text(0.5, -0.09, "De inhoudelijke detector gaat in geen enkele stand vals af, "
                         "ongeacht wat de volumeregeling doet.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p3_detectoren.png")


# ----------------------------------------------------- 4. de marge: aangenomen vs gemeten
def fig_marge(doel):
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    labels = ["Aangenomen\n(verkeerd gemeten)", "Nodig voor de eis", "Gemeten op\neen echte stem"]
    waarden = [2.5, 7.5, 18.93]
    kleuren = [ROOD, ORANJE, GROEN]
    balken = ax.bar(labels, waarden, color=kleuren, alpha=0.88, width=0.52)
    for b, v, kl in zip(balken, waarden, kleuren):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v:.1f} dB".replace(".", ","),
                ha="center", fontsize=13, fontweight="bold", color=kl)
    ax.axhline(7.5, color=ORANJE, linestyle="--", linewidth=1.6, zorder=0)
    ax.set_ylim(0, 22)
    ax.set_ylabel("hoeveel de fluistering boven de ruis uitkomt")
    ax.set_title("Hoeveel marge heeft een fluistering boven de nachtruis?", pad=14)
    for kant in ("top", "right"):
        ax.spines[kant].set_visible(False)
    ax.grid(axis="y", color=LIJN, linewidth=0.9)
    ax.set_axisbelow(True)
    fig.text(0.5, -0.17, "De oorspronkelijke 2,5 dB kwam uit twee metingen bij een verschillende "
                         "versterking.\nEerlijk gemeten is de marge ruim twee keer zo groot als "
                         "de eis vraagt.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p4_marge.png")


# ------------------------------------------------------------- 5. de gevoeligheidscurve
def fig_curve(doel):
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    marge = [2.5, 5.0, 7.5, 10.0, 15.0, 20.0]
    wer = [43.41, 32.94, 24.78, 20.38, 16.27, 14.19]
    ax.plot(marge, wer, marker="o", color=BLAUW, linewidth=2.4, markersize=7,
            label="gemeten foutpercentage")
    ax.axhline(25, color=ROOD, linestyle="--", linewidth=1.8)
    ax.text(20.2, 25.8, "eis: 25 %", color=ROOD, fontsize=11.5, fontweight="bold", ha="right")
    ax.axvline(18.93, color=GROEN, linestyle=":", linewidth=2)
    ax.text(18.5, 41, "gemeten\nmarge", color=GROEN, fontsize=11, fontweight="bold",
            ha="right", va="top")
    ax.fill_between([7.5, 21], 0, 25, color=GROEN, alpha=0.07)
    ax.set_xlim(1.5, 21)
    ax.set_ylim(10, 47)
    ax.set_xlabel("marge van de spraak boven de ruis (dB)")
    ax.set_ylabel("fout in de opgeschreven tekst (%)")
    ax.set_title("Hoe meer marge, hoe beter de computer verstaat", pad=14)
    for kant in ("top", "right"):
        ax.spines[kant].set_visible(False)
    ax.grid(color=LIJN, linewidth=0.9)
    ax.set_axisbelow(True)
    fig.text(0.5, -0.11, "Vanaf ongeveer 7,5 dB marge wordt de eis gehaald. "
                         "De gemeten marge ligt daar ruim boven —\nde ruis is dus niet het "
                         "probleem.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p5_curve.png")


# --------------------------------------------------- 6. synthetische stem versus echte stem
def fig_stem(doel):
    fig, ax = plt.subplots(figsize=(9, 4.2))
    labels = ["Nagemaakte stem\n(computerspraak)", "Echte fluisterstem"]
    waarden = [14.10, 41.05]
    balken = ax.bar(labels, waarden, color=[GROEN, ROOD], alpha=0.88, width=0.46)
    for b, v in zip(balken, waarden):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.1, f"{v:.1f} %".replace(".", ","),
                ha="center", fontsize=14, fontweight="bold",
                color=GROEN if v < 25 else ROOD)
    ax.axhline(25, color=ROOD, linestyle="--", linewidth=1.8)
    ax.text(1.46, 26.3, "eis: 25 %", color=ROOD, fontsize=11.5, fontweight="bold", ha="right")
    ax.set_ylim(0, 50)
    ax.set_ylabel("fout in de opgeschreven tekst (%)")
    ax.set_title("Een echte fluistering is veel moeilijker dan een nagemaakte", pad=14)
    for kant in ("top", "right"):
        ax.spines[kant].set_visible(False)
    ax.grid(axis="y", color=LIJN, linewidth=0.9)
    ax.set_axisbelow(True)
    fig.text(0.5, -0.17, "Bij een echte fluistering trillen de stembanden niet mee. "
                         "Juist die trilling is waar de computer\nop let — en de nagemaakte "
                         "stem had hem wel. Alle eerdere cijfers waren daardoor te gunstig.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p6_stem.png")


# ----------------------------------------------------------- 7. de apparaten vergeleken
def fig_apparaten(doel):
    fig, ax = plt.subplots(figsize=(9.8, 4.0))
    namen = ["Raspberry Pi 5", "LattePanda 3 Delta", "STM32MP257F-EV1"]
    ms = [1845, 2880, 11424]
    kleuren = [GROEN, GROEN, ROOD]
    balken = ax.barh(namen, ms, color=kleuren, alpha=0.88, height=0.5)
    for b, v in zip(balken, ms):
        ax.text(v + 180, b.get_y() + b.get_height() / 2, f"{v:,} ms".replace(",", "."),
                va="center", fontsize=12.5, fontweight="bold",
                color=GROEN if v < 2000 else (ZACHT if v < 5000 else ROOD))
    ax.axvline(2000, color=ROOD, linestyle="--", linewidth=1.8)
    ax.text(2150, 2.42, "eis: binnen 2.000 ms", color=ROOD, fontsize=11.5, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 13600)
    ax.set_xlabel("tijd om een hulpvraag van vijf seconden te verwerken")
    ax.set_title("Hoe snel verwerken de drie apparaten dezelfde hulpvraag?", pad=14)
    strip(ax)
    fig.text(0.5, -0.12, "Het zuinige microcontrollerbord is zes keer trager dan de Raspberry Pi "
                         "en loopt onherstelbaar achter\nop de spraak. Een eigen "
                         "besturingssysteem of de AI-chip aan boord verandert dat niet.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p7_apparaten.png")


# ------------------------------------------------------- 8. veilig falen bij noodsituaties
def fig_veilig(doel):
    fig, ax = plt.subplots(figsize=(9.6, 3.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.4)
    ax.axis("off")
    ax.text(5, 3.1, "Wat gebeurt er met een noodsituatie die de computer niet goed verstaat?",
            ha="center", fontsize=14, fontweight="bold")

    vakken = [
        (0.3, GROEN, "Escaleert naar\nde nachtdienst", "de hulpvraag is herkend"),
        (3.55, BLAUW, "Vraagt door", "'ik begrijp het niet,\nkunt u het anders zeggen'"),
        (6.8, ROOD, "Verkeerde actie", "nooit voorgekomen\nin geen enkele meting"),
    ]
    for x, kleur, titel, onder in vakken:
        rand = 2.6 if kleur == ROOD else 2.2
        ax.add_patch(Rectangle((x, 0.55), 2.9, 1.9, facecolor=VLAK, edgecolor=kleur,
                               linewidth=rand, zorder=2,
                               linestyle="--" if kleur == ROOD else "solid"))
        ax.text(x + 1.45, 1.92, titel, ha="center", va="center", fontsize=13,
                fontweight="bold", color=kleur, zorder=3)
        ax.text(x + 1.45, 1.12, onder, ha="center", va="center", fontsize=10.5,
                color=ZACHT, zorder=3)
    ax.text(8.25, 0.28, "0 keer", ha="center", fontsize=13, fontweight="bold", color=ROOD)
    fig.text(0.5, -0.07, "De beslislogica escaleert alleen bij duidelijk bewijs en vraagt "
                         "anders door. Daardoor kan een\nniet-herkende noodsituatie wel "
                         "vertraging oplopen, maar nooit als praatje worden afgedaan.",
             ha="center", fontsize=11, color=ZACHT)
    opslaan(fig, doel, "p8_veilig_falen.png")


def main() -> None:
    doel = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    doel.mkdir(parents=True, exist_ok=True)
    print(f"figuren naar {doel}:")
    fig_lagen(doel)
    fig_volumeregeling(doel)
    fig_detectoren(doel)
    fig_marge(doel)
    fig_curve(doel)
    fig_stem(doel)
    fig_apparaten(doel)
    fig_veilig(doel)


if __name__ == "__main__":
    main()
