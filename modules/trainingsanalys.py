"""Trainingsanalyse: Einlesen von Trainingsdaten, Berechnung von FTP, MaxHR und Leistungskurve."""

from __future__ import annotations

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
    Lädt eine Trainingsdaten-CSV-Datei und normalisiert die Spalten.

    Erwartet mindestens eine Zeitspalte sowie Leistungs- oder Herzfrequenzdaten.
    Unterstützte Spalten: timestamp, power, heart_rate, cadence, speed,
    elevation, latitude, longitude.
    """
    df = pd.read_csv(filepath, sep=None, engine="python")
    df = _normalize_columns(df)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    for col in ["power", "heart_rate", "cadence", "speed", "elevation"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _get_power_array(df: pd.DataFrame) -> np.ndarray:
    """
    Gibt ein 1-Sekunden-resampled Leistungsarray zurück.

    Falls kein Zeitstempel vorhanden ist, wird ein Eintrag pro Zeile als
    1-Sekunden-Intervall angenommen.
    """
    if "power" not in df.columns:
        return np.array([])

    if "timestamp" in df.columns:
        resampled = (
            df.set_index("timestamp")["power"]
            .resample("1s")
            .mean()
            .ffill()
            .fillna(0)
            .values
        )
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


def calculate_ftp(df: pd.DataFrame) -> Optional[float]:
    """
    Schätzt die Functional Threshold Power (FTP) aus den Trainingsdaten.

    Verwendet die beste 20-Minuten-Durchschnittsleistung multipliziert mit 0.95.
    Als Fallback wird die 10-Minuten-Leistung mit 0.90 verwendet.
    """
    curve = calculate_power_curve(df)
    if "20min" in curve:
        return round(curve["20min"] * 0.95, 1)
    if "10min" in curve:
        return round(curve["10min"] * 0.90, 1)
    return None


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

    Nimmt die beste FTP und maximale MaxHR über alle Trainingsdateien.
    Gibt ein Dict mit ftp, max_hr und power_curve zurück.
    """
    best_ftp: Optional[float] = None
    best_max_hr: Optional[int] = None
    best_power_curve: dict[str, float] = {}

    for fp in filepaths:
        try:
            df = load_training_data(fp)
            ftp = calculate_ftp(df)
            max_hr = calculate_max_hr(df)
            curve = calculate_power_curve(df)

            if ftp is not None and (best_ftp is None or ftp > best_ftp):
                best_ftp = ftp
                best_power_curve = curve

            if max_hr is not None and (best_max_hr is None or max_hr > best_max_hr):
                best_max_hr = max_hr
        except Exception:
            continue

    return {
        "ftp": best_ftp,
        "max_hr": best_max_hr,
        "power_curve": best_power_curve,
    }
