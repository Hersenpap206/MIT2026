"""Zet een projectdocument in markdown om naar HTML in de huisstijl, voor een deelbare PDF.

Bewust minimaal: het dekt de opmaak die in de projectdocumenten voorkomt (koppen, tabellen, vet,
cursief, code, lijsten, citaten, horizontale lijnen) en niets meer. Dat is genoeg om een rapport
leesbaar te delen zonder een externe markdown-bibliotheek te installeren.

Gebruik:
    py -3.12 analysis/md_naar_html.py <bestand.md> [uitvoer.html]
"""

import html as _html
import re
import sys
from pathlib import Path

STIJL = """
:root{--inkt:#16202b;--zacht:#5b6b7c;--lijn:#dfe5ec;--vlak:#f5f8fb;--blauw:#1f4e79;--rood:#c62828}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--inkt);font-family:"Segoe UI",system-ui,sans-serif;
     font-size:16px;line-height:1.62}
.blad{max-width:900px;margin:0 auto;padding:54px 64px 80px}
h1{font-size:33px;line-height:1.2;margin:0 0 6px;color:var(--blauw)}
h2{font-size:24px;margin:46px 0 6px;padding-top:22px;border-top:3px solid var(--lijn);line-height:1.25}
h3{font-size:19px;margin:30px 0 6px}
h4{font-size:16.5px;margin:22px 0 4px;color:var(--zacht)}
p{margin:12px 0}
ul,ol{margin:12px 0;padding-left:26px}
li{margin:5px 0}
table{width:100%;border-collapse:collapse;margin:22px 0;font-size:14.8px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--lijn);vertical-align:top}
th{background:var(--vlak);font-weight:600;font-size:13px;text-transform:uppercase;
   letter-spacing:.04em;color:var(--zacht)}
code{background:var(--vlak);padding:1px 5px;border-radius:4px;font-size:14px}
pre{background:var(--vlak);padding:14px 16px;border-radius:8px;overflow-x:auto;font-size:14px}
blockquote{margin:22px 0;padding:14px 22px;background:var(--vlak);border-left:5px solid var(--blauw);
           border-radius:0 8px 8px 0}
blockquote p:first-child{margin-top:0} blockquote p:last-child{margin-bottom:0}
hr{border:0;border-top:3px solid var(--lijn);margin:42px 0}
strong{color:var(--inkt)}
@media print{.blad{max-width:none;padding:0 14mm}h2,h3{page-break-after:avoid}
             table,blockquote,pre{page-break-inside:avoid}}
"""


def inline(s: str) -> str:
    s = _html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def omzetten(md: str) -> str:
    uit, i, regels = [], 0, md.split("\n")
    lijst = None

    def sluit_lijst():
        nonlocal lijst
        if lijst:
            uit.append(f"</{lijst}>")
            lijst = None

    while i < len(regels):
        r = regels[i]
        kaal = r.strip()

        if not kaal:
            sluit_lijst(); i += 1; continue

        if kaal.startswith("```"):
            sluit_lijst(); i += 1
            blok = []
            while i < len(regels) and not regels[i].strip().startswith("```"):
                blok.append(_html.escape(regels[i])); i += 1
            uit.append("<pre>" + "\n".join(blok) + "</pre>"); i += 1; continue

        if re.fullmatch(r"-{3,}", kaal):
            sluit_lijst(); uit.append("<hr>"); i += 1; continue

        k = re.match(r"(#{1,4})\s+(.*)", kaal)
        if k:
            sluit_lijst()
            n = len(k.group(1))
            uit.append(f"<h{n}>{inline(k.group(2))}</h{n}>"); i += 1; continue

        # tabel: een kopregel gevolgd door een scheidingsregel
        if kaal.startswith("|") and i + 1 < len(regels) and re.match(r"^\|[\s:|-]+\|$", regels[i + 1].strip()):
            sluit_lijst()
            def cellen(x):
                return [c.strip() for c in x.strip().strip("|").split("|")]
            uit.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cellen(r)) + "</tr>")
            i += 2
            while i < len(regels) and regels[i].strip().startswith("|"):
                uit.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cellen(regels[i])) + "</tr>")
                i += 1
            uit.append("</table>"); continue

        if kaal.startswith(">"):
            sluit_lijst()
            blok = []
            while i < len(regels) and regels[i].strip().startswith(">"):
                blok.append(regels[i].strip().lstrip(">").strip()); i += 1
            uit.append("<blockquote>" + omzetten("\n".join(blok)) + "</blockquote>"); continue

        p = re.match(r"(\d+)\.\s+(.*)", kaal)
        b = re.match(r"[-*]\s+(.*)", kaal)
        if p or b:
            soort = "ol" if p else "ul"
            if lijst != soort:
                sluit_lijst(); uit.append(f"<{soort}>"); lijst = soort
            tekst = (p.group(2) if p else b.group(1))
            i += 1
            # vervolgregels van hetzelfde punt
            while i < len(regels) and regels[i].startswith(("   ", "\t")) and regels[i].strip():
                tekst += " " + regels[i].strip(); i += 1
            uit.append(f"<li>{inline(tekst)}</li>")
            continue

        sluit_lijst()
        blok = []
        while i < len(regels) and regels[i].strip() and not re.match(r"^(#{1,4} |\||>|```|-{3,}$|\d+\. |[-*] )", regels[i].strip()):
            blok.append(regels[i].strip()); i += 1
        uit.append("<p>" + inline(" ".join(blok)) + "</p>")

    sluit_lijst()
    return "\n".join(uit)


def main() -> None:
    bron = Path(sys.argv[1])
    doel = Path(sys.argv[2]) if len(sys.argv) > 2 else bron.with_suffix(".html")
    md = bron.read_text(encoding="utf-8")
    titel = next((l.lstrip("# ").strip() for l in md.split("\n") if l.startswith("# ")), bron.stem)
    doel.write_text(
        '<!doctype html><html lang="nl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_html.escape(titel)}</title><style>{STIJL}</style></head>"
        f'<body><div class="blad">{omzetten(md)}</div></body></html>',
        encoding="utf-8")
    print(f"{doel.name}: {doel.stat().st_size // 1024} kB")


if __name__ == "__main__":
    main()
