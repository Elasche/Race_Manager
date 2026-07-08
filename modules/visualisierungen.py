"""Visualisierungen: Karte, Höhenprofil, Leistungskurve und Hilfsfunktionen für Diagramme."""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from modules.trainingsanalys import POWER_CURVE_DURATIONS

ROUTE_COLOR = "#7C3AED"
GEL_COLOR = "#FFD600"
DRINK_COLOR = "#16a34a"
FOOD_COLOR = "#f59e0b"
CLIMB_COLOR = "#ef4444"
BOTTLE_COLORS = ["#2563EB", "#db2777"]  # Flasche 1, Flasche 2


def _drink_color(bottle_index: Optional[int]) -> str:
    """Gibt die Flaschen-Farbe für ein Drink-Event zurück (Fallback: generisches Grün)."""
    if bottle_index is None:
        return DRINK_COLOR
    return BOTTLE_COLORS[bottle_index % len(BOTTLE_COLORS)]


def _zoom_to_fit_bounds(
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    map_px: float = 700.0, fill_fraction: float = 0.9,
) -> float:
    """
    Berechnet den Zoom-Level, bei dem die gesamte Strecke mit ca. 5-10% Rand
    ins (quadratische) Kartenfenster passt.

    Nutzt die Web-Mercator-Fit-Bounds-Formel (wie bei Google/Mapbox
    getBoundsZoomLevel): Breiten- und Längengrad-Ausdehnung werden getrennt
    in einen Anteil der Weltkarte umgerechnet, der jeweils benötigte Zoom
    berechnet und das Minimum (die restriktivere Achse) verwendet.
    """
    if lat_max <= lat_min and lon_max <= lon_min:
        return 14.0

    def lat_rad(lat: float) -> float:
        s = max(min(math.sin(math.radians(lat)), 0.9999), -0.9999)
        return math.log((1 + s) / (1 - s)) / 2

    lat_fraction = (lat_rad(lat_max) - lat_rad(lat_min)) / math.pi
    lon_fraction = (lon_max - lon_min) / 360.0

    def zoom_for(fraction: float) -> float:
        if fraction <= 0:
            return 20.0
        return math.log2((map_px / 256.0) * fill_fraction / fraction)

    zoom = min(zoom_for(lat_fraction), zoom_for(lon_fraction))
    return max(2.0, min(20.0, zoom))


def create_route_map(
    route_df: pd.DataFrame,
    nutrition_points: Optional[list[dict]] = None,
    key_features: Optional[list[dict]] = None,
) -> go.Figure:
    """
    Erstellt eine interaktive Kartenansicht der Strecke.

    Zeigt die Route als farbige Linie sowie Verpflegungspunkte (Gels schwarz,
    Drinks grün) und erkannte Anstiege (rot) als Marker. Unterstützt Zoom und Pan.
    """
    fig = go.Figure()

    hover = []
    for _, row in route_df.iterrows():
        parts = [f"Höhe: {row.get('elevation', 0):.0f}m"]
        if "distance_km" in row:
            parts.append(f"Distanz: {row['distance_km']:.1f}km")
        if "estimated_time_h" in row:
            h = int(row["estimated_time_h"])
            m = int((row["estimated_time_h"] - h) * 60)
            parts.append(f"Zeit: {h:02d}:{m:02d}h")
        hover.append("<br>".join(parts))

    fig.add_trace(go.Scattermapbox(
        lat=route_df["lat"],
        lon=route_df["lon"],
        mode="lines",
        line=dict(width=4, color=ROUTE_COLOR),
        name="Strecke",
        hovertext=hover,
        hovertemplate="%{hovertext}<extra></extra>",
    ))

    def _add_nutrition_trace(group: list[dict], color: str, label: str) -> None:
        fig.add_trace(go.Scattermapbox(
            lat=[p["lat"] for p in group],
            lon=[p["lon"] for p in group],
            mode="markers+text",
            marker=dict(size=14, color=color),
            text=[p["label"] for p in group],
            textposition="top right",
            textfont=dict(size=12, color=color),
            name=label,
            hovertemplate=(
                "<b>%{text}</b><br>"
                + "<br>".join(
                    f"{p['product_name']}<br>{int(p['time_min'])}min · {p['carbs_g']}g KH"
                    for p in group
                )
                + "<extra></extra>"
            ),
        ))

    if nutrition_points:
        gels = [p for p in nutrition_points if p.get("type") == "gel"]
        foods = [p for p in nutrition_points if p.get("type") == "food"]
        drinks = [p for p in nutrition_points if p.get("type") == "drink"]

        if gels:
            _add_nutrition_trace(gels, GEL_COLOR, "Gel")
        if foods:
            _add_nutrition_trace(foods, FOOD_COLOR, "Riegel")

        bottle_indices = sorted({p["bottle_index"] for p in drinks if p.get("bottle_index") is not None})
        for bi in bottle_indices:
            group = [p for p in drinks if p.get("bottle_index") == bi]
            _add_nutrition_trace(group, _drink_color(bi), f"Flasche {bi + 1}")

        unassigned_drinks = [p for p in drinks if p.get("bottle_index") is None]
        if unassigned_drinks:
            _add_nutrition_trace(unassigned_drinks, DRINK_COLOR, "Drink")

    if key_features:
        climbs = [f for f in key_features if f.get("type") == "climb"]
        summits = [f for f in key_features if f.get("type") == "summit"]
        if climbs:
            fig.add_trace(go.Scattermapbox(
                lat=[f["lat"] for f in climbs],
                lon=[f["lon"] for f in climbs],
                mode="markers+text",
                marker=dict(size=10, color=CLIMB_COLOR, symbol="triangle-up"),
                text=[f["label"] for f in climbs],
                textposition="bottom right",
                textfont=dict(size=9, color=CLIMB_COLOR),
                name="Anstiege",
            ))
        if summits:
            fig.add_trace(go.Scattermapbox(
                lat=[f["lat"] for f in summits],
                lon=[f["lon"] for f in summits],
                mode="markers+text",
                marker=dict(size=10, color="#6b7280"),
                text=[f["label"] for f in summits],
                textposition="top center",
                textfont=dict(size=9, color="#6b7280"),
                name="Gipfel",
            ))

    lat_min, lat_max = float(route_df["lat"].min()), float(route_df["lat"].max())
    lon_min, lon_max = float(route_df["lon"].min()), float(route_df["lon"].max())
    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2
    zoom = _zoom_to_fit_bounds(lat_min, lat_max, lon_min, lon_max)

    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=zoom),
        margin=dict(l=0, r=0, t=0, b=0),
        height=700,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
    )
    return fig


def create_elevation_profile(
    route_df: pd.DataFrame,
    nutrition_points: Optional[list[dict]] = None,
) -> go.Figure:
    """
    Erstellt ein interaktives Höhenprofil der Strecke.

    Die x-Achse zeigt die Distanz in km, die y-Achse die Höhe in Metern.
    Verpflegungspunkte werden als vertikale gestrichelte Linien eingezeichnet.
    Zoom und Pan werden unterstützt für detaillierte Streckenabschnitte.
    """
    fig = go.Figure()

    x_vals = route_df["distance_km"] if "distance_km" in route_df.columns else pd.Series(range(len(route_df)))

    fig.add_trace(go.Scatter(
        x=x_vals,
        y=route_df["elevation"].fillna(0),
        fill="tozeroy",
        fillcolor="rgba(124, 58, 237, 0.15)",
        line=dict(color=ROUTE_COLOR, width=2),
        name="Höhe",
        hovertemplate="Distanz: %{x:.1f}km<br>Höhe: %{y:.0f}m<extra></extra>",
    ))

    if nutrition_points:
        for p in nutrition_points:
            if p.get("type") == "drink":
                color = _drink_color(p.get("bottle_index"))
            elif p.get("type") == "food":
                color = FOOD_COLOR
            else:
                color = GEL_COLOR
            x_pos = p.get("distance_km", 0)
            fig.add_vline(
                x=x_pos,
                line=dict(color=color, width=1.5, dash="dash"),
                annotation=dict(
                    text=p["label"],
                    textangle=-90,
                    font=dict(size=9, color=color),
                    yref="paper",
                    y=1.0,
                ),
            )

    fig.update_layout(
        xaxis_title="Distanz (km)",
        yaxis_title="Höhe (m)",
        height=230,
        margin=dict(l=45, r=15, t=20, b=40),
        showlegend=False,
        dragmode="zoom",
        plot_bgcolor="#F9FAFB",
    )
    return fig


def create_elevation_profile_vertical(
    route_df: pd.DataFrame,
    nutrition_points: Optional[list[dict]] = None,
    width: int = 420,
    height: int = 1550,
) -> go.Figure:
    """
    Erstellt ein vertikales Höhenprofil für den PDF-Ausdruck (Oberrohr-Streifen).

    Die Distanz läuft von unten (0km, Start) nach oben (Ziel), damit der
    Ausdruck als schmaler Streifen aufs Oberrohr geklebt werden kann.
    """
    fig = go.Figure()

    y_vals = route_df["distance_km"] if "distance_km" in route_df.columns else pd.Series(range(len(route_df)))

    fig.add_trace(go.Scatter(
        x=route_df["elevation"].fillna(0),
        y=y_vals,
        fill="tozerox",
        fillcolor="rgba(124, 58, 237, 0.15)",
        line=dict(color=ROUTE_COLOR, width=2),
        name="Höhe",
        hoverinfo="skip",
    ))

    if nutrition_points:
        for p in nutrition_points:
            if p.get("type") == "drink":
                color = _drink_color(p.get("bottle_index"))
            elif p.get("type") == "food":
                color = FOOD_COLOR
            else:
                color = GEL_COLOR
            y_pos = p.get("distance_km", 0)
            fig.add_hline(
                y=y_pos,
                line=dict(color=color, width=1.2, dash="dash"),
                annotation=dict(text=p["label"], font=dict(size=10, color=color)),
                annotation_position="right",
            )

    fig.update_layout(
        xaxis_title="Höhe (m)",
        yaxis_title="Distanz (km)",
        width=width,
        height=height,
        margin=dict(l=60, r=110, t=20, b=40),
        showlegend=False,
        plot_bgcolor="#F9FAFB",
        font=dict(size=13),
    )
    return fig


def create_power_curve(power_curve: dict[str, float], ftp: Optional[float] = None) -> go.Figure:
    """
    Visualisiert die Leistungskurve (Mean Maximal Power) eines Athleten.

    X-Achse: Zeitdauern von 5s bis zu mehreren Stunden (abhängig von der
    längsten verfügbaren Aktivität des Athleten), Y-Achse: maximale
    Durchschnittsleistung in Watt. Optional wird die FTP als horizontale
    Linie eingezeichnet.
    """
    fig = go.Figure()

    if not power_curve:
        fig.add_annotation(
            text="Keine Trainingsdaten",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=12, color="#9ca3af"),
        )
        fig.update_layout(
            height=170, margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(visible=False, range=[0, 1]),
            yaxis=dict(visible=False, range=[0, 1]),
        )
        return fig

    labels = [d for d in POWER_CURVE_DURATIONS if d in power_curve]
    values = [power_curve[d] for d in labels]

    fig.add_trace(go.Scatter(
        x=labels, y=values,
        mode="lines+markers",
        line=dict(color=DRINK_COLOR, width=2),
        marker=dict(size=5, color=DRINK_COLOR),
        fill="tozeroy",
        fillcolor="rgba(22, 163, 74, 0.12)",
        hovertemplate="%{x}: <b>%{y:.0f}W</b><extra></extra>",
    ))

    if ftp:
        fig.add_hline(
            y=ftp,
            line=dict(color="#ef4444", width=1.5, dash="dot"),
            annotation_text=f"FTP {ftp:.0f}W",
            annotation_font_size=10,
            annotation_font_color="#ef4444",
        )

    fig.update_layout(
        yaxis_title="W",
        height=160,
        margin=dict(l=35, r=10, t=10, b=30),
        showlegend=False,
        plot_bgcolor="#F9FAFB",
    )
    return fig


def create_nutrition_table(nutrition_points: list[dict]) -> pd.DataFrame:
    """
    Erstellt einen formatierten DataFrame für die Verpflegungstabelle.

    Enthält geplante Zeit (HH:MM), Produkt, Kohlenhydrate und Gesamtsumme.
    """
    if not nutrition_points:
        return pd.DataFrame(columns=["Time", "Flasche", "Nutrition", "KH (g)", "KH gesamt (g)"])

    rows = []
    for p in nutrition_points:
        total_min = int(p["time_min"])
        h, m = divmod(total_min, 60)
        bottle_index = p.get("bottle_index")
        rows.append({
            "Time": f"{h:02d}:{m:02d}",
            "Flasche": f"F{bottle_index + 1}" if bottle_index is not None else "–",
            "Nutrition": p["product_name"],
            "KH (g)": int(p["carbs_g"]),
            "KH gesamt (g)": int(p["cumulative_carbs_g"]),
        })
    return pd.DataFrame(rows)
