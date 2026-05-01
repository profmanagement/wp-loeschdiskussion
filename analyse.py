#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wikipedia Löschkandidaten – Musteranalyse
==========================================
Analysiert automatisch die deutschen Wikipedia-Löschdiskussionen und erzeugt:

  data/rohdaten.csv   — kodierte Rohdaten (eine Zeile pro Diskussion)
  docs/index.html     — interaktive HTML-Auswertung (kein Server nötig)

Aufruf:
  python3 analyse.py          Stichprobe: 180 Tage, alle 5 Tage  (~35 Abrufe, ca.  2 min)
  python3 analyse.py --30     Vollständig: letzte  30 Tage        (~23 Abrufe, ca.  1 min)
  python3 analyse.py --60     Vollständig: letzte  60 Tage        (~53 Abrufe, ca.  3 min)
  python3 analyse.py --all    Vollständig: letzte 180 Tage        (~173 Abrufe, ca. 10 min)

Keine externen Abhängigkeiten – nur Python 3.8+.
"""

import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta, datetime

# ---------------------------------------------------------------------------
# Verzeichnisse
# ---------------------------------------------------------------------------
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
SITE_DIR  = os.path.join(BASE_DIR, "docs")
CSV_PATH  = os.path.join(DATA_DIR, "rohdaten.csv")
HTML_PATH = os.path.join(SITE_DIR, "index.html")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SITE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Deutsche Monatsnamen für Wikipedia-URLs
# ---------------------------------------------------------------------------
DE_MONTHS = {
    1: "Januar",  2: "Februar", 3: "März",     4: "April",
    5: "Mai",     6: "Juni",    7: "Juli",      8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

# ---------------------------------------------------------------------------
# Modi & Zeitschätzungen
# ---------------------------------------------------------------------------
MODES = {
    "default": dict(days_back=180, step=5,  label="Stichprobe 180 Tage (alle 5 Tage)", est="ca. 2 min"),
    "30":      dict(days_back=30,  step=1,  label="Vollständig: letzte 30 Tage",        est="ca. 1 min"),
    "60":      dict(days_back=60,  step=1,  label="Vollständig: letzte 60 Tage",        est="ca. 3 min"),
    "all":     dict(days_back=180, step=1,  label="Vollständig: letzte 180 Tage",       est="ca. 10 min"),
}

def parse_mode() -> dict:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)
    if "--all" in args:
        return MODES["all"]
    if "--60" in args:
        return MODES["60"]
    if "--30" in args:
        return MODES["30"]
    return MODES["default"]

# ---------------------------------------------------------------------------
# Stichprobendaten: mind. 7 Tage alt (jüngere Seiten noch nicht abgeschlossen)
# ---------------------------------------------------------------------------
def get_sample_dates(days_back: int = 180, step: int = 5) -> list:
    today  = date.today()
    cutoff = today - timedelta(days=7)
    start  = today - timedelta(days=days_back)
    dates, current = [], start
    while current <= cutoff:
        dates.append(current)
        current += timedelta(days=step)
    return dates

# ---------------------------------------------------------------------------
# Kategoriensystem A (Löschgrund)
# ---------------------------------------------------------------------------
A_LABELS = {
    "A1": "Relevanz – Person",
    "A2": "Relevanz – Unternehmen/Org.",
    "A3": "Werblicher Charakter",
    "A4": "Fehlende Belege",
    "A5": "Geographie / Infrastruktur",
    "A6": "Redundanz / Weiterleitung",
    "A7": "Kategoriediskussion",
    "A8": "Urheberrechtsverletzung",
    "A9": "Qualitätsmangel",
    "A0": "Unklar / Sonstiges",
}

A_CODES = {
    "A1": ["relevanzkriterien", "keine relevanz", "relevanz nicht dargestellt",
           "wp:rk", "überregionale relevanz", "keine enzyklopädische relevanz",
           "relevanz als person", "relevanz als politiker", "relevanz als sportler",
           "relevanz als künstler", "relevanz als musiker", "relevanz als autor",
           "relevanz als schauspieler", "relevanz als manager",
           "relevanz als influencer", "relevanz als journalist"],
    "A2": ["relevanz des unternehmens", "relevanz der firma",
           "relevanz des vereins", "relevanz der organisation",
           "unternehmensrelevanz", "vereinsrelevanz",
           "relevanz als unternehmen", "mitarbeiterzahl",
           "umsatz", "jahresumsatz"],
    "A3": ["werbetext", "werbeflyer", "werblich", "wwni",
           "selbstdarstellung", "werbezweck", "reklame",
           "keine enzyklopädie", "werbung für"],
    "A4": ["unbelegt", "fehlende belege", "ohne belege", "keine belege",
           "belege fehlen", "einzelnachweise fehlen", "nicht belegt",
           "quellen fehlen", "keine quellen"],
    "A5": ["bahnhof", "ortsteil", "gemeinde", "dorf",
           "brücke", "bundesstraße", "autobahn", "stadtteil"],
    "A6": ["redundanz", "bereits vorhanden", "zusammenführen",
           "doppelartikel", "bereits ein artikel"],
    "A7": ["kategorie:", "umbenennung", "kategorisierung",
           "wikiprojekt kategorien", "kategoriendiskussion"],
    "A8": ["urheberrecht", "urv", "urheberrechtsverletzung",
           "copyright", "plagiat", "lizenzverstoß"],
    "A9": ["kein artikel", "mindestartikel", "unleserlich",
           "erster artikel", "neuer benutzer"],
}

# Spezifische Strukturgründe vor inhaltlichen
A_PRIORITY = ["A8", "A7", "A6", "A5", "A4", "A9", "A1", "A2", "A3", "A0"]

# ---------------------------------------------------------------------------
# Kategoriensystem B (Artikeltyp)
# ---------------------------------------------------------------------------
B_LABELS = {
    "B1": "Person (lebend)",
    "B2": "Person (historisch)",
    "B3": "Unternehmen / Organisation",
    "B4": "Veranstaltung / Event",
    "B5": "Geographie / Infrastruktur",
    "B6": "Kulturelles Werk",
    "B7": "Kategorie / intern",
    "B8": "Sonstiges",
}

# ---------------------------------------------------------------------------
# Kategoriensystem E (Ergebnis)
# ---------------------------------------------------------------------------
E_LABELS = {
    "E1": "Gelöscht",
    "E2": "Behalten",
    "E3": "LAZ",
    "E4": "BNR",
    "E5": "Weiterleitung",
    "E6": "Noch offen",
    "E7": "SLA",
}

# ---------------------------------------------------------------------------
# Klassifikationsfunktionen
# ---------------------------------------------------------------------------
def classify_a(text: str) -> str:
    t = text.lower()
    for code in A_PRIORITY:
        if code == "A0":
            return "A0"
        for kw in A_CODES[code]:
            if " " in kw or ":" in kw:
                if kw in t:
                    return code
            else:
                if re.search(r"\b" + re.escape(kw) + r"\b", t):
                    return code
    return "A0"


def classify_b(article_name: str, section_text: str) -> str:
    raw = article_name.strip()
    name = re.sub(r"^\[\[(.+?)(?:\|.*)?\]\]$", r"\1", raw).strip()
    text = section_text[:2000]
    combined = name + " " + text

    ns_prefixes = ("Kategorie:", "Vorlage:", "Wikipedia:", "Benutzer:",
                   "Portal:", "Hilfe:", "MediaWiki:")
    if name.startswith(ns_prefixes):
        return "B7"

    if re.search(r"\b(GmbH|AG|e\.V\.|eV\b|Verein|Partei|Stiftung|Institut|"
                 r"Gesellschaft|Genossenschaft|Holding|Konzern|NGO|NPO|"
                 r"Bundesverband|Landesverband)\b", combined):
        return "B3"

    if re.search(r"\b(Festival|Messe|Kongress|Award|Turnier|Wettbewerb|"
                 r"Championship|Cup|Open|Meisterschaft|Gala|WM|EM)\b",
                 combined, re.I):
        return "B4"

    if re.search(r"\b(Bahnhof|Bahnstrecke|Straße|Berg|Fluss|See|Kanal|"
                 r"Gemeinde|Dorf|Stadtteil|Ortsteil|Autobahn|Bundesstraße|"
                 r"Landkreis|Bezirk|Brücke|Tunnel|Hafen)\b",
                 name + " " + text[:500]):
        return "B5"

    if re.search(r"\b(Film|Buch|Album|Lied|Song|Single|Serie|Roman|Gedicht|"
                 r"Kunstwerk|Comic|Manga|Videospiel|Fernsehserie|Dokumentation|"
                 r"Kurzfilm|Theaterstück|Oper|Musical)\b", combined, re.I):
        return "B6"

    if re.search(r"(†|\(gest\.|gestorben\s+1[0-8]\d\d|"
                 r"geb(?:oren)?\.\s*1[0-8]\d\d|"
                 r"\b1[0-8]\d\d\b.*\b1[0-9]\d\d\b)", text):
        return "B2"

    _jobs = (r"Politiker(?:in)?|Sportler(?:in)?|Schauspieler(?:in)?|"
             r"Sänger(?:in)?|Musiker(?:in)?|Autor(?:in)?|Journalist(?:in)?|"
             r"Unternehmer(?:in)?|Trainer(?:in)?|Bürgermeister(?:in)?|"
             r"Aktivist(?:in)?|Influencer(?:in)?|YouTuber(?:in)?|Streamer(?:in)?|"
             r"Fußballer(?:in)?|Basketballer(?:in)?|Tennisspieler(?:in)?|"
             r"Regisseur(?:in)?|Produzent(?:in)?|Moderator(?:in)?|"
             r"Wissenschaftler(?:in)?|Forscher(?:in)?|Professor(?:in)?|"
             r"Schwimmer(?:in)?|Turner(?:in)?|Radfahrer(?:in)?|Boxer(?:in)?")
    if re.search(r"\b(?:" + _jobs + r")\b", text, re.I):
        return "B1"

    if re.match(
        r"^(?:Dr\.|Prof\.|Prof\. Dr\.|Sir |Lord |von |van |de )?"
        r"[A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\-]+"
        r"(?:\s+(?:von|van|de|di|del|der|bin|al))??"
        r"\s+[A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\-]+$",
        name
    ):
        return "B1"

    return "B8"


def classify_e(section_title: str) -> str:
    t = section_title.lower()
    if re.search(r"\bsla\b|schnelllösch", t):
        return "E7"
    if re.search(r"\bgelöscht\b", t):
        return "E1"
    if re.search(r"\bbleibt\b|\bbehalten\b", t):
        return "E2"
    if re.search(r"\blaz\b|löschantrag\s+zurückgezogen", t):
        return "E3"
    if re.search(r"\bbnr\b", t):
        return "E4"
    if re.search(r"\bweiterleitung\b|\bwl\b", t):
        return "E5"
    return "E6"


def calc_intensity(text: str) -> int:
    count = len(re.findall(r"\d{2}:\d{2},\s*\d{1,2}\.\s*\w+\s*\d{4}", text))
    if count == 0:
        count = len(re.findall(r"(?m)^[:*]+", text))
    return max(count, 1)

# ---------------------------------------------------------------------------
# Wikipedia-API
# ---------------------------------------------------------------------------
SECTION_RE  = re.compile(r"^(==+)\s*(.+?)\s*\1\s*$", re.MULTILINE)
SKIP_TITLES = re.compile(
    r"^(Heute|Einleitung|Navigationsleiste|Erledigt|Adminnotiz|"
    r"Diese Seite|Löschkandidaten vom|Archiv|Inhalt|Vorabinformation)",
    re.I,
)


def fetch_wikitext(d: date, retries: int = 4) -> tuple:
    month = DE_MONTHS[d.month]
    title = f"Wikipedia:Löschkandidaten/{d.day}._{month}_{d.year}"
    api = (
        "https://de.wikipedia.org/w/api.php?action=query&prop=revisions"
        "&rvprop=content&rvslots=main&format=json&titles="
        + urllib.parse.quote(title)
    )
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                api, headers={"User-Agent": "LK-Analyse/2.0 (github.com/user/wikipedia-loeschanalyse)"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            page = next(iter(data["query"]["pages"].values()))
            if "missing" in page:
                return None, title
            return page["revisions"][0]["slots"]["main"]["*"], title
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 10 * (2 ** attempt)
                print(f"  429 – warte {wait}s …", end=" ", flush=True)
                time.sleep(wait)
            else:
                print(f"  FEHLER HTTP {e.code}")
                return None, title
        except Exception as e:
            print(f"  FEHLER: {e}")
            return None, title
    print("  übersprungen (zu viele Versuche)")
    return None, title


def extract_sections(wikitext: str) -> list:
    matches = list(SECTION_RE.finditer(wikitext))
    sections = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        sections.append((level, title, wikitext[start:end]))
    return sections

# ---------------------------------------------------------------------------
# Hauptanalyse
# ---------------------------------------------------------------------------
def run_analysis(mode: dict) -> list:
    sample_dates = get_sample_dates(mode["days_back"], mode["step"])
    total = len(sample_dates)
    print(f"Modus:           {mode['label']}  ({mode['est']})")
    print(f"Analysezeitraum: {sample_dates[0]} bis {sample_dates[-1]}")
    print(f"Stichprobentage: {total}\n")

    rows = []
    for idx, d in enumerate(sample_dates, 1):
        month = DE_MONTHS[d.month]
        date_str = f"{d.day:02d}.{month[:3]}.{d.year}"
        url = (
            "https://de.wikipedia.org/wiki/Wikipedia:L%C3%B6schkandidaten/"
            + urllib.parse.quote(f"{d.day}._{month}_{d.year}")
        )
        print(f"[{idx:02d}/{total}] {date_str} ...", end=" ", flush=True)

        wikitext, _ = fetch_wikitext(d)
        if wikitext is None:
            print("übersprungen")
            continue

        count = 0
        for level, sec_title, body in extract_sections(wikitext):
            if level != 2:
                continue
            if SKIP_TITLES.match(sec_title):
                continue
            if len(body.strip()) < 20:
                continue

            m = re.match(r"^(.+?)\s*(?:\(|$)", sec_title)
            article_name = m.group(1).strip() if m else sec_title

            rows.append({
                "Datum":         date_str,
                "Artikelname":   article_name,
                "A-Code":        classify_a(body),
                "B-Code":        classify_b(article_name, body),
                "Ergebnis-Code": classify_e(sec_title),
                "Intensität":    calc_intensity(body),
                "URL":           url,
                "Anmerkung":     "",
            })
            count += 1

        print(f"{count} Fälle")
        time.sleep(3)

    print(f"\nGesamt: {len(rows)} Fälle aus {total} Stichprobentagen.\n")
    return rows

# ---------------------------------------------------------------------------
# CSV-Export
# ---------------------------------------------------------------------------
def write_csv(rows: list):
    fields = ["Datum", "Artikelname", "A-Code", "B-Code",
              "Ergebnis-Code", "Intensität", "URL", "Anmerkung"]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"CSV: {CSV_PATH}")

# ---------------------------------------------------------------------------
# HTML-Generierung
# ---------------------------------------------------------------------------
def build_stats(rows: list) -> dict:
    total = len(rows)
    if total == 0:
        return {}

    def freq(key):
        c = defaultdict(int)
        for r in rows:
            c[r[key]] += 1
        return dict(sorted(c.items(), key=lambda x: x[1], reverse=True))

    a_freq = freq("A-Code")
    b_freq = freq("B-Code")
    e_freq = freq("Ergebnis-Code")

    cross = defaultdict(int)
    for r in rows:
        cross[(r["A-Code"], r["B-Code"])] += 1

    top_intensity = {}
    for r in rows:
        a = r["A-Code"]
        if a not in top_intensity or r["Intensität"] > top_intensity[a]["Intensität"]:
            top_intensity[a] = r

    # Zeitreihe: Fälle pro Datum
    timeline = defaultdict(int)
    for r in rows:
        timeline[r["Datum"]] += 1

    return {
        "total":         total,
        "generated_at":  datetime.now().strftime("%d.%m.%Y %H:%M"),
        "a_freq":        a_freq,
        "b_freq":        b_freq,
        "e_freq":        e_freq,
        "cross":         {f"{a}×{b}": n for (a, b), n in
                          sorted(cross.items(), key=lambda x: x[1], reverse=True)[:15]},
        "top_intensity": {k: {"name": v["Artikelname"], "score": v["Intensität"], "url": v["URL"]}
                          for k, v in top_intensity.items()},
        "timeline":      dict(sorted(timeline.items())),
        "rows":          rows,
    }


# ---------------------------------------------------------------------------
# Kurzauswertung: Hinweise je Löschgrund, datengestützt aus E1-Fällen
# ---------------------------------------------------------------------------
ADVICE = {
    "A1": {
        "problem": "Artikel über Personen, deren überregionale Bedeutung nicht nachgewiesen ist. "
                   "Betroffen sind häufig Sportler:innen unterer Ligen, lokale Politiker:innen, "
                   "Influencer:innen sowie Personen, die nur in Eigenveröffentlichungen erwähnt werden.",
        "tip":     "WP:RK vor dem Anlegen prüfen. Mindestens ein harter Relevanzpunkt muss belegbar sein: "
                   "Buchveröffentlichung in einem anerkannten Verlag, mehrfache unabhängige Medienberichterstattung "
                   "auf nationaler Ebene oder ein öffentliches Amt mit eigenständiger enzyklopädischer Bedeutung. "
                   "Lokale Berichterstattung allein reicht nicht.",
    },
    "A4": {
        "problem": "Aussagen im Artikel sind nicht mit Einzelnachweisen belegt oder stützen sich "
                   "ausschließlich auf Primärquellen (eigene Website, Pressemitteilungen).",
        "tip":     "Jede nicht-triviale Aussage braucht einen unabhängigen Beleg. "
                   "Eigene Websites, Social-Media-Profile oder Unternehmensbroschüren gelten nicht als Belege "
                   "im Wikipedia-Sinne. Artikel ohne Einzelnachweise werden erfahrungsgemäß schnell gestellt.",
    },
    "A9": {
        "problem": "Artikel ist zu kurz, unvollständig oder nicht im enzyklopädischen Stil verfasst. "
                   "Typisch: Erstbeiträge neuer Nutzer:innen, die direkt einen Artikel anlegen.",
        "tip":     "Entwurf zunächst im Benutzernamensraum (BNR) ausarbeiten und von erfahrenen "
                   "Nutzer:innen prüfen lassen. Wikipedia:Wie schreibe ich gute Artikel lesen. "
                   "Ein Artikel sollte mindestens Einleitung, Fließtext und Belege enthalten.",
    },
    "A5": {
        "problem": "Infrastrukturartikel (Bahnhöfe, Straßen, Brücken) ohne eigenständige "
                   "enzyklopädische Darstellung in unabhängigen Quellen.",
        "tip":     "Kleine Infrastrukturobjekte sind nur relevant, wenn sie in anerkannten "
                   "Sekundärquellen (Fachbücher, überregionale Medien) eigenständig behandelt werden. "
                   "Reine Existenz reicht nicht für einen eigenen Artikel.",
    },
    "A3": {
        "problem": "Artikel liest sich wie ein Werbetext: Superlative, unkritische Selbstdarstellung, "
                   "fehlende neutrale Außenperspektive.",
        "tip":     "Neutraler Ton ist Pflicht. Keine Marketing-Sprache, keine Superlative, "
                   "keine ausschließlich positiven Formulierungen. "
                   "Quellen müssen unabhängig und nicht werblich sein (kein Presseportal, keine PR-Agenturen).",
    },
    "A2": {
        "problem": "Unternehmensartikel unterschreiten die Relevanzkriterien: zu wenig Mitarbeiter, "
                   "zu geringer Umsatz, keine nachgewiesene Marktstellung.",
        "tip":     "WP:RK#U kennen: Umsatz über 100 Mio. €, mehr als 1.000 Mitarbeiter "
                   "oder Marktführerschaft in einer Branche sind typische Eintrittsschwellen. "
                   "Regionale Unternehmen ohne überregionale Berichterstattung werden fast immer gelöscht.",
    },
    "A7": {
        "problem": "Kategorienamen oder -strukturen entsprechen nicht den Wikipedia-Konventionen "
                   "oder sind redundant zu bestehenden Kategorien.",
        "tip":     "Vor dem Anlegen neuer Kategorien die Diskussionsseiten des WikiProjekts Kategorien "
                   "konsultieren. Umbenennung ist in der Regel aufwändiger als Prävention.",
    },
    "A8": {
        "problem": "Text oder Bilder wurden ohne ausreichende Lizenz eingestellt oder "
                   "aus urheberrechtlich geschützten Quellen kopiert.",
        "tip":     "Nur Inhalte unter freier Lizenz (CC BY-SA, gemeinfrei) verwenden. "
                   "Texte nie aus anderen Quellen kopieren – auch nicht in eigener Übersetzung. "
                   "Bilder nur aus Wikimedia Commons einbinden.",
    },
    "A6": {
        "problem": "Inhalt des Artikels ist bereits in einem anderen Artikel enthalten "
                   "oder beschreibt dasselbe Thema unter anderem Namen.",
        "tip":     "Vor dem Anlegen die Wikipedia-Suche nutzen und prüfen, "
                   "ob das Thema bereits behandelt wird. Im Zweifel eine Weiterleitung anlegen statt eines neuen Artikels.",
    },
    "A0": {
        "problem": "Kein eindeutiger Löschgrund durch automatische Analyse erkennbar – "
                   "heterogene Gruppe aus gemischten oder untypisch formulierten Diskussionen.",
        "tip":     "Manuelle Sichtung empfohlen.",
    },
}


def build_kurzauswertung_html(rows: list, stats: dict) -> str:
    total      = stats["total"]
    deleted    = [r for r in rows if r["Ergebnis-Code"] == "E1"]
    n_deleted  = len(deleted)
    del_pct    = n_deleted / total * 100 if total else 0

    # Häufigkeit je A-Code unter den gelöschten Fällen
    a_counts = defaultdict(int)
    for r in deleted:
        a_counts[r["A-Code"]] += 1
    top_reasons = sorted(a_counts.items(), key=lambda x: x[1], reverse=True)

    # Intensivstes Beispiel je A-Code (aus allen Fällen, nicht nur E1)
    top_ex = {}
    for r in rows:
        a = r["A-Code"]
        if a not in top_ex or r["Intensität"] > top_ex[a]["Intensität"]:
            top_ex[a] = r

    cards_html = ""
    for rank, (code, count) in enumerate(top_reasons, 1):
        if count == 0:
            continue
        pct     = count / n_deleted * 100
        advice  = ADVICE.get(code, {})
        problem = advice.get("problem", "")
        tip     = advice.get("tip", "")
        label   = A_LABELS.get(code, code)
        ex      = top_ex.get(code)
        ex_html = ""
        if ex:
            ex_html = (
                f'<div class="auswertung-example">'
                f'Intensivstes Beispiel: '
                f'<a href="{ex["URL"]}" target="_blank">{ex["Artikelname"]}</a>'
                f' &nbsp;·&nbsp; {ex["Intensität"]} Beiträge'
                f'</div>'
            )
        cards_html += f"""
    <div class="auswertung-card">
      <div class="auswertung-header">
        <span class="rank">#{rank}</span>
        <span class="badge badge-{code}">{code}</span>
        <span class="auswertung-title">{label}</span>
        <span class="auswertung-stat">{count} Fälle &nbsp;·&nbsp; {pct:.0f}&thinsp;% der Löschungen</span>
      </div>
      <p class="auswertung-problem">{problem}</p>
      <div class="auswertung-tip"><strong>Was vermeiden?</strong> {tip}</div>
      {ex_html}
    </div>"""

    return f"""
  <section>
    <h2>Kurzauswertung – Was führt zur Löschung?</h2>
    <p class="auswertung-intro">
      Von <strong>{total}</strong> analysierten Diskussionen wurden
      <strong>{n_deleted}</strong> ({del_pct:.0f}&thinsp;%) gelöscht.
      Die häufigsten Gründe und was man daraus lernen kann:
    </p>
    <div class="auswertung-grid">
      {cards_html}
    </div>
  </section>"""


def write_html(stats: dict):
    # Alle JSON-Strings vor dem f-string definieren, damit die Interpolation greift
    data_json         = json.dumps(stats, ensure_ascii=False)
    a_labels_json     = json.dumps(A_LABELS, ensure_ascii=False)
    b_labels_json     = json.dumps(B_LABELS, ensure_ascii=False)
    e_labels_json     = json.dumps(E_LABELS, ensure_ascii=False)
    kurzauswertung    = build_kurzauswertung_html(stats.get("rows", []), stats)

    html = f"""<!DOCTYPE html>\n<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wikipedia Löschkandidaten – Musteranalyse</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg:       #0d1117;
    --surface:  #161b22;
    --border:   #30363d;
    --text:     #e6edf3;
    --muted:    #8b949e;
    --accent:   #58a6ff;
    --green:    #3fb950;
    --red:      #f85149;
    --yellow:   #d29922;
    --purple:   #bc8cff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; line-height: 1.6; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  header {{ padding: 2rem 2rem 1rem; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 1.6rem; font-weight: 700; }}
  header p  {{ color: var(--muted); margin-top: .25rem; }}

  .container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem 2rem; }}
  section {{ margin-bottom: 2.5rem; }}
  h2 {{ font-size: 1rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: .4rem; }}

  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }}
  .card .num {{ font-size: 1.8rem; font-weight: 700; line-height: 1; }}
  .card .lbl {{ color: var(--muted); font-size: .8rem; margin-top: .25rem; }}
  .card.deleted .num {{ color: var(--red); }}
  .card.kept    .num {{ color: var(--green); }}
  .card.open    .num {{ color: var(--yellow); }}
  .card.sla     .num {{ color: var(--purple); }}

  .charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  @media (max-width: 700px) {{ .charts-grid {{ grid-template-columns: 1fr; }} }}
  .chart-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }}
  .chart-box h3 {{ font-size: .85rem; font-weight: 600; color: var(--muted); margin-bottom: 1rem; text-transform: uppercase; letter-spacing: .04em; }}
  .chart-full {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }}
  .chart-full h3 {{ font-size: .85rem; font-weight: 600; color: var(--muted); margin-bottom: 1rem; text-transform: uppercase; letter-spacing: .04em; }}

  .intensity-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: .75rem; }}
  .intensity-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: .85rem 1rem; display: flex; align-items: flex-start; gap: .75rem; }}
  .intensity-badge {{ background: var(--border); border-radius: 5px; padding: .2rem .45rem; font-size: .75rem; font-weight: 700; white-space: nowrap; flex-shrink: 0; }}
  .intensity-info .name {{ font-weight: 600; font-size: .85rem; }}
  .intensity-info .meta {{ color: var(--muted); font-size: .75rem; margin-top: .15rem; }}

  .controls {{ display: flex; gap: .75rem; flex-wrap: wrap; margin-bottom: .75rem; align-items: center; }}
  .controls input {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: .4rem .75rem; color: var(--text); font-size: .85rem; flex: 1; min-width: 200px; }}
  .controls input:focus {{ outline: none; border-color: var(--accent); }}
  .controls select {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: .4rem .75rem; color: var(--text); font-size: .85rem; }}
  .controls .count {{ color: var(--muted); font-size: .8rem; white-space: nowrap; }}

  table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
  thead th {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: .5rem .75rem; text-align: left; color: var(--muted); font-weight: 600; white-space: nowrap; position: sticky; top: 0; z-index: 1; }}
  tbody tr {{ border-bottom: 1px solid var(--border); }}
  tbody tr:hover {{ background: var(--surface); }}
  td {{ padding: .4rem .75rem; vertical-align: top; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  td.wrap {{ white-space: normal; }}

  .badge {{ display: inline-block; padding: .1rem .4rem; border-radius: 4px; font-size: .72rem; font-weight: 600; }}
  .badge-A1 {{ background: #1f3a5f; color: #79b8ff; }}
  .badge-A2 {{ background: #1f3a5f; color: #58a6ff; }}
  .badge-A3 {{ background: #3b2300; color: #d29922; }}
  .badge-A4 {{ background: #2d1a00; color: #e3b341; }}
  .badge-A5 {{ background: #1a2f1a; color: #3fb950; }}
  .badge-A6 {{ background: #1a2f1a; color: #56d364; }}
  .badge-A7 {{ background: #2f1a2f; color: #bc8cff; }}
  .badge-A8 {{ background: #3b0b0b; color: #f85149; }}
  .badge-A9 {{ background: #1c1c1c; color: #8b949e; }}
  .badge-A0 {{ background: #1c1c1c; color: #6e7681; }}
  .badge-E1 {{ background: #3b0b0b; color: #f85149; }}
  .badge-E2 {{ background: #1a2f1a; color: #3fb950; }}
  .badge-E3 {{ background: #1f2d3b; color: #58a6ff; }}
  .badge-E4 {{ background: #2f2014; color: #d29922; }}
  .badge-E5 {{ background: #1c1c2f; color: #bc8cff; }}
  .badge-E6 {{ background: #1c1c1c; color: #8b949e; }}
  .badge-E7 {{ background: #2f1a2f; color: #bc8cff; }}

  .table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; max-height: 600px; overflow-y: auto; }}

  footer {{ text-align: center; padding: 2rem; color: var(--muted); font-size: .8rem; border-top: 1px solid var(--border); }}

  .auswertung-intro {{ margin-bottom: 1.25rem; line-height: 1.7; }}
  .auswertung-grid {{ display: flex; flex-direction: column; gap: 1rem; }}
  .auswertung-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem 1.25rem; }}
  .auswertung-header {{ display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; margin-bottom: .6rem; }}
  .rank {{ font-size: .75rem; font-weight: 700; color: var(--muted); min-width: 1.4rem; }}
  .auswertung-title {{ font-weight: 600; font-size: .9rem; flex: 1; }}
  .auswertung-stat {{ font-size: .78rem; color: var(--muted); white-space: nowrap; }}
  .auswertung-problem {{ color: var(--muted); font-size: .83rem; margin-bottom: .6rem; line-height: 1.6; }}
  .auswertung-tip {{ background: #0d2137; border-left: 3px solid var(--accent); border-radius: 0 6px 6px 0; padding: .6rem .9rem; font-size: .83rem; line-height: 1.6; margin-bottom: .5rem; }}
  .auswertung-tip strong {{ color: var(--accent); }}
  .auswertung-example {{ font-size: .78rem; color: var(--muted); margin-top: .4rem; }}

  .legend-grid {{ display: flex; flex-direction: column; gap: 1.25rem; }}
  .legend-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }}
  @media (max-width: 700px) {{ .legend-cols {{ grid-template-columns: 1fr; }} }}
  .legend-block {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; }}
  .legend-title {{ font-size: .8rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: .75rem; }}
  .legend-table {{ border-collapse: collapse; width: 100%; font-size: .82rem; }}
  .legend-table tr {{ border-bottom: 1px solid var(--border); }}
  .legend-table tr:last-child {{ border-bottom: none; }}
  .legend-table td {{ padding: .35rem .5rem; vertical-align: middle; }}
  .legend-table td:first-child {{ width: 3rem; }}
  .legend-hint {{ color: var(--muted); font-size: .75rem; padding-left: 1rem; }}
</style>
</head>
<body>

<header>
  <h1>Wikipedia Löschdiskussionen – Musteranalyse</h1>
  <p id="subtitle">Lade Daten…</p>
  <p style="margin-top:.5rem;font-size:.8rem;color:var(--muted)">Ein Projekt von <a href="https://github.com/profmanagement" target="_blank">Profmanagement</a></p>
</header>

<div class="container">

  <section>
    <h2>Übersicht</h2>
    <div class="cards" id="cards"></div>
  </section>

  <section>
    <div class="charts-grid">
      <div class="chart-box">
        <h3>Löschgründe (A-Codes)</h3>
        <canvas id="chartA"></canvas>
      </div>
      <div class="chart-box">
        <h3>Ergebnisse</h3>
        <canvas id="chartE"></canvas>
      </div>
    </div>
  </section>

  <section>
    <div class="chart-full">
      <h3>Artikeltypen (B-Codes)</h3>
      <canvas id="chartB"></canvas>
    </div>
  </section>

  <section>
    <div class="chart-full">
      <h3>Diskussionen im Zeitverlauf</h3>
      <canvas id="chartTimeline"></canvas>
    </div>
  </section>

  <section>
    <h2>Intensivste Diskussionen je Kategorie</h2>
    <div class="intensity-grid" id="intensityGrid"></div>
  </section>

  <section>
    <h2>Alle Diskussionen</h2>
    <div class="controls">
      <input type="text" id="search" placeholder="Artikelname suchen…">
      <select id="filterA"><option value="">Alle Löschgründe</option></select>
      <select id="filterB"><option value="">Alle Artikeltypen</option></select>
      <select id="filterE"><option value="">Alle Ergebnisse</option></select>
      <span class="count" id="rowCount"></span>
    </div>
    <div class="table-wrap">
      <table id="dataTable">
        <thead>
          <tr>
            <th>Datum</th>
            <th>Artikel</th>
            <th>Löschgrund</th>
            <th>Typ</th>
            <th>Ergebnis</th>
            <th style="text-align:right">Beiträge</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </section>

{kurzauswertung}

  <section>
    <h2>Legende</h2>
    <div class="legend-grid">

      <div class="legend-block">
        <div class="legend-title">A-Codes – Löschgrund</div>
        <table class="legend-table">
          <tr><td><span class="badge badge-A1">A1</span></td><td>Fehlende Relevanz – Person</td><td class="legend-hint">WP:RK, Relevanzkriterien, keine überregionale Relevanz</td></tr>
          <tr><td><span class="badge badge-A2">A2</span></td><td>Fehlende Relevanz – Unternehmen / Organisation</td><td class="legend-hint">Unternehmensrelevanz, Umsatz, Mitarbeiterzahl</td></tr>
          <tr><td><span class="badge badge-A3">A3</span></td><td>Werblicher / PR-Charakter</td><td class="legend-hint">WP:WWNI, Werbetext, Werbeflyer, Selbstdarstellung</td></tr>
          <tr><td><span class="badge badge-A4">A4</span></td><td>Fehlende Belege</td><td class="legend-hint">unbelegt, Belege fehlen, keine Quellen</td></tr>
          <tr><td><span class="badge badge-A5">A5</span></td><td>Relevanz Geographie / Infrastruktur</td><td class="legend-hint">Bahnhof, Ortsteil, Bundesstraße, Stadtteil</td></tr>
          <tr><td><span class="badge badge-A6">A6</span></td><td>Redundanz / Weiterleitung</td><td class="legend-hint">bereits vorhanden, Doppelartikel, zusammenführen</td></tr>
          <tr><td><span class="badge badge-A7">A7</span></td><td>Kategoriediskussion</td><td class="legend-hint">Umbenennung, Kategorisierung, WikiProjekt Kategorien</td></tr>
          <tr><td><span class="badge badge-A8">A8</span></td><td>Urheberrechtsverletzung</td><td class="legend-hint">URV, Copyright, Plagiat, Lizenzverstoß</td></tr>
          <tr><td><span class="badge badge-A9">A9</span></td><td>Qualitätsmangel</td><td class="legend-hint">kein Artikel, unleserlich, neuer Benutzer</td></tr>
          <tr><td><span class="badge badge-A0">A0</span></td><td>Unklar / Sonstiges</td><td class="legend-hint">kein eindeutiges Muster erkannt</td></tr>
        </table>
      </div>

      <div class="legend-cols">
        <div class="legend-block">
          <div class="legend-title">B-Codes – Artikeltyp</div>
          <table class="legend-table">
            <tr><td><span class="badge" style="background:#1f3a5f;color:#79b8ff">B1</span></td><td>Person (lebend)</td></tr>
            <tr><td><span class="badge" style="background:#1f3a5f;color:#58a6ff">B2</span></td><td>Person (historisch)</td></tr>
            <tr><td><span class="badge" style="background:#1a2f1a;color:#3fb950">B3</span></td><td>Unternehmen / Organisation</td></tr>
            <tr><td><span class="badge" style="background:#3b2300;color:#d29922">B4</span></td><td>Veranstaltung / Event</td></tr>
            <tr><td><span class="badge" style="background:#1a2f1a;color:#56d364">B5</span></td><td>Geographie / Infrastruktur</td></tr>
            <tr><td><span class="badge" style="background:#2f1a2f;color:#bc8cff">B6</span></td><td>Kulturelles Werk (Film, Buch, Musik …)</td></tr>
            <tr><td><span class="badge" style="background:#1c1c2f;color:#8b949e">B7</span></td><td>Kategorie / Vorlage / Wikipedia-intern</td></tr>
            <tr><td><span class="badge" style="background:#1c1c1c;color:#6e7681">B8</span></td><td>Sonstiges / nicht eindeutig klassifiziert</td></tr>
          </table>
        </div>

        <div class="legend-block">
          <div class="legend-title">E-Codes – Ergebnis der Diskussion</div>
          <table class="legend-table">
            <tr><td><span class="badge badge-E1">E1</span></td><td>Gelöscht</td></tr>
            <tr><td><span class="badge badge-E2">E2</span></td><td>Behalten (<em>bleibt</em>)</td></tr>
            <tr><td><span class="badge badge-E3">E3</span></td><td>LAZ – Löschantrag zurückgezogen</td></tr>
            <tr><td><span class="badge badge-E4">E4</span></td><td>BNR – in Benutzernamensraum verschoben</td></tr>
            <tr><td><span class="badge badge-E5">E5</span></td><td>Weiterleitung eingerichtet</td></tr>
            <tr><td><span class="badge badge-E6">E6</span></td><td>Noch offen / nicht abgearbeitet</td></tr>
            <tr><td><span class="badge badge-E7">E7</span></td><td>SLA – Schnelllöschantrag</td></tr>
          </table>
        </div>
      </div>

    </div>
  </section>

</div>

<footer>
  &copy; <a href="https://github.com/profmanagement" target="_blank">Profmanagement</a> &nbsp;·&nbsp;
  Datenquelle: <a href="https://de.wikipedia.org/wiki/Wikipedia:L%C3%B6schkandidaten" target="_blank">Wikipedia:Löschkandidaten</a> &nbsp;·&nbsp;
  Wikipedia-Inhalte: <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank">CC BY-SA 4.0</a> &nbsp;·&nbsp;
  <a href="https://github.com/profmanagement/wp-loeschdiskussion" target="_blank">Quellcode auf GitHub</a> &nbsp;·&nbsp;
  Generiert am <span id="genDate"></span>
</footer>

<script>
const DATA = {data_json};

const A_LABELS = {a_labels_json};
const B_LABELS = {b_labels_json};
const E_LABELS = {e_labels_json};

const COLORS_A = ["#79b8ff","#58a6ff","#d29922","#e3b341","#3fb950","#56d364","#bc8cff","#f85149","#8b949e","#6e7681"];
const COLORS_E = ["#f85149","#3fb950","#58a6ff","#d29922","#bc8cff","#8b949e","#c084fc"];
const COLORS_B = ["#79b8ff","#58a6ff","#3fb950","#d29922","#56d364","#bc8cff","#e3b341","#8b949e"];

document.getElementById("subtitle").textContent =
  `Stichprobe der letzten 180 Tage · ${{DATA.total}} kodierte Diskussionen · Stand: ${{DATA.generated_at}}`;
document.getElementById("genDate").textContent = DATA.generated_at;

// --- Cards ---
const e = DATA.e_freq;
const cards = [
  {{ num: DATA.total, lbl: "Diskussionen gesamt", cls: "" }},
  {{ num: e["E1"] || 0, lbl: "Gelöscht", cls: "deleted" }},
  {{ num: e["E2"] || 0, lbl: "Behalten", cls: "kept" }},
  {{ num: e["E6"] || 0, lbl: "Noch offen", cls: "open" }},
  {{ num: e["E7"] || 0, lbl: "SLA", cls: "sla" }},
  {{ num: e["E3"] || 0, lbl: "LAZ", cls: "" }},
];
document.getElementById("cards").innerHTML = cards.map(c =>
  `<div class="card ${{c.cls}}"><div class="num">${{c.num}}</div><div class="lbl">${{c.lbl}}</div></div>`
).join("");

// --- Chart helpers ---
function barChart(id, labels, values, colors, horizontal=true) {{
  new Chart(document.getElementById(id), {{
    type: "bar",
    data: {{ labels, datasets: [{{ data: values, backgroundColor: colors, borderRadius: 4, borderSkipped: false }}] }},
    options: {{
      indexAxis: horizontal ? "y" : "x",
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ grid: {{ color: "#21262d" }}, ticks: {{ color: "#8b949e" }} }},
        y: {{ grid: {{ color: "#21262d" }}, ticks: {{ color: "#e6edf3", font: {{ size: 11 }} }} }}
      }}
    }}
  }});
}}

function donutChart(id, labels, values, colors) {{
  new Chart(document.getElementById(id), {{
    type: "doughnut",
    data: {{ labels, datasets: [{{ data: values, backgroundColor: colors, borderColor: "#0d1117", borderWidth: 2 }}] }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ position: "right", labels: {{ color: "#e6edf3", font: {{ size: 11 }}, padding: 12 }} }}
      }}
    }}
  }});
}}

// A-Codes bar
const aKeys = Object.keys(DATA.a_freq);
barChart("chartA",
  aKeys.map(k => `${{k}} ${{A_LABELS[k] || ""}}`),
  aKeys.map(k => DATA.a_freq[k]),
  COLORS_A
);

// E-Codes donut
const eKeys = Object.keys(DATA.e_freq);
donutChart("chartE",
  eKeys.map(k => `${{E_LABELS[k] || k}} (${{DATA.e_freq[k]}})`),
  eKeys.map(k => DATA.e_freq[k]),
  COLORS_E
);

// B-Codes bar
const bKeys = Object.keys(DATA.b_freq);
barChart("chartB",
  bKeys.map(k => `${{k}} ${{B_LABELS[k] || ""}}`),
  bKeys.map(k => DATA.b_freq[k]),
  COLORS_B
);

// Timeline
const tKeys = Object.keys(DATA.timeline);
new Chart(document.getElementById("chartTimeline"), {{
  type: "bar",
  data: {{
    labels: tKeys,
    datasets: [{{ data: tKeys.map(k => DATA.timeline[k]), backgroundColor: "#1f6feb", borderRadius: 3 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ color: "#8b949e", maxRotation: 45, font: {{ size: 10 }} }} }},
      y: {{ grid: {{ color: "#21262d" }}, ticks: {{ color: "#8b949e" }} }}
    }}
  }}
}});

// --- Intensity cards ---
const ig = document.getElementById("intensityGrid");
Object.entries(DATA.top_intensity).sort().forEach(([code, info]) => {{
  ig.innerHTML += `
    <div class="intensity-card">
      <span class="intensity-badge badge badge-${{code}}">${{code}}</span>
      <div class="intensity-info">
        <div class="name"><a href="${{info.url}}" target="_blank">${{info.name}}</a></div>
        <div class="meta">${{A_LABELS[code] || code}} &nbsp;·&nbsp; ${{info.score}} Beiträge</div>
      </div>
    </div>`;
}});

// --- Table ---
const tbody = document.getElementById("tbody");
const selA = document.getElementById("filterA");
const selB = document.getElementById("filterB");
const selE = document.getElementById("filterE");

Object.entries(DATA.a_freq).forEach(([k]) => {{
  selA.innerHTML += `<option value="${{k}}">${{k}} – ${{A_LABELS[k] || k}}</option>`;
}});
Object.entries(DATA.b_freq).forEach(([k]) => {{
  selB.innerHTML += `<option value="${{k}}">${{k}} – ${{B_LABELS[k] || k}}</option>`;
}});
Object.entries(DATA.e_freq).forEach(([k]) => {{
  selE.innerHTML += `<option value="${{k}}">${{k}} – ${{E_LABELS[k] || k}}</option>`;
}});

function renderTable() {{
  const q  = document.getElementById("search").value.toLowerCase();
  const fa = selA.value;
  const fb = selB.value;
  const fe = selE.value;
  const filtered = DATA.rows.filter(r =>
    (!q  || r.Artikelname.toLowerCase().includes(q)) &&
    (!fa || r["A-Code"] === fa) &&
    (!fb || r["B-Code"] === fb) &&
    (!fe || r["Ergebnis-Code"] === fe)
  );
  document.getElementById("rowCount").textContent = `${{filtered.length}} von ${{DATA.total}} Einträgen`;
  tbody.innerHTML = filtered.map(r => `
    <tr>
      <td>${{r.Datum}}</td>
      <td class="wrap"><a href="${{r.URL}}" target="_blank">${{r.Artikelname}}</a></td>
      <td><span class="badge badge-${{r["A-Code"]}}">${{r["A-Code"]}}</span> <span style="color:#8b949e;font-size:.78rem">${{A_LABELS[r["A-Code"]] || ""}}</span></td>
      <td><span style="color:#8b949e;font-size:.78rem">${{B_LABELS[r["B-Code"]] || r["B-Code"]}}</span></td>
      <td><span class="badge badge-${{r["Ergebnis-Code"]}}">${{E_LABELS[r["Ergebnis-Code"]] || r["Ergebnis-Code"]}}</span></td>
      <td style="text-align:right;color:#8b949e">${{r["Intensität"]}}</td>
    </tr>`).join("");
}}

document.getElementById("search").addEventListener("input", renderTable);
selA.addEventListener("change", renderTable);
selB.addEventListener("change", renderTable);
selE.addEventListener("change", renderTable);
renderTable();
</script>
</body>
</html>
"""

    # f-string hat alle Variablen ({data_json}, {a_labels_json} etc.) bereits eingesetzt
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML: {HTML_PATH}")

# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mode = parse_mode()
    rows = run_analysis(mode)
    write_csv(rows)
    stats = build_stats(rows)
    write_html(stats)
    print("\nFertig. Öffne docs/index.html im Browser.")
