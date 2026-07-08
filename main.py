"""Race Manager – Hauptanwendung für MTB-Rennplanung (Pacing & Ernährungsstrategie)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from modules.athletenverwaltung import (
    Athlete,
    add_training_file,
    assign_training_file,
    create_athlete,
    decode_photo,
    delete_athlete,
    delete_training_file,
    list_athlete_training_files,
    list_unassigned_training_files,
    load_athletes,
    normalize_photo_bytes,
    rename_training_file,
    update_athlete,
)
from modules.ernaehrungsdaten import (
    BOTTLE_SIZES_ML,
    Bottle,
    build_feed_zone_recommendation,
    build_selected_products,
    calculate_nutrition_plan,
    check_hydration_capacity,
    get_brands_by_type,
    get_products_by_brand,
    load_products,
)
from modules.streckenanalys import (
    calculate_route_metrics,
    calculate_target_time,
    delete_route_file,
    detect_key_features,
    estimate_time_at_points,
    list_saved_routes,
    load_route,
    load_saved_route,
    save_route_file,
    suggest_nutrition_points,
    time_at_distance,
)
from modules.trainingsanalys import aggregate_athlete_data
from modules.visualisierungen import (
    create_elevation_profile,
    create_elevation_profile_vertical,
    create_nutrition_table,
    create_power_curve,
    create_route_map,
)

# ── Seitenkonfiguration ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Race Manager",
    page_icon="🚵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0.5rem; }
    .athlete-card {
        background: #F3F4F6; border-radius: 10px;
        padding: 8px 14px; margin-bottom: 6px;
        cursor: pointer; border: 2px solid transparent;
    }
    .athlete-card.selected { border-color: #7C3AED; background: #EDE9FE; }
    .metric-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
    .section-label { font-size: 0.75rem; color: #6B7280; text-transform: uppercase;
                     letter-spacing: 0.05em; margin-top: 12px; margin-bottom: 4px; }

    .app-header-bar {
        background: #FFFFFF;
        border-radius: 16px;
        padding: 0.6rem 1rem;
        text-align: center;
        font-size: 1.7rem;
        font-weight: 700;
        color: #4C1D95;
        box-shadow: 0 8px 20px rgba(76, 29, 149, 0.20);
        margin-bottom: 1.1rem;
    }

    /* ── Modernes Panel-Layout: kräftige lila Seitenpanels, helle Mitte ── */
    .stApp { background: linear-gradient(160deg, #F5F3FF 0%, #ECE9FB 100%); }

    div[data-testid="stColumn"]:has(.panel-marker-left),
    div[data-testid="stColumn"]:has(.panel-marker-right) {
        background: linear-gradient(165deg, #6D28D9 0%, #8B5CF6 100%);
        border-radius: 22px;
        padding: 1.3rem 1.2rem 2rem;
        box-shadow: 0 12px 28px rgba(76, 29, 149, 0.28);
    }

    div[data-testid="stColumn"]:has(.panel-marker-left) *,
    div[data-testid="stColumn"]:has(.panel-marker-right) * {
        color: #F5F3FF !important;
    }

    div[data-testid="stColumn"]:has(.panel-marker-left) .section-label,
    div[data-testid="stColumn"]:has(.panel-marker-right) .section-label {
        color: #DDD6FE !important;
    }

    /* Auswahlfenster (Select/Input) bekommen ein leichtes Lila statt Weiß,
       damit sie sich vom kräftigen Panel abheben und lesbar bleiben */
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-baseweb="select"] > div,
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-baseweb="select"] > div,
    div[data-testid="stColumn"]:has(.panel-marker-left) input,
    div[data-testid="stColumn"]:has(.panel-marker-right) input,
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stNumberInputContainer"],
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stNumberInputContainer"] {
        background-color: #EDE9FE !important;
        border-radius: 8px;
    }

    /* st.expander ("Strecke/Flaschen/Feedzonen einstellen") ist von Haus aus
       transparent und ließ das kräftige Panel-Lila durchscheinen – dadurch
       wirkte der Text darin wie im Hintergrund statt auf einer eigenen Fläche */
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stExpander"],
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stExpander"] {
        background-color: #EDE9FE !important;
        border-radius: 12px !important;
        border: none !important;
    }

    /* Auf Streamlits eigenen (hellen) Widget-Flächen bleibt der Text dunkel */
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-baseweb="select"] *,
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-baseweb="select"] *,
    div[data-testid="stColumn"]:has(.panel-marker-left) input,
    div[data-testid="stColumn"]:has(.panel-marker-right) input,
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stNumberInputContainer"] *,
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stNumberInputContainer"] *,
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stDataFrame"] *,
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stDataFrame"] *,
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stExpander"] *,
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stExpander"] *,
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stAlert"] *,
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stAlert"] *,
    div[data-testid="stColumn"]:has(.panel-marker-left) button *,
    div[data-testid="stColumn"]:has(.panel-marker-right) button *,
    div[data-testid="stColumn"]:has(.panel-marker-left) button,
    div[data-testid="stColumn"]:has(.panel-marker-right) button {
        color: #3B0764 !important;
    }

    /* Die Dropdown-Liste eines Selectbox wird von Streamlit außerhalb der
       Spalte gerendert (Portal) – deshalb global statt scoped stylen */
    ul[data-testid="stSelectboxVirtualDropdown"] {
        background-color: #F5F3FF !important;
    }
    ul[data-testid="stSelectboxVirtualDropdown"] li {
        background-color: #F5F3FF !important;
        color: #3B0764 !important;
    }
    ul[data-testid="stSelectboxVirtualDropdown"] li:hover,
    ul[data-testid="stSelectboxVirtualDropdown"] li[aria-selected="true"] {
        background-color: #DDD6FE !important;
    }

    div[data-testid="stColumn"]:has(.panel-marker-mid) {
        background: #FFFFFF;
        border-radius: 22px;
        padding: 1.3rem 1.4rem 2rem;
        box-shadow: 0 12px 28px rgba(17, 24, 39, 0.07);
    }

    /* Slider/Radio nutzen primaryColor (=lila) und verschwinden sonst im Panel */
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stSlider"],
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stSlider"],
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stRadio"],
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stRadio"] {
        background: rgba(255, 255, 255, 0.14);
        border-radius: 12px;
        padding: 0.7rem 0.9rem 0.5rem;
        margin-bottom: 0.4rem;
    }

    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stSlider"] [role="slider"],
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stSlider"] [role="slider"] {
        background-color: #FFD600 !important;
        box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.9), 0 2px 6px rgba(0, 0, 0, 0.35) !important;
    }

    /* Warnhinweis (Flüssigkeitszufuhr) leicht gelb hinterlegen */
    div[data-testid="stColumn"]:has(.panel-marker-left) [data-testid="stAlertContainer"],
    div[data-testid="stColumn"]:has(.panel-marker-right) [data-testid="stAlertContainer"] {
        background-color: #FEF9C3 !important;
        border-radius: 10px;
    }
</style>
""",
    unsafe_allow_html=True,
)

if not st.session_state.get("show_streamlit_menu", False):
    st.markdown(
        """
<style>
    header[data-testid="stHeader"] { display: none; }
    div[data-testid="stAppViewContainer"] { padding-top: 0 !important; }
    div[data-testid="stMain"] .block-container { padding-top: 1.5rem !important; }
</style>
""",
        unsafe_allow_html=True,
    )


# ── Session-State initialisieren ─────────────────────────────────────────────


def _init_state() -> None:
    """Setzt Standardwerte für den Session-State beim ersten Aufruf."""
    defaults = {
        "selected_athlete_id": None,
        "route_df": None,
        "route_filename": "",
        "target_time_h": 2.0,
        "carbs_per_hour": 60,
        "num_bottles": 1,
        "bottle_size_0": 750,
        "bottle_content_0": "Wasser",
        "bottle_size_1": 750,
        "bottle_content_1": "Wasser",
        "gel_brand_choice": "Keine Gels",
        "gel_product_choice": "",
        "num_feed_zones": 0,
        "show_add_athlete": False,
        "show_edit_athlete": False,
        "athletes_cache": None,
        "show_streamlit_menu": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────


def _get_athletes() -> list[Athlete]:
    """Gibt die gecachte Athletenliste zurück."""
    if st.session_state.athletes_cache is None:
        st.session_state.athletes_cache = load_athletes()
    return st.session_state.athletes_cache


def _reload_athletes() -> list[Athlete]:
    """Erzwingt ein Neuladen der Athletenliste aus der Datei."""
    st.session_state.athletes_cache = load_athletes()
    return st.session_state.athletes_cache


def _selected_athlete() -> Optional[Athlete]:
    """Gibt den aktuell ausgewählten Athleten zurück oder None."""
    aid = st.session_state.selected_athlete_id
    if not aid:
        return None
    return next((a for a in _get_athletes() if a.id == aid), None)


@st.cache_data(show_spinner="Trainingsdaten werden analysiert…")
def _compute_athlete_stats(athlete_id: str, file_fingerprint: tuple) -> dict:
    """Cache-Schlüssel ist der Athlet plus ein Fingerabdruck seiner Dateien (Pfad+Änderungszeit+Größe)."""
    return aggregate_athlete_data(list_athlete_training_files(athlete_id))


def _get_athlete_stats(athlete: Athlete) -> dict:
    """
    Berechnet FTP, MaxHR und Leistungskurve aus allen Trainingsdateien.

    Das Einlesen (insb. FIT-Dateien) ist teuer – bei Athleten mit vollständiger
    Strava-Historie (hunderte Dateien) kann das mehrere Minuten dauern. Das
    Ergebnis wird deshalb anhand eines Datei-Fingerabdrucks gecacht, damit es
    nicht bei jedem Streamlit-Rerun neu berechnet wird.
    """
    files = list_athlete_training_files(athlete.id)
    fingerprint = tuple((fp, stat.st_mtime, stat.st_size) for fp, stat in ((f, Path(f).stat()) for f in files))
    return _compute_athlete_stats(athlete.id, fingerprint)


def _current_bottles() -> list[Bottle]:
    """Liest die konfigurierten Flaschen (Größe + Hersteller) aus dem Session-State."""
    bottles = []
    for i in range(st.session_state.num_bottles):
        content = st.session_state.get(f"bottle_content_{i}", "Wasser")
        bottles.append(Bottle(
            size_ml=st.session_state.get(f"bottle_size_{i}", 750),
            brand="" if content == "Wasser" else content,
        ))
    return bottles


def _current_gel_brand() -> str:
    """Liest den gewählten Gel-Hersteller aus dem Session-State ("" = keine Gels)."""
    choice = st.session_state.get("gel_brand_choice", "Keine Gels")
    return "" if choice == "Keine Gels" else choice


def _current_gel_product_name() -> str:
    """Liest die gewählte Gel-Produktlinie aus dem Session-State."""
    return st.session_state.get("gel_product_choice", "")


def _current_feed_zone_times_h(route_df: Optional[pd.DataFrame]) -> list[float]:
    """
    Wandelt die konfigurierten Feedzonen-Positionen (km) in Renndauer (h) um.

    Wird u.a. für die Mindesthydrierungs-Prüfung gebraucht: an jeder Feedzone
    gelten die Flaschen als aufgefüllt, relevant ist deshalb der längste
    Abschnitt zwischen zwei Feedzonen (bzw. Start/Ziel), nicht die Zielzeit.
    """
    num_zones = st.session_state.get("num_feed_zones", 0)
    if not num_zones or route_df is None or route_df.empty:
        return []
    total_km = calculate_route_metrics(route_df)["total_distance_km"]
    route_with_time = estimate_time_at_points(route_df, st.session_state.target_time_h)
    return [
        time_at_distance(route_with_time, float(min(st.session_state.get(f"feedzone_km_{i}", 0.0), total_km)))
        for i in range(num_zones)
    ]


def _build_nutrition_plan(route_df: Optional[pd.DataFrame] = None) -> tuple[list, list]:
    """
    Berechnet den Verpflegungsplan und ordnet ihn der Strecke zu.

    Gibt (nutrition_events, nutrition_points) zurück.
    """
    catalog = load_products()
    selected_products = build_selected_products(
        catalog, _current_bottles(), _current_gel_brand(), _current_gel_product_name()
    )
    events = calculate_nutrition_plan(
        target_time_h=st.session_state.target_time_h,
        carbs_per_hour=st.session_state.carbs_per_hour,
        products=selected_products,
    )
    points: list[dict] = []
    if route_df is not None and not route_df.empty:
        route_with_time = estimate_time_at_points(route_df, st.session_state.target_time_h)
        points = suggest_nutrition_points(route_with_time, events)
    return events, points


def _pdf_safe(text: str) -> str:
    """
    Ersetzt Sonderzeichen, die von der FPDF-Kernschrift nicht unterstützt werden.

    Athletennamen oder Produktbezeichnungen können Zeichen wie Gedankenstriche
    oder typografische Anführungszeichen enthalten, an denen fpdf2 sonst mit
    FPDFUnicodeEncodingException abbricht.
    """
    replacements = {"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "..."}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


@st.cache_data(show_spinner="PDF wird erstellt…")
def _export_pdf(
    athlete: Optional[Athlete],
    route_df: Optional[pd.DataFrame],
    nutrition_points: list[dict],
    target_time_h: float,
    carbs_per_hour: int,
) -> bytes:
    """
    Erstellt eine PDF-Übersicht des Rennplans.

    Enthält Athleteninfo, Streckenmetriken und die Verpflegungstabelle. Das
    vertikale Höhenprofil wird über Kaleido gerendert, was spürbar länger
    dauert als reiner Text – deshalb ist diese Funktion gecacht, damit sie
    nicht bei jedem Streamlit-Rerun neu läuft, sondern nur wenn sich Athlet,
    Strecke, Verpflegungsplan, Zielzeit oder Kohlenhydratrate ändern.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "Race Manager - Rennplan", ln=True)
    pdf.set_draw_color(124, 58, 237)
    pdf.set_line_width(0.8)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    content_start_y = pdf.get_y()
    photo_bottom_y = content_start_y

    photo_bytes = decode_photo(athlete.photo_b64) if athlete else None
    if photo_bytes:
        from PIL import Image

        img = Image.open(io.BytesIO(photo_bytes))
        photo_w = 55.0
        photo_h = photo_w * img.height / img.width
        photo_x = pdf.w - pdf.r_margin - photo_w
        pdf.image(io.BytesIO(photo_bytes), x=photo_x, y=content_start_y, w=photo_w, h=photo_h)
        photo_bottom_y = content_start_y + photo_h
    pdf.set_y(content_start_y)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Athlet", ln=True)
    pdf.set_font("Helvetica", size=11)
    if athlete:
        stats = _get_athlete_stats(athlete)
        pdf.cell(0, 6, f"Name: {_pdf_safe(athlete.name)}", ln=True)
        pdf.cell(0, 6, f"Jahrgang: {athlete.birth_year}  |  Alter: {athlete.age}", ln=True)
        if stats.get("ftp"):
            pdf.cell(0, 6, f"FTP: {stats['ftp']:.0f} W", ln=True)
        if stats.get("max_hr"):
            pdf.cell(0, 6, f"Max HF: {stats['max_hr']} bpm", ln=True)
    else:
        pdf.cell(0, 6, "Kein Athlet ausgewählt", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Strecke", ln=True)
    pdf.set_font("Helvetica", size=11)
    if route_df is not None and not route_df.empty:
        m = calculate_route_metrics(route_df)
        pdf.cell(0, 6, f"Distanz: {m['total_distance_km']:.1f} km", ln=True)
        pdf.cell(0, 6, f"Höhenmeter (bergauf): {m['elevation_gain_m']:.0f} m", ln=True)
        pdf.cell(0, 6, f"Höhenmeter (bergab): {m['elevation_loss_m']:.0f} m", ln=True)
        pdf.cell(0, 6, f"Höchster Punkt: {m['max_elevation_m']:.0f} m", ln=True)
    else:
        pdf.cell(0, 6, "Keine Streckendaten vorhanden", ln=True)
    pdf.ln(2)
    pdf.cell(
        0,
        6,
        f"Zielzeit: {int(target_time_h)}h {int((target_time_h % 1) * 60):02d}min",
        ln=True,
    )
    pdf.cell(0, 6, f"Kohlenhydrate/Stunde: {carbs_per_hour} g", ln=True)
    pdf.ln(4)

    pdf.set_y(max(pdf.get_y(), photo_bottom_y + 4))

    if nutrition_points:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Verpflegungsplan", ln=True)
        pdf.set_font("Helvetica", "B", 10)
        col_w = [22, 80, 28, 40]
        headers = ["Zeit", "Produkt", "KH (g)", "KH gesamt (g)"]
        for h, w in zip(headers, col_w):
            pdf.cell(w, 7, h, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", size=10)
        for p in nutrition_points:
            total_min = int(p["time_min"])
            hh, mm = divmod(total_min, 60)
            pdf.cell(col_w[0], 6, f"{hh:02d}:{mm:02d}", border=1)
            pdf.cell(col_w[1], 6, _pdf_safe(p["product_name"])[:38], border=1)
            pdf.cell(col_w[2], 6, str(int(p["carbs_g"])), border=1)
            pdf.cell(col_w[3], 6, str(int(p["cumulative_carbs_g"])), border=1)
            pdf.ln()

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, "Erstellt mit Race Manager", ln=True)
    pdf.set_text_color(0, 0, 0)

    if route_df is not None and not route_df.empty:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Hoehenprofil (Start unten, Ziel oben)", ln=True)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 5, "Ausschneiden und aufs Oberrohr kleben", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        fig_vertical = create_elevation_profile_vertical(route_df, nutrition_points)
        png_bytes = fig_vertical.to_image(format="png")

        img_w_mm = 80.0
        img_h_mm = img_w_mm * fig_vertical.layout.height / fig_vertical.layout.width
        max_h_mm = pdf.h - pdf.get_y() - pdf.b_margin
        if img_h_mm > max_h_mm:
            img_h_mm = max_h_mm
            img_w_mm = img_h_mm * fig_vertical.layout.width / fig_vertical.layout.height
        x_pos = (pdf.w - img_w_mm) / 2
        pdf.image(io.BytesIO(png_bytes), x=x_pos, y=pdf.get_y(), w=img_w_mm, h=img_h_mm)

    return pdf.output()


# ── Dialoge ──────────────────────────────────────────────────────────────────


@st.dialog("Neuen Athleten anlegen")
def _dialog_add_athlete() -> None:
    """Zeigt ein Formular zum Anlegen eines neuen Athleten an."""
    with st.form("form_add_athlete"):
        name = st.text_input("Name *")
        birth_year = st.number_input("Geburtsjahr *", min_value=1940, max_value=2010, value=1995)
        weight_kg = st.number_input("Gewicht (kg)", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
        default_carbs = st.number_input(
            "Standard Kohlenhydrate/Stunde (g)", min_value=0, max_value=200, value=100, step=5
        )
        photo = st.file_uploader("Foto (optional)", type=["jpg", "jpeg", "png"])
        submitted = st.form_submit_button("Anlegen", type="primary")

    if submitted:
        if not name.strip():
            st.error("Name darf nicht leer sein.")
            return
        photo_bytes = photo.read() if photo else None
        athlete = create_athlete(name.strip(), int(birth_year), photo_bytes, weight_kg or None, int(default_carbs))
        _reload_athletes()
        st.session_state.selected_athlete_id = athlete.id
        st.success(f"Athlet '{athlete.name}' wurde angelegt.")
        st.rerun()


@st.dialog("Athleten bearbeiten")
def _dialog_edit_athlete(athlete: Athlete) -> None:
    """Zeigt ein Formular zum Bearbeiten eines bestehenden Athleten an."""
    with st.form("form_edit_athlete"):
        name = st.text_input("Name", value=athlete.name)
        birth_year = st.number_input("Geburtsjahr", min_value=1940, max_value=2010, value=athlete.birth_year)
        weight_kg = st.number_input(
            "Gewicht (kg)", min_value=0.0, max_value=200.0, value=athlete.weight_kg or 0.0, step=0.5
        )
        default_carbs = st.number_input(
            "Standard Kohlenhydrate/Stunde (g)", min_value=0, max_value=200,
            value=athlete.default_carbs_per_hour if athlete.default_carbs_per_hour is not None else 100, step=5,
        )
        photo = st.file_uploader("Foto ersetzen (optional)", type=["jpg", "jpeg", "png"])
        submitted = st.form_submit_button("Speichern", type="primary")

    if submitted:
        if not name.strip():
            st.error("Name darf nicht leer sein.")
            return
        athlete.name = name.strip()
        athlete.birth_year = int(birth_year)
        athlete.weight_kg = weight_kg or None
        athlete.default_carbs_per_hour = int(default_carbs)
        if photo:
            import base64

            athlete.photo_b64 = base64.b64encode(normalize_photo_bytes(photo.read())).decode()
        update_athlete(athlete)
        _reload_athletes()
        st.success("Änderungen gespeichert.")
        st.rerun()


# ── Layout ───────────────────────────────────────────────────────────────────

st.markdown('<div class="app-header-bar">Race Manager</div>', unsafe_allow_html=True)

col_left, col_mid, col_right = st.columns([1.15, 2.2, 1.15], gap="medium")

# ── LINKE SPALTE ─────────────────────────────────────────────────────────────
with col_left:
    st.markdown('<div class="panel-marker panel-marker-left"></div>', unsafe_allow_html=True)
    athletes = _get_athletes()

    st.markdown('<div class="section-label">Athlet</div>', unsafe_allow_html=True)
    athlete_names = [a.name for a in athletes]
    selected_idx = (
        next((i for i, a in enumerate(athletes) if a.id == st.session_state.selected_athlete_id), 0) if athletes else 0
    )

    select_col, add_col = st.columns([5, 1])
    with select_col:
        if athletes:
            chosen_name = st.selectbox(
                "Athlet auswählen", athlete_names, index=selected_idx,
                key="athlete_select_name", label_visibility="collapsed",
            )
            chosen = next(a for a in athletes if a.name == chosen_name)
            if chosen.id != st.session_state.selected_athlete_id:
                st.session_state.carbs_per_hour = chosen.default_carbs_per_hour or 100
            st.session_state.selected_athlete_id = chosen.id
        else:
            st.info("Noch kein Athlet vorhanden.")
    with add_col:
        if st.button("＋", help="Neuen Athleten anlegen", use_container_width=True):
            _dialog_add_athlete()

    st.markdown('<div class="section-label">Strecke</div>', unsafe_allow_html=True)

    with st.expander("Strecke einstellen"):
        saved_routes = list_saved_routes()
        if saved_routes:
            select_col, del_col = st.columns([5, 1])
            with select_col:
                current_name = st.session_state.route_filename
                route_idx = saved_routes.index(current_name) if current_name in saved_routes else 0
                chosen_route = st.selectbox(
                    "Gespeicherte Strecke wählen",
                    saved_routes,
                    index=route_idx,
                    label_visibility="collapsed",
                )
                if chosen_route != st.session_state.route_filename:
                    try:
                        df = load_saved_route(chosen_route)
                        st.session_state.route_df = df
                        st.session_state.route_filename = chosen_route

                        athlete = _selected_athlete()
                        ftp = _get_athlete_stats(athlete)["ftp"] if athlete else None
                        st.session_state.target_time_h = calculate_target_time(df, ftp)
                    except Exception as e:
                        st.error(f"Fehler beim Laden: {e}")
            with del_col:
                if st.button("🗑️", key="delete_route_btn", help="Strecke löschen", use_container_width=True):
                    delete_route_file(chosen_route)
                    if st.session_state.route_filename == chosen_route:
                        st.session_state.route_df = None
                        st.session_state.route_filename = ""
                    st.success(f"'{chosen_route}' gelöscht.")
                    st.rerun()
        else:
            st.caption("Noch keine gespeicherten Strecken.")

        route_upload_key = f"route_upload_{st.session_state.get('route_upload_seq', 0)}"
        route_file = st.file_uploader(
            "Neue Strecke hochladen (.gpx / .csv)", type=["gpx", "csv"],
            key=route_upload_key, label_visibility="collapsed",
        )
        if route_file is not None:
            if st.button("Hochladen bestätigen", key="confirm_route_upload", use_container_width=True):
                try:
                    content = route_file.read()
                    save_route_file(route_file.name, content)
                    df = load_route(content, route_file.name)
                    st.session_state.route_df = df
                    st.session_state.route_filename = route_file.name

                    athlete = _selected_athlete()
                    ftp = _get_athlete_stats(athlete)["ftp"] if athlete else None
                    suggested = calculate_target_time(df, ftp)
                    st.session_state.target_time_h = suggested
                    st.session_state.route_upload_seq = st.session_state.get("route_upload_seq", 0) + 1
                    st.success(
                        f"{route_file.name} gespeichert · Vorschlag: {int(suggested)}h {int((suggested % 1) * 60):02d}min"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Fehler beim Laden: {e}")

        route_df = st.session_state.route_df
        if route_df is not None:
            m = calculate_route_metrics(route_df)
            st.caption(f"📍 {m['total_distance_km']} km · ⬆ {m['elevation_gain_m']:.0f}m · ⬇ {m['elevation_loss_m']:.0f}m")

        st.markdown("**Zielzeit anpassen**")
        st.session_state.target_time_h = st.slider(
            "Zielzeit (h)",
            min_value=0.5,
            max_value=12.0,
            value=float(st.session_state.target_time_h),
            step=0.25,
            format="%.2f h",
            label_visibility="collapsed",
        )
        th = int(st.session_state.target_time_h)
        tm = int((st.session_state.target_time_h % 1) * 60)
        st.caption(f"Zielzeit: **{th}h {tm:02d}min**")

    route_df = st.session_state.route_df
    if route_df is not None:
        m = calculate_route_metrics(route_df)
        route_summary = (
            f"📍 {st.session_state.route_filename or 'Strecke'} · {m['total_distance_km']} km · "
            f"⬆ {m['elevation_gain_m']:.0f}m · 🎯 {th}h {tm:02d}min"
        )
    else:
        route_summary = "Noch keine Strecke ausgewählt."
    st.caption(route_summary)

    st.markdown('<div class="section-label">Verpflegung</div>', unsafe_allow_html=True)

    nutrition_catalog = load_products()
    drink_brand_options = get_brands_by_type(nutrition_catalog, "drink")
    gel_brand_options = get_brands_by_type(nutrition_catalog, "gel")

    with st.expander("Flaschen & Produkte einstellen"):
        st.markdown("**Zielrate**")
        st.session_state.carbs_per_hour = st.slider(
            "Kohlenhydrate / Stunde (g)",
            min_value=0,
            max_value=200,
            value=st.session_state.carbs_per_hour,
            step=5,
        )

        st.radio(
            "Anzahl Flaschen am Rad", [1, 2],
            index=[1, 2].index(st.session_state.num_bottles),
            key="num_bottles", horizontal=True,
        )
        for i in range(st.session_state.num_bottles):
            st.markdown(f"**Flasche {i + 1}**")
            size_col, content_col = st.columns(2)
            with size_col:
                size_val = st.session_state.get(f"bottle_size_{i}", 750)
                st.selectbox(
                    "Größe", BOTTLE_SIZES_ML,
                    index=BOTTLE_SIZES_ML.index(size_val) if size_val in BOTTLE_SIZES_ML else 1,
                    format_func=lambda ml: f"{ml} ml",
                    key=f"bottle_size_{i}",
                )
            with content_col:
                content_options = ["Wasser"] + drink_brand_options
                content_val = st.session_state.get(f"bottle_content_{i}", "Wasser")
                st.selectbox(
                    "Inhalt", content_options,
                    index=content_options.index(content_val) if content_val in content_options else 0,
                    key=f"bottle_content_{i}",
                )
        st.markdown("**Gels**")
        gel_options = ["Keine Gels"] + gel_brand_options
        gel_val = st.session_state.get("gel_brand_choice", "Keine Gels")
        st.selectbox(
            "Gel-Hersteller", gel_options,
            index=gel_options.index(gel_val) if gel_val in gel_options else 0,
            key="gel_brand_choice",
        )

        chosen_gel_brand = _current_gel_brand()
        if chosen_gel_brand:
            gel_product_options = [
                p.name for p in get_products_by_brand(nutrition_catalog, "gel", chosen_gel_brand)
            ]
            product_val = st.session_state.get("gel_product_choice", "")
            st.selectbox(
                "Produktlinie", gel_product_options,
                index=gel_product_options.index(product_val) if product_val in gel_product_options else 0,
                key="gel_product_choice",
            )
        else:
            st.session_state.gel_product_choice = ""

    bottle_summary = " · ".join(
        f"🚴 F{i + 1}: {b.size_ml}ml {b.brand or 'Wasser'}" for i, b in enumerate(_current_bottles())
    )
    gel_summary = _current_gel_brand() or "keine"
    st.caption(f"{bottle_summary} · 🍮 Gel: {gel_summary} · {st.session_state.carbs_per_hour}g KH/h")

    st.markdown("---")

    athlete = _selected_athlete()
    nutrition_events, nutrition_points = _build_nutrition_plan(route_df)

    hydration_issue = check_hydration_capacity(
        _current_bottles(), st.session_state.target_time_h, _current_feed_zone_times_h(route_df),
    )
    if hydration_issue:
        st.warning(
            f"💧 Deine Flaschen fassen zusammen {hydration_issue['total_ml']:.0f} ml – ohne Nachfüllen reicht das "
            f"für {hydration_issue['longest_segment_h']:.2f}h nur für {hydration_issue['ml_per_hour']:.0f} ml/h, "
            f"empfohlen sind mind. {hydration_issue['min_ml_per_hour']:.0f} ml/h. Größere/mehr Flaschen wählen "
            "oder unten eine (weitere) Feedzone zum Nachfüllen einplanen."
        )

    st.markdown('<div class="section-label">Feedzonen</div>', unsafe_allow_html=True)
    with st.expander("Feedzonen einstellen"):
        minus_col, count_col, plus_col = st.columns([1, 2, 1])
        with minus_col:
            minus_clicked = st.button(
                "−", key="feedzone_minus", use_container_width=True,
                disabled=st.session_state.num_feed_zones <= 0,
            )
        with plus_col:
            plus_clicked = st.button(
                "＋", key="feedzone_plus", use_container_width=True,
                disabled=st.session_state.num_feed_zones >= 5,
            )
        if minus_clicked:
            st.session_state.num_feed_zones -= 1
        if plus_clicked:
            st.session_state.num_feed_zones += 1
        with count_col:
            st.markdown(
                f"<div style='text-align:center; padding-top:8px;'>"
                f"{st.session_state.num_feed_zones} Feedzone(n)</div>",
                unsafe_allow_html=True,
            )

        if st.session_state.num_feed_zones > 0:
            if route_df is None or route_df.empty:
                st.caption("Bitte zuerst eine Strecke auswählen, um Feedzonen zu platzieren.")
            else:
                total_km = calculate_route_metrics(route_df)["total_distance_km"]
                route_with_time_fz = estimate_time_at_points(route_df, st.session_state.target_time_h)

                for i in range(st.session_state.num_feed_zones):
                    zone_key = f"feedzone_km_{i}"
                    if zone_key not in st.session_state:
                        st.session_state[zone_key] = round(
                            total_km * (i + 1) / (st.session_state.num_feed_zones + 1), 1
                        )

                zone_kms = [
                    float(min(st.session_state[f"feedzone_km_{i}"], total_km))
                    for i in range(st.session_state.num_feed_zones)
                ]
                sorted_kms = sorted(zone_kms)
                boundaries_km = sorted_kms[1:] + [total_km]
                boundary_for_km = dict(zip(sorted_kms, boundaries_km))
                bottles_now = _current_bottles()

                st.markdown("---")
                for i in range(st.session_state.num_feed_zones):
                    zone_key = f"feedzone_km_{i}"
                    st.markdown(f"**Feedzone {i + 1}**")
                    st.number_input(
                        "Position (km)",
                        min_value=0.0, max_value=float(total_km),
                        value=zone_kms[i],
                        step=10.0, key=zone_key,
                    )
                    km = float(min(st.session_state[zone_key], total_km))
                    next_km = boundary_for_km.get(km, total_km)
                    start_min = time_at_distance(route_with_time_fz, km) * 60.0
                    end_min = (
                        time_at_distance(route_with_time_fz, next_km) * 60.0
                        if next_km < total_km
                        else st.session_state.target_time_h * 60.0
                    )
                    rec = build_feed_zone_recommendation(nutrition_events, start_min, end_min, bottles_now)
                    bottle_txt = ", ".join(rec["bottles_to_refill"]) or "–"
                    st.caption(f"🍼 Flaschen auffüllen: {bottle_txt}")
                    if rec["gel_counts"]:
                        gel_txt = ", ".join(f"{n}× {name}" for name, n in rec["gel_counts"].items())
                        st.caption(f"🍬 Gele übergeben: {gel_txt}")
                    else:
                        st.caption("🍬 Keine weiteren Gele für diesen Abschnitt geplant.")

    if nutrition_points or (route_df is not None):
        pdf_bytes = _export_pdf(
            athlete, route_df, nutrition_points,
            st.session_state.target_time_h, st.session_state.carbs_per_hour,
        )
        st.download_button(
            label="📄 Save Plan (PDF)",
            data=bytes(pdf_bytes),
            file_name="race_plan.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.checkbox(
        "Streamlit-Menü anzeigen",
        key="show_streamlit_menu",
        help="Blendet die Streamlit-Werkzeugleiste (Rerun, Settings, Deploy, ...) oben ein oder aus.",
    )


# ── MITTLERE SPALTE ───────────────────────────────────────────────────────────
with col_mid:
    st.markdown('<div class="panel-marker panel-marker-mid"></div>', unsafe_allow_html=True)
    route_df = st.session_state.route_df
    if route_df is not None and not route_df.empty:
        route_with_time = estimate_time_at_points(route_df, st.session_state.target_time_h)
        key_features = detect_key_features(route_df)

        fig_map = create_route_map(route_with_time, nutrition_points, key_features)
        st.plotly_chart(fig_map, width="stretch", config={"scrollZoom": True})

        fig_elev = create_elevation_profile(route_df, nutrition_points)
        st.plotly_chart(fig_elev, width="stretch")

        st.markdown('<div class="section-label">Verpflegungsplan</div>', unsafe_allow_html=True)
        df_table = create_nutrition_table(nutrition_points)
        if not df_table.empty:
            table_height = 38 * (len(df_table) + 1) + 40
            st.dataframe(df_table, use_container_width=True, hide_index=True, height=table_height)
        else:
            st.caption("Kein Plan – bitte Strecke und Athlet auswählen.")
    else:
        st.markdown(
            "<div style='text-align:center; color:#9CA3AF; padding: 80px 0;'>"
            "📂 Bitte eine Streckendatei (.gpx oder .csv) hochladen"
            "</div>",
            unsafe_allow_html=True,
        )

        if nutrition_events:
            st.markdown('<div class="section-label">Verpflegungsplan (ohne Strecke)</div>', unsafe_allow_html=True)
            rows = []
            for e in nutrition_events:
                h, m = divmod(int(e.time_min), 60)
                rows.append(
                    {
                        "Time": f"{h:02d}:{m:02d}",
                        "Flasche": f"F{e.product.bottle_index + 1}" if e.product.bottle_index is not None else "–",
                        "Nutrition": e.product.name,
                        "KH (g)": int(e.product.carbs_g),
                        "KH gesamt (g)": int(e.cumulative_carbs_g),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── RECHTE SPALTE ─────────────────────────────────────────────────────────────
with col_right:
    st.markdown('<div class="panel-marker panel-marker-right"></div>', unsafe_allow_html=True)
    athlete = _selected_athlete()

    if athlete:
        photo_bytes = decode_photo(athlete.photo_b64)
        if photo_bytes:
            st.image(photo_bytes, use_container_width=True)
        else:
            st.markdown(
                "<div style='background:#E5E7EB; border-radius:8px; height:140px;"
                "display:flex; align-items:center; justify-content:center;"
                "color:#9CA3AF; font-size:2rem;'>👤</div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"**{athlete.name}**  \n*Jahrgang {athlete.birth_year} · {athlete.age} Jahre*")

        stats = _get_athlete_stats(athlete)
        ftp = stats.get("ftp")
        max_hr = stats.get("max_hr")
        power_curve = stats.get("power_curve", {})

        energy_kj = round(ftp * st.session_state.target_time_h * 3600 / 1000, 0) if ftp else None

        st.markdown('<div class="section-label">Leistungsdaten</div>', unsafe_allow_html=True)
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Max HF", f"{max_hr} bpm" if max_hr else "–")
        wkg = ftp / athlete.weight_kg if ftp and athlete.weight_kg else None
        col_m2.metric(
            "FTP", f"{ftp:.0f} W" if ftp else "–",
            delta=f"{wkg:.2f} W/kg" if wkg else None, delta_color="off",
        )
        if energy_kj:
            st.metric("Energie (Zielzeit)", f"{energy_kj:.0f} kJ")

        st.markdown('<div class="section-label">Leistungskurve</div>', unsafe_allow_html=True)
        fig_pc = create_power_curve(power_curve, ftp)
        st.plotly_chart(fig_pc, width="stretch")

        st.markdown("---")
        st.markdown('<div class="section-label">Trainingsdaten</div>', unsafe_allow_html=True)
        upload_key = f"training_upload_{st.session_state.get('training_upload_seq', 0)}"
        training_files_up = st.file_uploader(
            "Trainingsdateien hinzufügen (.csv / .fit / .gpx / .gz)",
            type=["csv", "fit", "gpx", "gz"],
            key=upload_key,
            label_visibility="collapsed",
            accept_multiple_files=True,
        )
        if training_files_up:
            if st.button("Hochladen bestätigen", key="confirm_training_upload", use_container_width=True):
                saved, errors = [], []
                for training_file in training_files_up:
                    try:
                        add_training_file(athlete.id, training_file.name, training_file.read())
                        saved.append(training_file.name)
                    except Exception as e:
                        errors.append(f"{training_file.name}: {e}")
                _reload_athletes()
                # Uploader-Key wechseln, damit die Auswahl danach geleert wird
                # (verhindert, dass dieselben Dateien bei jedem weiteren Rerun erneut hochgeladen werden).
                st.session_state.training_upload_seq = st.session_state.get("training_upload_seq", 0) + 1
                if saved:
                    st.success(f"{len(saved)} Datei(en) gespeichert.")
                for err in errors:
                    st.error(f"Fehler: {err}")
                st.rerun()

        unassigned = list_unassigned_training_files()
        if unassigned:
            st.caption("Bereits abgelegte, noch nicht zugeordnete Dateien:")
            to_assign = st.multiselect(
                "Dateien zuweisen", unassigned, key="unassigned_files", label_visibility="collapsed"
            )
            if to_assign and st.button(f"→ {athlete.name} zuordnen", use_container_width=True):
                for fn in to_assign:
                    assign_training_file(athlete.id, fn)
                _reload_athletes()
                st.success(f"{len(to_assign)} Datei(en) zugeordnet.")
                st.rerun()

        existing_files = [Path(fp).name for fp in list_athlete_training_files(athlete.id)]
        if existing_files:
            with st.expander(f"Dateien verwalten ({len(existing_files)})"):
                for fname in existing_files:
                    col_name, col_ren, col_del = st.columns([5, 1, 1])
                    with col_name:
                        new_name = st.text_input(
                            fname, value=fname,
                            key=f"rename_{athlete.id}_{fname}",
                            label_visibility="collapsed",
                        )
                    with col_ren:
                        if st.button("✓", key=f"renbtn_{athlete.id}_{fname}",
                                      help="Umbenennen", use_container_width=True):
                            try:
                                rename_training_file(athlete.id, fname, new_name)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fehler: {e}")
                    with col_del:
                        if st.button("🗑️", key=f"delbtn_{athlete.id}_{fname}",
                                      help="Löschen", use_container_width=True):
                            delete_training_file(athlete.id, fname)
                            st.rerun()

        st.markdown("---")
        edit_col, del_col = st.columns(2)
        with edit_col:
            if st.button("✏️ Bearbeiten", use_container_width=True):
                _dialog_edit_athlete(athlete)
        with del_col:
            if st.button("🗑️ Löschen", use_container_width=True, type="secondary"):
                delete_athlete(athlete.id)
                st.session_state.selected_athlete_id = None
                _reload_athletes()
                st.rerun()
    else:
        st.markdown(
            "<div style='text-align:center; color:#9CA3AF; padding: 60px 0;'>"
            "👤 Bitte einen Athleten auswählen oder neu anlegen"
            "</div>",
            unsafe_allow_html=True,
        )
