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
    list_athlete_training_files,
    list_unassigned_training_files,
    load_athletes,
    update_athlete,
)
from modules.ernaehrungsdaten import (
    calculate_nutrition_plan,
    load_products,
)
from modules.streckenanalys import (
    calculate_route_metrics,
    calculate_target_time,
    detect_key_features,
    estimate_time_at_points,
    list_saved_routes,
    load_route,
    load_saved_route,
    save_route_file,
    suggest_nutrition_points,
)
from modules.trainingsanalys import aggregate_athlete_data
from modules.visualisierungen import (
    create_elevation_profile,
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
    h1 { font-size: 1.6rem !important; margin-bottom: 0 !important; }
    .section-label { font-size: 0.75rem; color: #6B7280; text-transform: uppercase;
                     letter-spacing: 0.05em; margin-top: 12px; margin-bottom: 4px; }
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
        "nutrition_type": "gel+drink",
        "show_add_athlete": False,
        "show_edit_athlete": False,
        "athletes_cache": None,
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


def _build_nutrition_plan(route_df: Optional[pd.DataFrame] = None) -> tuple[list, list]:
    """
    Berechnet den Verpflegungsplan und ordnet ihn der Strecke zu.

    Gibt (nutrition_events, nutrition_points) zurück.
    """
    products = load_products()
    events = calculate_nutrition_plan(
        target_time_h=st.session_state.target_time_h,
        carbs_per_hour=st.session_state.carbs_per_hour,
        products=products,
        nutrition_type=st.session_state.nutrition_type,
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


def _export_pdf(athlete: Optional[Athlete], route_df: Optional[pd.DataFrame], nutrition_points: list[dict]) -> bytes:
    """
    Erstellt eine PDF-Übersicht des Rennplans.

    Enthält Athleteninfo, Streckenmetriken und die Verpflegungstabelle.
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
        f"Zielzeit: {int(st.session_state.target_time_h)}h {int((st.session_state.target_time_h % 1) * 60):02d}min",
        ln=True,
    )
    pdf.cell(0, 6, f"Kohlenhydrate/Stunde: {st.session_state.carbs_per_hour} g", ln=True)
    pdf.ln(4)

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

    return pdf.output()


# ── Dialoge ──────────────────────────────────────────────────────────────────


@st.dialog("Neuen Athleten anlegen")
def _dialog_add_athlete() -> None:
    """Zeigt ein Formular zum Anlegen eines neuen Athleten an."""
    with st.form("form_add_athlete"):
        name = st.text_input("Name *")
        birth_year = st.number_input("Geburtsjahr *", min_value=1940, max_value=2010, value=1995)
        photo = st.file_uploader("Foto (optional)", type=["jpg", "jpeg", "png"])
        submitted = st.form_submit_button("Anlegen", type="primary")

    if submitted:
        if not name.strip():
            st.error("Name darf nicht leer sein.")
            return
        photo_bytes = photo.read() if photo else None
        athlete = create_athlete(name.strip(), int(birth_year), photo_bytes)
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
        photo = st.file_uploader("Foto ersetzen (optional)", type=["jpg", "jpeg", "png"])
        submitted = st.form_submit_button("Speichern", type="primary")

    if submitted:
        if not name.strip():
            st.error("Name darf nicht leer sein.")
            return
        athlete.name = name.strip()
        athlete.birth_year = int(birth_year)
        if photo:
            athlete.photo_b64 = None
            import base64

            athlete.photo_b64 = base64.b64encode(photo.read()).decode()
        update_athlete(athlete)
        _reload_athletes()
        st.success("Änderungen gespeichert.")
        st.rerun()


# ── Layout ───────────────────────────────────────────────────────────────────

st.title("🚵 Race Manager")

col_left, col_mid, col_right = st.columns([1.15, 2.2, 1.15], gap="medium")

# ── LINKE SPALTE ─────────────────────────────────────────────────────────────
with col_left:
    athletes = _get_athletes()

    st.markdown('<div class="section-label">Athlet</div>', unsafe_allow_html=True)
    athlete_names = [a.name for a in athletes]
    selected_idx = (
        next((i for i, a in enumerate(athletes) if a.id == st.session_state.selected_athlete_id), 0) if athletes else 0
    )

    if athletes:
        chosen_name = st.selectbox("Athlet auswählen", athlete_names, index=selected_idx, label_visibility="collapsed")
        chosen = next(a for a in athletes if a.name == chosen_name)
        st.session_state.selected_athlete_id = chosen.id
    else:
        st.info("Noch kein Athlet vorhanden.")

    st.markdown('<div class="section-label">Verpflegung</div>', unsafe_allow_html=True)
    nt_map = {"Gel + Drink": "gel+drink", "Nur Gel": "gel", "Nur Drink": "drink", "Alle": "alle"}
    nt_label = st.selectbox("Typ", list(nt_map.keys()), label_visibility="collapsed")
    st.session_state.nutrition_type = nt_map[nt_label]

    st.session_state.carbs_per_hour = st.slider(
        "Kohlenhydrate / Stunde (g)",
        min_value=30,
        max_value=120,
        value=st.session_state.carbs_per_hour,
        step=5,
    )

    st.markdown('<div class="section-label">Strecke</div>', unsafe_allow_html=True)

    saved_routes = list_saved_routes()
    if saved_routes:
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
    else:
        st.caption("Noch keine gespeicherten Strecken.")

    route_file = st.file_uploader(
        "Neue Strecke hochladen (.gpx / .csv)", type=["gpx", "csv"], label_visibility="collapsed"
    )
    if route_file is not None and route_file.name != st.session_state.get("_last_uploaded_route"):
        try:
            content = route_file.read()
            save_route_file(route_file.name, content)
            df = load_route(content, route_file.name)
            st.session_state.route_df = df
            st.session_state.route_filename = route_file.name
            st.session_state._last_uploaded_route = route_file.name

            athlete = _selected_athlete()
            ftp = _get_athlete_stats(athlete)["ftp"] if athlete else None
            suggested = calculate_target_time(df, ftp)
            st.session_state.target_time_h = suggested
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

    st.markdown('<div class="section-label">Zielzeit anpassen</div>', unsafe_allow_html=True)
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

    st.markdown("---")

    athlete = _selected_athlete()
    nutrition_events, nutrition_points = _build_nutrition_plan(route_df)

    if nutrition_points or (route_df is not None):
        pdf_bytes = _export_pdf(athlete, route_df, nutrition_points)
        st.download_button(
            label="📄 Save Plan (PDF)",
            data=bytes(pdf_bytes),
            file_name="race_plan.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ── MITTLERE SPALTE ───────────────────────────────────────────────────────────
with col_mid:
    athletes = _get_athletes()

    head_col, add_col = st.columns([5, 1])
    with head_col:
        st.markdown('<div class="section-label">Athleten</div>', unsafe_allow_html=True)
    with add_col:
        if st.button("＋", help="Neuen Athleten anlegen", use_container_width=True):
            _dialog_add_athlete()

    if athletes:
        btn_cols = st.columns(min(len(athletes), 4))
        for i, a in enumerate(athletes):
            with btn_cols[i % len(btn_cols)]:
                is_sel = a.id == st.session_state.selected_athlete_id
                label = f"**{a.name}**" if is_sel else a.name
                if st.button(
                    label, key=f"sel_{a.id}", use_container_width=True, type="primary" if is_sel else "secondary"
                ):
                    st.session_state.selected_athlete_id = a.id
                    st.rerun()
    else:
        st.caption("Noch keine Athleten. Klicke ＋ um einen anzulegen.")

    st.markdown("---")

    route_df = st.session_state.route_df
    if route_df is not None and not route_df.empty:
        route_with_time = estimate_time_at_points(route_df, st.session_state.target_time_h)
        key_features = detect_key_features(route_df)

        fig_map = create_route_map(route_with_time, nutrition_points, key_features)
        st.plotly_chart(fig_map, width="stretch", config={"scrollZoom": True})

        chart_col, table_col = st.columns([1.2, 1])
        with chart_col:
            fig_elev = create_elevation_profile(route_df, nutrition_points)
            st.plotly_chart(fig_elev, width="stretch")
        with table_col:
            st.markdown('<div class="section-label">Verpflegungsplan</div>', unsafe_allow_html=True)
            df_table = create_nutrition_table(nutrition_points)
            if not df_table.empty:
                st.dataframe(df_table, use_container_width=True, hide_index=True, height=230)
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
                        "Nutrition": e.product.name,
                        "KH (g)": int(e.product.carbs_g),
                        "KH gesamt (g)": int(e.cumulative_carbs_g),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── RECHTE SPALTE ─────────────────────────────────────────────────────────────
with col_right:
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
        col_m2.metric("FTP", f"{ftp:.0f} W" if ftp else "–")
        if energy_kj:
            st.metric("Energie (Zielzeit)", f"{energy_kj:.0f} kJ")

        st.markdown('<div class="section-label">Leistungskurve</div>', unsafe_allow_html=True)
        fig_pc = create_power_curve(power_curve, ftp)
        st.plotly_chart(fig_pc, width="stretch")

        st.markdown("---")
        st.markdown('<div class="section-label">Trainingsdaten</div>', unsafe_allow_html=True)
        training_file = st.file_uploader(
            "Trainingsdatei hinzufügen (.csv / .fit / .fit.gz)",
            type=["csv", "fit", "gz"],
            key="training_upload",
            label_visibility="collapsed",
        )
        if training_file is not None:
            try:
                add_training_file(athlete.id, training_file.name, training_file.read())
                _reload_athletes()
                st.success(f"'{training_file.name}' gespeichert.")
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {e}")

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

        existing = [Path(fp).name for fp in list_athlete_training_files(athlete.id)]
        if existing:
            st.caption(f"Dateien: {', '.join(existing)}")

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
