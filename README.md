# Race Manager

Ein Streamlit-Dashboard zur Renn- und Verpflegungsplanung für MTB-Marathons und Ultra-Rennen. Race Manager kombiniert Streckendaten (GPX), Trainingsdaten (Strava-Exports) und eine konfigurierbare Verpflegungsstrategie zu einem Zielzeit- und Ernährungsplan – inklusive PDF-Export für unterwegs.

## Features

- **Athletenverwaltung** – Athleten anlegen/bearbeiten/löschen, Foto (EXIF-Ausrichtung wird automatisch korrigiert), Gewicht, Geburtsjahr, Standard-Kohlenhydratrate
- **Trainingsdaten-Analyse** – Import von `.csv`, `.fit`, `.gpx` sowie gzip-komprimierten Strava-Exports (`.fit.gz`, `.gpx.gz`), auch mehrere Dateien gleichzeitig; automatische Berechnung von FTP, maximaler Herzfrequenz und Leistungskurve (Mean Maximal Power über alle Trainingsdateien kombiniert)
- **Streckenverwaltung** – GPX/CSV-Strecken hochladen (mit Bestätigung), speichern, wiederverwenden und wieder löschen; automatische Höhenprofil-, Distanz- und Höhenmeter-Berechnung
- **Zielzeit-Kalkulation** – Geschwindigkeitsvorschlag auf Basis von Streckenprofil (Steigung) und Athleten-FTP; die Zielzeit lässt sich zusätzlich frei über Stunden/Minuten-Eingabefelder anpassen
- **Verpflegungsplanung** – Flaschenkonfiguration (Anzahl, Größe, Inhalt inkl. Produktlinie bei Marken mit mehreren Varianten), Gel-Auswahl nach Hersteller/Produktlinie, automatische Verpflegungs-Timeline auf Basis der gewünschten Kohlenhydratrate; Mindesthydrierungs-Warnung (500 ml/h), die den gesamten Flaschen- und Feedzonen-Bestand kumulativ berücksichtigt (Restvolumen aus noch nicht leeren Flaschen fließt korrekt mit ein)
- **Feedzonen** – Verpflegungsstationen entlang der Strecke platzieren (Position frei über km-Eingabefeld); pro Feedzone wird explizit festgelegt, wie viele Flaschen (mit Größe/Inhalt) und Gele dort übergeben werden. Feedzonen-Übergaben erscheinen gelb hervorgehoben in der Verpflegungstabelle und als eigene Markierung im Höhenprofil
- **Kartenansicht & Höhenprofil** – interaktive Karte (Route, Flaschen-/Gel-/Riegel-Marker, Anstiege, Gipfel) sowie ein Höhenprofil über die volle Breite mit eingezeichneten Verpflegungs- und Feedzonen-Marken
- **PDF-Export** – Rennplan mit Athletenfoto, Streckendaten und Verpflegungstabelle (Feedzonen gelb markiert) sowie ein zweites Blatt mit vertikalem Höhenprofil zum Ausschneiden und aufs Oberrohr kleben

## Projektstruktur

```
Race_Manager/
├── main.py                        # Streamlit-Einstiegspunkt, UI-Layout, PDF-Export
├── modules/
│   ├── athletenverwaltung.py      # Athleten- und Trainingsdatei-Verwaltung (CRUD)
│   ├── ernaehrungsdaten.py        # Produktkatalog, Flaschen-/Verpflegungslogik, Feedzonen
│   ├── streckenanalys.py          # GPX/CSV-Import, Streckenmetriken, Zielzeit- & Zeitschätzung
│   ├── trainingsanalys.py         # FIT/GPX/CSV-Trainingsimport, FTP & Leistungskurve
│   └── visualisierungen.py        # Plotly-Diagramme: Karte, Höhenprofil, Leistungskurve
├── data/
│   ├── athletes.json              # Gespeicherte Athletenprofile
│   ├── nutrition_products.json    # Verpflegungsprodukt-Katalog (Gels, Drinks)
│   ├── routes/                    # Gespeicherte Streckendateien (.gpx/.csv)
│   └── trainings/                 # Trainingsdateien je Athlet (Unterordner nach Athleten-ID)
├── .streamlit/config.toml         # Theme-Konfiguration (Farben, Font)
└── pyproject.toml                 # Abhängigkeiten (PDM)
```

## Installation

Voraussetzung: Python ≥ 3.11 und [PDM](https://pdm-project.org/).

```bash
pdm install
```

## Starten

```bash
pdm run streamlit run main.py
```

Alternativ über das hinterlegte PDM-Script:

```bash
pdm run start
```

Die App ist danach unter `http://localhost:8501` erreichbar.

## Bedienung

1. **Athlet anlegen/auswählen** – links oben über die Athleten-Auswahl bzw. den "+"-Button.
2. **Strecke einstellen** – gespeicherte Strecke wählen, löschen oder neue GPX/CSV-Datei hochladen (mit Bestätigung); die Zielzeit wird automatisch vorgeschlagen und lässt sich im selben Bereich über Stunden/Minuten-Felder frei anpassen.
3. **Verpflegung einstellen** – Flaschenanzahl, -größe und -inhalt (bei Marken mit mehreren Produkten zusätzlich die Produktlinie) sowie Gel-Hersteller/Produktlinie festlegen; die Kohlenhydratrate lässt sich dort ebenfalls anpassen. Erscheint eine Warnung zur Mindesthydrierung, hilft meist eine größere Flasche oder eine zusätzliche Feedzone.
4. **Feedzonen** – bei Bedarf Verpflegungsstationen entlang der Strecke einplanen: Position (km) sowie Anzahl/Größe/Inhalt der dort übergebenen Flaschen und Anzahl der Gele festlegen.
5. **Trainingsdaten** – rechts können Trainingsdateien (auch mehrere gleichzeitig) hochgeladen, umbenannt oder gelöscht werden; FTP und Leistungskurve werden automatisch aus allen Dateien des Athleten berechnet.
6. **PDF exportieren** – über den Button "Save Plan (PDF)" links unten.

Über die Checkbox "Streamlit-Menü anzeigen" unten links lässt sich bei Bedarf die native Streamlit-Werkzeugleiste (Rerun, Settings, Deploy, …) wieder einblenden, die standardmäßig ausgeblendet ist.

## Datenablage

Alle Daten werden lokal im `data/`-Verzeichnis als JSON bzw. als Rohdateien gespeichert – es wird keine externe Datenbank benötigt. Trainingsdateien liegen je Athlet in einem eigenen, nach Athleten-ID benannten Unterordner unter `data/trainings/`.

## Tech-Stack

- [Streamlit](https://streamlit.io/) – UI-Framework
- [Plotly](https://plotly.com/python/) + [Kaleido](https://github.com/plotly/Kaleido) – interaktive Diagramme und deren Export als Bild (für die PDF)
- [pandas](https://pandas.pydata.org/) / [numpy](https://numpy.org/) – Datenverarbeitung
- [gpxpy](https://github.com/tkrajina/gpxpy) / [fitparse](https://github.com/dtcooper/python-fitparse) – Einlesen von GPX- bzw. FIT-Dateien
- [fpdf2](https://github.com/py-pdf/fpdf2) / [Pillow](https://python-pillow.org/) – PDF-Erstellung
