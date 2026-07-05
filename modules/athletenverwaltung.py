"""Athletenverwaltung: Anlegen, Bearbeiten, Löschen und Auswählen von Athleten."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

DATA_DIR = Path("data")
ATHLETES_FILE = DATA_DIR / "athletes.json"


@dataclass
class Athlete:
    """Enthält alle Stammdaten eines Athleten."""

    name: str
    birth_year: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    photo_b64: Optional[str] = None
    training_files: list[str] = field(default_factory=list)

    @property
    def age(self) -> int:
        """Berechnet das aktuelle Alter des Athleten."""
        return date.today().year - self.birth_year


def _ensure_dirs() -> None:
    """Erstellt benötigte Datenverzeichnisse falls nicht vorhanden."""
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "trainings").mkdir(exist_ok=True)
    (DATA_DIR / "routes").mkdir(exist_ok=True)


def load_athletes() -> list[Athlete]:
    """Lädt alle Athleten aus der persistenten Speicherdatei."""
    _ensure_dirs()
    if not ATHLETES_FILE.exists():
        return []
    with open(ATHLETES_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    athletes = []
    for a in raw.get("athletes", []):
        try:
            athletes.append(Athlete(**a))
        except TypeError:
            pass
    return athletes


def _save_athletes(athletes: list[Athlete]) -> None:
    """Schreibt die Athletenliste in die Speicherdatei."""
    _ensure_dirs()
    with open(ATHLETES_FILE, "w", encoding="utf-8") as f:
        json.dump({"athletes": [asdict(a) for a in athletes]}, f, indent=2, ensure_ascii=False)


def create_athlete(name: str, birth_year: int, photo_bytes: Optional[bytes] = None) -> Athlete:
    """Legt einen neuen Athleten an und persistiert ihn."""
    photo_b64 = base64.b64encode(photo_bytes).decode("utf-8") if photo_bytes else None
    athlete = Athlete(name=name, birth_year=birth_year, photo_b64=photo_b64)
    athletes = load_athletes()
    athletes.append(athlete)
    _save_athletes(athletes)
    return athlete


def update_athlete(updated: Athlete) -> None:
    """Überschreibt die Daten eines bestehenden Athleten."""
    athletes = [updated if a.id == updated.id else a for a in load_athletes()]
    _save_athletes(athletes)


def delete_athlete(athlete_id: str) -> None:
    """Entfernt einen Athleten dauerhaft aus dem System."""
    _save_athletes([a for a in load_athletes() if a.id != athlete_id])


def add_training_file(athlete_id: str, filename: str, content: bytes) -> str:
    """Speichert eine Trainingsdatei und verknüpft sie mit dem Athleten."""
    training_dir = DATA_DIR / "trainings" / athlete_id
    training_dir.mkdir(parents=True, exist_ok=True)
    path = training_dir / filename
    path.write_bytes(content)

    athletes = load_athletes()
    for a in athletes:
        if a.id == athlete_id and str(path) not in a.training_files:
            a.training_files.append(str(path))
    _save_athletes(athletes)
    return str(path)


def list_athlete_training_files(athlete_id: str) -> list[str]:
    """
    Gibt alle Trainingsdateien eines Athleten zurück, direkt vom Dateisystem gelesen.

    Liest den Athleten-Ordner statt der gespeicherten training_files-Liste, damit
    auch manuell hineinkopierte Dateien (z.B. entpackte Strava-Bulk-Exports)
    erkannt werden, ohne über die App hochgeladen worden zu sein.
    """
    training_dir = DATA_DIR / "trainings" / athlete_id
    if not training_dir.exists():
        return []
    return sorted(
        str(p) for p in training_dir.iterdir()
        if p.is_file() and (p.suffix.lower() in (".csv", ".fit") or p.name.lower().endswith(".gz"))
    )


def list_unassigned_training_files() -> list[str]:
    """
    Gibt Trainingsdateien zurück, die direkt in data/trainings/ liegen statt
    in einem Athleten-Unterordner (z.B. manuell entpackte Strava-Exports).
    """
    _ensure_dirs()
    training_root = DATA_DIR / "trainings"
    return sorted(
        p.name for p in training_root.iterdir()
        if p.is_file() and p.suffix.lower() in (".csv", ".fit", ".gz")
    )


def assign_training_file(athlete_id: str, filename: str) -> str:
    """
    Ordnet eine bereits in data/trainings/ liegende Datei einem Athleten zu.

    Verschiebt die Datei in den Athleten-Unterordner und verknüpft sie.
    """
    src = DATA_DIR / "trainings" / filename
    training_dir = DATA_DIR / "trainings" / athlete_id
    training_dir.mkdir(parents=True, exist_ok=True)
    dest = training_dir / filename
    src.replace(dest)

    athletes = load_athletes()
    for a in athletes:
        if a.id == athlete_id and str(dest) not in a.training_files:
            a.training_files.append(str(dest))
    _save_athletes(athletes)
    return str(dest)


def get_athlete_by_id(athlete_id: str) -> Optional[Athlete]:
    """Gibt einen Athleten anhand seiner ID zurück oder None falls nicht gefunden."""
    return next((a for a in load_athletes() if a.id == athlete_id), None)


def decode_photo(photo_b64: Optional[str]) -> Optional[bytes]:
    """Dekodiert ein Base64-kodiertes Foto zurück in Bytes."""
    if not photo_b64:
        return None
    try:
        return base64.b64decode(photo_b64)
    except Exception:
        return None
