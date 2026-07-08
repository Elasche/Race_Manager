"""Streckenanalyse: Einlesen von GPS-Daten, Schlüsselstellen-Erkennung und Zielzeit-Kalkulation."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from modules.ernaehrungsdaten import NutritionEvent

try:
    import gpxpy
    _HAS_GPXPY = True
except ImportError:
    _HAS_GPXPY = False

ROUTES_DIR = Path("data") / "routes"


def list_saved_routes() -> list[str]:
    """Gibt die Dateinamen aller gespeicherten Streckendateien zurück."""
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        p.name for p in ROUTES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".gpx", ".csv")
    )


def save_route_file(filename: str, content: bytes) -> Path:
    """Speichert eine hochgeladene Streckendatei dauerhaft in data/routes."""
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    path = ROUTES_DIR / filename
    path.write_bytes(content)
    return path


def load_saved_route(filename: str) -> pd.DataFrame:
    """Lädt eine gespeicherte Streckendatei anhand ihres Dateinamens."""
    path = ROUTES_DIR / filename
    return load_route(path.read_bytes(), filename)


def delete_route_file(filename: str) -> None:
    """Löscht eine gespeicherte Streckendatei dauerhaft."""
    path = ROUTES_DIR / filename
    if path.exists():
        path.unlink()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Berechnet die Luftlinienentfernung zwischen zwei GPS-Koordinaten in Kilometern."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Berechnet kumulative Distanz und Steigung für alle Streckenpunkte."""
    distances = [0.0]
    for i in range(1, len(df)):
        d = _haversine_km(
            df.iloc[i - 1]["lat"], df.iloc[i - 1]["lon"],
            df.iloc[i]["lat"], df.iloc[i]["lon"],
        )
        distances.append(distances[-1] + d)
    df = df.copy()
    df["distance_km"] = distances

    # Fehlende Höhenwerte linear interpolieren statt mit 0 aufzufüllen,
    # sonst entstehen bei lückenhaften GPX-Tracks künstliche Klippen.
    df["elevation"] = df["elevation"].interpolate(limit_direction="both")
    elev = df["elevation"].fillna(0).values
    dist_m = np.array(distances) * 1000.0
    grades = [0.0]
    for i in range(1, len(df)):
        seg_m = dist_m[i] - dist_m[i - 1]
        grades.append((elev[i] - elev[i - 1]) / seg_m * 100.0 if seg_m > 0 else 0.0)
    df["grade_pct"] = grades
    return df


def load_route_gpx(content: bytes) -> pd.DataFrame:
    """
    Lädt eine GPX-Datei und gibt die Streckenpunkte als DataFrame zurück.

    Parst Track-Segmente und Wegpunkte. Gibt DataFrame mit Spalten
    lat, lon, elevation, distance_km und grade_pct zurück.
    """
    if not _HAS_GPXPY:
        raise ImportError("gpxpy ist nicht installiert. Bitte CSV-Format verwenden.")

    gpx = gpxpy.parse(content.decode("utf-8", errors="replace"))
    points: list[dict] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append({
                    "lat": pt.latitude,
                    "lon": pt.longitude,
                    "elevation": pt.elevation if pt.elevation is not None else np.nan,
                })

    if not points:
        for wp in gpx.waypoints:
            points.append({
                "lat": wp.latitude, "lon": wp.longitude,
                "elevation": wp.elevation if wp.elevation is not None else np.nan,
            })

    if not points:
        raise ValueError("GPX-Datei enthält keine verwertbaren Streckenpunkte.")

    df = pd.DataFrame(points)
    return _add_derived_columns(df)


def load_route_csv(content: bytes) -> pd.DataFrame:
    """
    Lädt eine CSV-Streckendatei mit GPS-Koordinaten und optionalen Höhendaten.

    Erkennt automatisch Spaltennamen für Breite, Länge und Höhe.
    """
    df = pd.read_csv(io.BytesIO(content), sep=None, engine="python")
    col_lower = {c.lower().strip(): c for c in df.columns}

    rename: dict[str, str] = {}
    for target, aliases in [
        ("lat", ["lat", "latitude", "breitengrad"]),
        ("lon", ["lon", "lng", "longitude", "laengengrad"]),
        ("elevation", ["elevation", "elevation_m", "altitude", "alt", "hoehe", "höhe"]),
    ]:
        for alias in aliases:
            if alias in col_lower:
                rename[col_lower[alias]] = target
                break

    df = df.rename(columns=rename)
    for col in ["lat", "lon", "elevation"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    if "elevation" not in df.columns:
        df["elevation"] = 0.0

    return _add_derived_columns(df)


def load_route(content: bytes, filename: str) -> pd.DataFrame:
    """
    Lädt eine Streckendatei (GPX oder CSV) und gibt einen normalisierten DataFrame zurück.

    GPX wird bevorzugt wenn gpxpy installiert ist, sonst nur CSV möglich.
    """
    if filename.lower().endswith(".gpx"):
        return load_route_gpx(content)
    return load_route_csv(content)


def calculate_route_metrics(df: pd.DataFrame) -> dict:
    """
    Berechnet Kennzahlen der Strecke: Distanz, Höhenmeter, Min/Max-Höhe.

    Gibt ein Dict mit total_distance_km, elevation_gain_m, elevation_loss_m,
    max_elevation_m und min_elevation_m zurück.
    """
    total_distance = float(df["distance_km"].max()) if "distance_km" in df.columns else 0.0
    elev_diffs = np.diff(df["elevation"].fillna(0).values)
    return {
        "total_distance_km": round(total_distance, 2),
        "elevation_gain_m": round(float(elev_diffs[elev_diffs > 0].sum()), 0),
        "elevation_loss_m": round(float(abs(elev_diffs[elev_diffs < 0].sum())), 0),
        "max_elevation_m": round(float(df["elevation"].max()), 0),
        "min_elevation_m": round(float(df["elevation"].min()), 0),
    }


def detect_key_features(df: pd.DataFrame) -> list[dict]:
    """
    Erkennt Schlüsselstellen auf der Strecke: Anstiege und Gipfel.

    Ein Anstieg wird erkannt wenn auf einem Abschnitt von maximal 3km
    mindestens 80 Höhenmeter überwunden werden. Gipfel sind lokale
    Höhenmaxima mit einer Prominenz von über 50m.
    """
    if len(df) < 10:
        return []

    elev = df["elevation"].fillna(0).values
    dist = df["distance_km"].values
    features: list[dict] = []

    smooth_w = max(5, min(30, len(elev) // 20))
    smooth = np.convolve(elev, np.ones(smooth_w) / smooth_w, mode="same")

    CLIMB_GAIN_M = 80.0
    CLIMB_MAX_KM = 3.0

    i = 0
    while i < len(df) - 1:
        j = i + 1
        while j < len(df) and (dist[j] - dist[i]) < CLIMB_MAX_KM:
            j += 1
        j = min(j, len(df) - 1)
        gain = smooth[j] - smooth[i]
        seg_km = dist[j] - dist[i]
        if gain >= CLIMB_GAIN_M and seg_km > 0:
            avg_grade = gain / (seg_km * 1000.0) * 100.0
            features.append({
                "type": "climb",
                "label": f"+{round(gain)}m",
                "start_idx": int(i),
                "end_idx": int(j),
                "lat": float(df.iloc[i]["lat"]),
                "lon": float(df.iloc[i]["lon"]),
                "elevation_gain_m": round(gain),
                "distance_km": round(seg_km, 2),
                "avg_grade_pct": round(avg_grade, 1),
            })
            i = j
        else:
            i += 1

    for i in range(1, len(smooth) - 1):
        if smooth[i] > smooth[i - 1] and smooth[i] > smooth[i + 1]:
            look = 60
            left = smooth[max(0, i - look)]
            right = smooth[min(len(smooth) - 1, i + look)]
            prominence = smooth[i] - max(left, right)
            if prominence > 50:
                features.append({
                    "type": "summit",
                    "label": f"Gipfel {round(smooth[i])}m",
                    "idx": int(i),
                    "lat": float(df.iloc[i]["lat"]),
                    "lon": float(df.iloc[i]["lon"]),
                    "elevation_m": round(float(smooth[i])),
                })

    return features


def estimate_time_at_points(route_df: pd.DataFrame, target_time_h: float) -> pd.DataFrame:
    """
    Schätzt die verstrichene Rennzeit an jedem Streckenpunkt.

    Berücksichtigt die Geländeneigung: Anstiege verlängern die Zeit,
    moderate Abfahrten verkürzen sie. Die Gesamtzeit wird auf die
    Zielzeit skaliert.
    """
    df = route_df.copy()
    if len(df) < 2:
        df["estimated_time_h"] = 0.0
        return df

    elev = df["elevation"].fillna(0).values
    dist = df["distance_km"].values
    seg_len = np.diff(dist)
    seg_elev = np.diff(elev)

    speed_factors = np.ones(len(seg_len))
    for i, (d, e) in enumerate(zip(seg_len, seg_elev)):
        if d > 0:
            grade = (e / (d * 1000.0)) * 100.0
            if grade > 2.0:
                speed_factors[i] = max(0.25, 1.0 - grade * 0.09)
            elif grade < -5.0:
                speed_factors[i] = min(1.4, 1.0 + abs(grade) * 0.025)

    seg_times = np.where(seg_len > 0, seg_len / speed_factors, 0.0)
    total_rel = seg_times.sum()

    if total_rel == 0:
        df["estimated_time_h"] = np.linspace(0, target_time_h, len(df))
        return df

    scale = target_time_h / total_rel
    cum_times = np.concatenate([[0.0], np.cumsum(seg_times * scale)])
    df["estimated_time_h"] = cum_times
    return df


def time_at_distance(route_df: pd.DataFrame, distance_km: float) -> float:
    """
    Gibt die geschätzte Renndauer (h) an einem gegebenen Streckenkilometer zurück.

    Erwartet ein route_df mit "estimated_time_h"-Spalte (siehe estimate_time_at_points).
    """
    if route_df.empty or "estimated_time_h" not in route_df.columns:
        return 0.0
    idx = int(np.argmin(np.abs(route_df["distance_km"].values - distance_km)))
    return float(route_df.iloc[idx]["estimated_time_h"])


def calculate_target_time(route_df: pd.DataFrame, ftp: Optional[float] = None) -> float:
    """
    Schlägt eine Zielzeit für die Strecke vor.

    Basisgeschwindigkeit von 25 km/h wird durch Geländeneigung und
    optional durch das FTP des Athleten (Referenz 250W) angepasst.
    """
    metrics = calculate_route_metrics(route_df)
    total_km = metrics["total_distance_km"]
    gain_m = metrics["elevation_gain_m"]

    if total_km <= 0:
        return 2.0

    gradient_factor = gain_m / (total_km * 10.0)
    adjusted_speed = 25.0 * max(0.3, 1.0 - gradient_factor * 0.10)

    base_time = total_km / adjusted_speed

    if ftp and ftp > 0:
        ftp_factor = (ftp / 250.0) ** 0.3
        base_time /= ftp_factor

    return round(max(0.5, base_time), 2)


def suggest_nutrition_points(
    route_df: pd.DataFrame,
    nutrition_events: list[NutritionEvent],
) -> list[dict]:
    """
    Ordnet Verpflegungsereignisse ihren GPS-Koordinaten auf der Strecke zu.

    Findet für jede geplante Verpflegungszeit den nächstgelegenen Streckenpunkt
    anhand der geschätzten Rennzeit.
    """
    if route_df.empty or not nutrition_events:
        return []

    has_time = "estimated_time_h" in route_df.columns
    times = route_df["estimated_time_h"].values if has_time else None
    total_time_h = float(route_df["estimated_time_h"].max()) if has_time else 2.0

    points: list[dict] = []
    for event in nutrition_events:
        event_h = event.time_min / 60.0

        if times is not None:
            idx = int(np.argmin(np.abs(times - event_h)))
        else:
            frac = min(1.0, event_h / max(total_time_h, 0.001))
            idx = int(frac * (len(route_df) - 1))

        idx = max(0, min(idx, len(route_df) - 1))
        row = route_df.iloc[idx]

        points.append({
            "time_min": event.time_min,
            "time_h": event_h,
            "label": event.label,
            "type": event.product.type,
            "product_name": event.product.name,
            "carbs_g": event.product.carbs_g,
            "bottle_index": event.product.bottle_index,
            "cumulative_carbs_g": event.cumulative_carbs_g,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "elevation_m": float(row.get("elevation", 0)),
            "distance_km": float(row.get("distance_km", 0)),
        })

    return points
