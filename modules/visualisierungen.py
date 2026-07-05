"""Visualisierungen: Karte, Höhenprofil, Leistungskurve und Hilfsfunktionen für Diagramme."""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from modules.trainingsanalys import POWER_CURVE_DURATIONS

ROUTE_COLOR = "#7C3AED"
GEL_COLOR = "#111827"
DRINK_COLOR = "#16a34a"
FOOD_COLOR = "#f59e0b"
CLIMB_COLOR = "#ef4444"


def _zoom_from_extent(lat_range: float, lon_range: float) -> int:
    """Berechnet einen geeigneten Zoom-Level für die gegebene geografische Ausdehnung."""
    max_range = max(lat_range, lon_range)
    if max_range == 0:
        return 13
    zoom = int(round(8.5 - math.log2(max_range * 40.0 + 0.001)))
    return max(6, min(15, zoom))


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

    if nutrition_points:
        type_config = {
            "gel": (GEL_COLOR, "Gel"),
            "drink": (DRINK_COLOR, "Drink"),
            "food": (FOOD_COLOR, "Riegel"),
        }
        for ptype, (color, label) in type_config.items():
            group = [p for p in nutrition_points if p.get("type") == ptype]
            if not group:
                continue
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

    center_lat = float(route_df["lat"].mean())
    center_lon = float(route_df["lon"].mean())
    zoom = _zoom_from_extent(
        float(route_df["lat"].max() - route_df["lat"].min()),
        float(route_df["lon"].max() - route_df["lon"].min()),
    )

    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=zoom),
        margin=dict(l=0, r=0, t=0, b=0),
        height=380,
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
            color = DRINK_COLOR if p.get("type") == "drink" else (FOOD_COLOR if p.get("type") == "food" else GEL_COLOR)
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
        return pd.DataFrame(columns=["Time", "Nutrition", "KH (g)", "KH gesamt (g)"])

    rows = []
    for p in nutrition_points:
        total_min = int(p["time_min"])
        h, m = divmod(total_min, 60)
        rows.append({
            "Time": f"{h:02d}:{m:02d}",
            "Nutrition": p["product_name"],
            "KH (g)": int(p["carbs_g"]),
            "KH gesamt (g)": int(p["cumulative_carbs_g"]),
        })
    return pd.DataFrame(rows)
