# Wikipedia Löschkandidaten – Musteranalyse

Ein Werkzeug zur automatischen Analyse von Diskussionsmustern in den deutschen Wikipedia-Löschdiskussionen. Das Skript holt die Daten direkt von Wikipedia, kodiert jede Diskussion nach einem systematischen Kategoriensystem und erzeugt eine interaktive HTML-Auswertung.

Keine externen Abhängigkeiten. Keine API-Schlüssel. Einfach ausführen.

---

## Schnellstart

```bash
git clone https://github.com/DEIN-USERNAME/wikipedia-loeschanalyse
cd wikipedia-loeschanalyse
python3 analyse.py
```

Danach im Browser öffnen:

```
site/index.html
```

---

## Was das Skript macht

1. **Stichprobenziehung** – berechnet automatisch alle 5 Tage rückwirkend für die letzten 180 Tage (mind. 7 Tage alt, damit Diskussionen abgeschlossen sind)
2. **Datenabruf** – holt den Wikitext jeder Archivseite über die Wikipedia-API
3. **Kodierung** – klassifiziert jede Diskussion nach drei Dimensionen (s. u.)
4. **Export** – schreibt `data/rohdaten.csv` und `site/index.html`

Laufzeit: ca. 3–5 Minuten (je nach Netzgeschwindigkeit, 1 Sekunde Pause zwischen Requests).

---

## Kategoriensystem

### Dimension A – Löschgrund

| Code | Bezeichnung | Typische Signalwörter |
|------|-------------|----------------------|
| A1 | Relevanz – Person | *keine Relevanz, WP:RK, Relevanzkriterien* |
| A2 | Relevanz – Unternehmen/Org. | *Unternehmensrelevanz, Umsatz, Mitarbeiterzahl* |
| A3 | Werblicher Charakter | *Werbetext, Werbeflyer, WP:WWNI* |
| A4 | Fehlende Belege | *unbelegt, Belege fehlen, keine Quellen* |
| A5 | Geographie / Infrastruktur | *Bahnhof, Ortsteil, Bundesstraße* |
| A6 | Redundanz / Weiterleitung | *Redundanz, bereits vorhanden, zusammenführen* |
| A7 | Kategoriediskussion | *Kategorie:, Umbenennung, Kategorisierung* |
| A8 | Urheberrechtsverletzung | *URV, Urheberrecht, Copyright* |
| A9 | Qualitätsmangel | *kein Artikel, unleserlich, neuer Benutzer* |
| A0 | Unklar / Sonstiges | kein eindeutiges Muster erkannt |

### Dimension B – Artikeltyp

| Code | Bezeichnung |
|------|-------------|
| B1 | Person (lebend) |
| B2 | Person (historisch) |
| B3 | Unternehmen / Organisation |
| B4 | Veranstaltung / Event |
| B5 | Geographie / Infrastruktur |
| B6 | Kulturelles Werk |
| B7 | Kategorie / intern |
| B8 | Sonstiges |

### Dimension E – Ergebnis

| Code | Bedeutung |
|------|-----------|
| E1 | Gelöscht |
| E2 | Behalten (`bleibt`) |
| E3 | LAZ (Löschantrag zurückgezogen) |
| E4 | BNR (Benutzernamensraum) |
| E5 | Weiterleitung |
| E6 | Noch offen |
| E7 | SLA (Schnelllöschung) |

---

## Ausgabedateien

| Datei | Inhalt |
|-------|--------|
| `site/index.html` | Interaktive Auswertung mit Charts und durchsuchbarer Tabelle |
| `data/rohdaten.csv` | Alle kodierten Diskussionen (eine Zeile pro Fall) |

---

## Methodik & Grenzen

Die Kodierung basiert auf **schlüsselwortbasiertem Matching** des Wikitexts. Das ist schnell und reproduzierbar, hat aber bekannte Grenzen:

- **A0 (Unklar)** tritt auf, wenn kein Schlüsselwort eindeutig zutrifft — oft bei kurzen oder untypisch formulierten Diskussionen
- **A1 vs. A2**: Unternehmens-Diskussionen, die generische Relevanzformulierungen verwenden, werden manchmal A1 statt A2 zugeordnet
- **Intensität** = Anzahl der Zeitstempel im Wikitext (Proxy für Diskussionsbeiträge, nicht exakt)

Für wissenschaftliche Verwendung empfiehlt sich manuelle Überprüfung einer Stichprobe (~10 %) der kodierten Fälle.

---

## Anpassungen

**Analysezeitraum ändern:**
```python
# In analyse.py, Zeile ~60:
def get_sample_dates(days_back: int = 180, step: int = 5) -> list:
```

**Kategorien erweitern:**  
Die Schlüsselwörterlisten `A_CODES` in `analyse.py` können beliebig ergänzt werden. Das Skript erkennt neue Muster automatisch beim nächsten Durchlauf.

---

## Datenquelle & Lizenz

- **Daten:** [Wikipedia:Löschkandidaten](https://de.wikipedia.org/wiki/Wikipedia:L%C3%B6schkandidaten) – Lizenz [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Code:** MIT License
