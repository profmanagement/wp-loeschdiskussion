# Wikipedia Löschkandidaten – Musteranalyse

## Das Problem

Täglich werden in der deutschen Wikipedia Dutzende Artikel zur Löschung vorgeschlagen. Die Gründe sind vielfältig: fehlende Relevanz, mangelnde Belege, werbliche Sprache oder schlicht unzureichende Qualität. Für viele Autorinnen und Autoren – ob neu oder erfahren – sind diese Löschungen frustrierend und oft überraschend.

**Das Kernproblem:** Wikipedia bietet keine systematische Auswertung dieser Diskussionen. Es gibt keine Musteranalyse, keine aggregierte Übersicht, welche Themen besonders häufig betroffen sind, und keinen strukturierten Leitfaden, der zeigt, was man vor dem Anlegen eines Artikels hätte beachten müssen. Löschungen sind damit zwar lehrreich – aber nur für diejenigen, die bereit sind, die Archive manuell zu durchsuchen.

---

## Die Lösung

Dieses Projekt automatisiert genau das: Es ruft die Wikipedia-Löschdiskussionen der letzten 180 Tage ab, kodiert jede Diskussion systematisch nach Löschgrund, Artikeltyp und Ergebnis – und erzeugt daraus eine interaktive Auswertung im Browser.

Das Ergebnis ist eine datengestützte Antwort auf die Frage: **Warum werden Wikipedia-Artikel gelöscht, und was kann man dagegen tun?**

Die Auswertung zeigt nicht nur Häufigkeiten, sondern schlägt für jeden Löschgrund konkrete Lösungswege vor – als praktischer Leitfaden für alle, die Artikel anlegen oder verbessern möchten.

Keine externen Abhängigkeiten. Keine API-Schlüssel. Einfach ausführen.

---

## Schnellstart

```bash
git clone https://github.com/profmanagement/wp-loeschdiskussion
cd wp-loeschdiskussion
python3 analyse.py
```

Danach `docs/index.html` im Browser öffnen.

---

## Analyseoptionen

| Befehl | Zeitraum | Abrufe | Geschätzte Zeit |
|--------|----------|--------|-----------------|
| `python3 analyse.py` | 180 Tage, Stichprobe alle 5 Tage | ~35 | ca. 2 min |
| `python3 analyse.py --30` | Letzte 30 Tage, täglich | ~23 | ca. 1 min |
| `python3 analyse.py --60` | Letzte 60 Tage, täglich | ~53 | ca. 3 min |
| `python3 analyse.py --all` | Letzte 180 Tage, täglich | ~173 | ca. 10 min |
| `python3 analyse.py --help` | Hilfe anzeigen | — | — |

**Empfehlung:** Für einen ersten Überblick reicht die Standardoption. `--all` liefert die vollständigste Datenbasis für ernsthafte Analysen.

---

## Was das Skript macht

1. **Stichprobenziehung** – berechnet automatisch Analysetage rückwirkend (mind. 7 Tage alt, damit Diskussionen abgeschlossen sind)
2. **Datenabruf** – holt den Wikitext jeder Archivseite über die Wikipedia-API
3. **Kodierung** – klassifiziert jede Diskussion nach drei Dimensionen (s. u.)
4. **Export** – schreibt `data/rohdaten.csv` und `docs/index.html`

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
| `docs/index.html` | Interaktive Auswertung mit Charts, Zeitfilter und durchsuchbarer Tabelle |
| `data/rohdaten.csv` | Alle kodierten Diskussionen (eine Zeile pro Fall) |

---

## Methodik & Grenzen

Die Kodierung basiert auf **schlüsselwortbasiertem Matching** des Wikitexts. Das ist schnell und reproduzierbar, hat aber bekannte Grenzen:

- **A0 (Unklar)** tritt auf, wenn kein Schlüsselwort eindeutig zutrifft — oft bei kurzen oder untypisch formulierten Diskussionen
- **A1 vs. A2**: Unternehmens-Diskussionen mit generischen Relevanzformulierungen werden manchmal A1 statt A2 zugeordnet
- **Intensität** = Anzahl der Zeitstempel im Wikitext (Proxy für Diskussionsbeiträge, nicht exakt)

Für wissenschaftliche Verwendung empfiehlt sich manuelle Überprüfung einer Stichprobe (~10 %) der kodierten Fälle.

---

## Anpassungen

**Kategorien erweitern:**  
Die Schlüsselwörterlisten `A_CODES` in `analyse.py` können beliebig ergänzt werden. Das Skript erkennt neue Muster automatisch beim nächsten Durchlauf.

---

## Datenquelle & Lizenz

- **Projekt:** [Profmanagement](https://github.com/profmanagement)
- **Daten:** [Wikipedia:Löschkandidaten](https://de.wikipedia.org/wiki/Wikipedia:L%C3%B6schkandidaten) – Lizenz [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Code:** MIT License
