"""Trainingsanalyse: Einlesen von Trainingsdaten, Berechnung von FTP, MaxHR und Leistungskurve."""

from __future__ import annotations

import gzip
import io
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

COLUMN_ALIASES: dict[str, list[str]] = {
    "power": ["power", "power_w", "watts", "w", "leistung"],
    "heart_rate": ["heart_rate", "heart_rate_bpm", "hr", "heartrate", "pulse", "herzfrequenz"],
    "cadence": ["cadence", "cadence_rpm", "cad", "trittfrequenz"],
    "speed": ["speed", "speed_kmh", "velocity", "geschwindigkeit"],
    "elevation": ["elevation", "elevation_m", "altitude", "alt", "hoehe", "höhe"],
    "latitude": ["latitude", "lat", "breitengrad"],
    "longitude": ["longitude", "lon", "lng", "laengengrad"],
    "timestamp": ["timestamp", "time", "datetime", "date_time", "zeit"],
}

POWER_CURVE_DURATIONS: dict[str, int] = {
    "5s": 5,
    "10s": 10,
    "30s": 30,
    "1min": 60,
    "5min": 300,
    "10min": 600,
    "20min": 1200,
    "60min": 3600,
    "90min": 5400,
    "2h": 7200,
    "3h": 10800,
    "4h": 14400,
    "5h": 18000,
    "6h": 21600,
    "8h": 28800,
    "10h": 36000,
    "12h": 43200,
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Benennt Spalten auf standardisierte interne Namen um."""
    lower_map = {c.lower().strip(): c for c in df.columns}
    rename: dict[str, str] = {}
    for std_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map and std_name not in rename.values():
                rename[lower_map[alias]] = std_name
                break
    return df.rename(columns=rename)


def load_training_data(filepath: str | Path) -> pd.DataFrame:
    """
    Lädt eine Trainingsdatei (.csv, .fit oder .gpx, auch gzip-komprimiert)
    und normalisiert die Spalten.

    Strava-Exports liefern Aktivitäten oft gzip-komprimiert (.fit.gz, .gpx.gz);
    diese werden transparent entpackt. Erwartet mindestens eine Zeitspalte sowie
    Leistungs- oder Herzfrequenzdaten. Unterstützte Spalten: timestamp, power,
    heart_rate, cadence, speed, elevation, latitude, longitude.
    """
    name = Path(filepath).name.lower()

    if name.endswith(".gz"):
        content = gzip.decompress(Path(filepath).read_bytes())
        inner_name = name[:-3]
        if inner_name.endswith(".fit"):
            return load_training_data_fit(io.BytesIO(content))
        if inner_name.endswith(".gpx"):
            return load_training_data_gpx(content)
        return _load_training_csv(io.BytesIO(content))

    if name.endswith(".fit"):
        return load_training_data_fit(filepath)

    if name.endswith(".gpx"):
        return load_training_data_gpx(Path(filepath).read_bytes())

    return _load_training_csv(filepath)


def _load_training_csv(source) -> pd.DataFrame:
    """Lädt und normalisiert Trainingsdaten aus einer CSV-Quelle (Pfad oder Bytes-Puffer)."""
    df = pd.read_csv(source, sep=None, engine="python")
    df = _normalize_columns(df)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    for col in ["power", "heart_rate", "cadence", "speed", "elevation"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_training_data_fit(source) -> pd.DataFrame:
    """
    Lädt eine Garmin/Strava-FIT-Datei (Pfad oder Bytes-Puffer) und normalisiert
    sie auf dieselben Spalten wie CSV-Importe.

    Positionsdaten liegen im FIT-Format als Semicircles vor und werden in
    Dezimalgrad umgerechnet; Geschwindigkeit wird von m/s in km/h umgerechnet.
    """
    import fitparse

    fitfile = fitparse.FitFile(str(source) if isinstance(source, (str, Path)) else source)
    rows: list[dict] = []
    for record in fitfile.get_messages("record"):
        values = {d.name: d.value for d in record}
        rows.append(
            {
                "timestamp": values.get("timestamp"),
                "power": values.get("power"),
                "heart_rate": values.get("heart_rate"),
                "cadence": values.get("cadence"),
                "speed": values.get("enhanced_speed", values.get("speed")),
                "elevation": values.get("enhanced_altitude", values.get("altitude")),
                "latitude": values.get("position_lat"),
                "longitude": values.get("position_long"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("FIT-Datei enthält keine Aufzeichnungsdaten (record messages).")

    semicircle_to_deg = 180.0 / (2**31)
    for col in ("latitude", "longitude"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") * semicircle_to_deg

    if "speed" in df.columns:
        df["speed"] = pd.to_numeric(df["speed"], errors="coerce") * 3.6

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    for col in ["power", "heart_rate", "cadence", "elevation"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return _drop_empty_sensor_columns(df)


def load_training_data_gpx(content: bytes) -> pd.DataFrame:
    """
    Lädt eine Trainings-GPX-Datei und normalisiert sie auf dieselben Spalten
    wie CSV-/FIT-Importe.

    Strava-Exports betten Power/Herzfrequenz/Kadenz als GPX-Erweiterungen ein
    (das nicht-namensraum-gebundene <power>-Element sowie das Garmin
    TrackPointExtension-Schema mit <gpxtpx:hr>/<gpxtpx:cad>). gpxpy liefert
    diese als rohe XML-Elemente zurück, die hier namensraum-unabhängig anhand
    des lokalen Tag-Namens ausgelesen werden.
    """
    import gpxpy

    gpx = gpxpy.parse(content.decode("utf-8", errors="replace"))
    rows: list[dict] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                ext_values: dict[str, str] = {}
                for ext in pt.extensions:
                    for el in ext.iter():
                        local_tag = el.tag.split("}")[-1]
                        if el.text and el.text.strip():
                            ext_values.setdefault(local_tag, el.text.strip())

                rows.append({
                    "timestamp": pt.time,
                    "power": ext_values.get("power"),
                    "heart_rate": ext_values.get("hr"),
                    "cadence": ext_values.get("cad"),
                    "elevation": pt.elevation,
                    "latitude": pt.latitude,
                    "longitude": pt.longitude,
                })

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("GPX-Datei enthält keine verwertbaren Trackpunkte.")

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    for col in ["power", "heart_rate", "cadence", "elevation"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return _drop_empty_sensor_columns(df)


def _drop_empty_sensor_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Entfernt durchgehend leere Sensor-Spalten (z.B. Power auf einem Gerät ohne
    Leistungsmesser), damit sie wie eine fehlende Spalte behandelt werden statt
    fälschlich als lauter Nullen in die Auswertung einzufließen.
    """
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    return df.drop(columns=empty_cols)


def _get_power_array(df: pd.DataFrame) -> np.ndarray:
    """
    Gibt ein 1-Sekunden-resampled Leistungsarray zurück.

    Lücken in der Aufzeichnung (z.B. Pausen, Signalverlust) werden mit 0
    aufgefüllt statt mit dem letzten Wert fortzuschreiben: ein Vorwärtsfüllen
    (ffill) würde über mehrminütige Aufzeichnungslücken hinweg einen
    fiktiven Dauereinsatz erzeugen und FTP/Leistungskurve verfälschen.
    Falls kein Zeitstempel vorhanden ist, wird ein Eintrag pro Zeile als
    1-Sekunden-Intervall angenommen.
    """
    if "power" not in df.columns:
        return np.array([])

    if "timestamp" in df.columns:
        resampled = df.set_index("timestamp")["power"].resample("1s").mean().fillna(0).values
        return resampled.astype(float)

    return df["power"].fillna(0).values.astype(float)


def calculate_power_curve(df: pd.DataFrame) -> dict[str, float]:
    """
    Berechnet die mittlere Maximalleistung (MMP) für verschiedene Zeitdauern.

    Für jede Dauer wird das Maximum aller Durchschnittswerte über ein
    gleitendes Fenster der entsprechenden Länge berechnet.
    Gibt ein leeres Dict zurück wenn keine Leistungsdaten vorhanden sind.
    """
    power = _get_power_array(df)
    if len(power) == 0:
        return {}

    cumsum = np.cumsum(np.insert(power, 0, 0.0))
    result: dict[str, float] = {}

    for label, seconds in POWER_CURVE_DURATIONS.items():
        if len(power) >= seconds:
            window_avgs = (cumsum[seconds:] - cumsum[:-seconds]) / seconds
            result[label] = round(float(np.max(window_avgs)), 1)

    return result


def calculate_max_hr(df: pd.DataFrame) -> Optional[int]:
    """Gibt die maximale Herzfrequenz aus den Trainingsdaten zurück."""
    if "heart_rate" not in df.columns:
        return None
    max_hr = df["heart_rate"].max()
    return int(max_hr) if pd.notna(max_hr) else None


def calculate_hr_zones(max_hr: int) -> dict[str, tuple[int, int]]:
    """
    Berechnet die Herzfrequenz-Trainingszonen basierend auf der MaxHR.

    Verwendet das 5-Zonen-Modell nach Coggan/Allen (% der maximalen HF).
    """
    return {
        "Zone 1 – Regeneration": (0, int(max_hr * 0.60)),
        "Zone 2 – Grundlage": (int(max_hr * 0.60), int(max_hr * 0.70)),
        "Zone 3 – Tempo": (int(max_hr * 0.70), int(max_hr * 0.80)),
        "Zone 4 – Schwelle": (int(max_hr * 0.80), int(max_hr * 0.90)),
        "Zone 5 – VO2max": (int(max_hr * 0.90), max_hr),
    }


def aggregate_athlete_data(filepaths: list[str]) -> dict:
    """
    Aggregiert Trainingsdaten aus mehreren Dateien zu Athletenkennwerten.

    Die Leistungskurve wird über alle Dateien hinweg kombiniert (bester
    Durchschnittswert je Dauer, unabhängig davon aus welcher Datei er stammt) –
    nicht nur aus der einen Datei mit der höchsten Einzel-FTP übernommen.
    Dadurch trägt z.B. eine lange Ultra-Ausfahrt auch dann zu den langen
    Dauern (2h, 4h, ...) bei, wenn ein anderer, kürzerer Ritt die beste
    20-Minuten-Leistung geliefert hat. Gibt ein Dict mit ftp, max_hr und
    power_curve zurück.
    """
    combined_curve: dict[str, float] = {}
    best_max_hr: Optional[int] = None

    for fp in filepaths:
        try:
            df = load_training_data(fp)
        except Exception:
            continue

        for label, value in calculate_power_curve(df).items():
            if label not in combined_curve or value > combined_curve[label]:
                combined_curve[label] = value

        max_hr = calculate_max_hr(df)
        if max_hr is not None and (best_max_hr is None or max_hr > best_max_hr):
            best_max_hr = max_hr

    best_ftp: Optional[float] = None
    if "20min" in combined_curve:
        best_ftp = round(combined_curve["20min"] * 0.95, 1)

    return {
        "ftp": best_ftp,
        "max_hr": best_max_hr,
        "power_curve": combined_curve,
    }
