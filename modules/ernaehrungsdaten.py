"""Ernährungsdaten: Produktverwaltung und Berechnung der Verpflegungsstrategie."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PRODUCTS_FILE = Path("data") / "nutrition_products.json"


@dataclass
class NutritionProduct:
    """Repräsentiert ein Ernährungsprodukt mit seinen Nährstoffangaben."""

    name: str
    type: str  # 'gel' | 'drink' | 'food'
    carbs_g: float
    caffeine_mg: float = 0.0
    notes: str = ""


@dataclass
class NutritionEvent:
    """Ein geplanter Verpflegungszeitpunkt während des Rennens."""

    time_min: float
    product: NutritionProduct
    cumulative_carbs_g: float
    label: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


def load_products() -> list[NutritionProduct]:
    """Lädt die verfügbaren Ernährungsprodukte aus der JSON-Datei."""
    if not PRODUCTS_FILE.exists():
        return _default_products()
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    products = []
    for p in data.get("products", []):
        try:
            products.append(NutritionProduct(**p))
        except TypeError:
            pass
    return products if products else _default_products()


def save_products(products: list[NutritionProduct]) -> None:
    """Speichert die Produktliste in der JSON-Datei."""
    PRODUCTS_FILE.parent.mkdir(exist_ok=True)
    data = [{"name": p.name, "type": p.type, "carbs_g": p.carbs_g,
              "caffeine_mg": p.caffeine_mg, "notes": p.notes} for p in products]
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"products": data}, f, indent=2, ensure_ascii=False)


def _default_products() -> list[NutritionProduct]:
    """Gibt eine Liste von Standard-Produkten zurück."""
    return [
        NutritionProduct("Maurten Gel 100", "gel", 25.0),
        NutritionProduct("SiS Go Isotonic Gel", "gel", 22.0),
        NutritionProduct("Maurten Drink Mix 160", "drink", 40.0),
        NutritionProduct("Isostar Hydrate & Perform", "drink", 35.0),
        NutritionProduct("Banana", "food", 27.0),
    ]


def get_products_by_type(products: list[NutritionProduct], nutrition_type: str) -> list[NutritionProduct]:
    """Filtert Produkte nach dem gewählten Ernährungstyp (gel, drink, gel+drink, alle)."""
    if nutrition_type == "gel":
        return [p for p in products if p.type == "gel"] or products
    if nutrition_type == "drink":
        return [p for p in products if p.type == "drink"] or products
    if nutrition_type == "gel+drink":
        filtered = [p for p in products if p.type in ("gel", "drink")]
        return filtered or products
    return products


def calculate_nutrition_interval(carbs_per_hour: int, product: NutritionProduct) -> float:
    """
    Berechnet das Verpflegungsintervall in Minuten für ein gegebenes Produkt.

    Das Intervall ergibt sich aus den Kohlenhydraten pro Stunde geteilt durch
    die Kohlenhydrate pro Portion.
    """
    if carbs_per_hour <= 0 or product.carbs_g <= 0:
        return 30.0
    interval = (product.carbs_g / carbs_per_hour) * 60.0
    return max(15.0, interval)


def calculate_nutrition_plan(
    target_time_h: float,
    carbs_per_hour: int,
    products: list[NutritionProduct],
    nutrition_type: str = "gel+drink",
) -> list[NutritionEvent]:
    """
    Berechnet einen Verpflegungsplan für ein Rennen.

    Verteilt die gewählten Produkte so, dass das Kohlenhydratziel (carbs_per_hour)
    möglichst genau erreicht wird. Erste Einnahme nach 20 Minuten,
    letzte Einnahme mindestens 10 Minuten vor dem Ziel.
    """
    if not products or target_time_h <= 0:
        return []

    selected = get_products_by_type(products, nutrition_type)
    if not selected:
        return []

    avg_carbs = sum(p.carbs_g for p in selected) / len(selected)
    interval_min = max(15.0, (avg_carbs / max(carbs_per_hour, 1)) * 60.0)

    events: list[NutritionEvent] = []
    current_min = 20.0
    end_min = target_time_h * 60.0 - 10.0
    cumulative = 0.0
    idx = 0

    while current_min <= end_min:
        product = selected[idx % len(selected)]
        cumulative += product.carbs_g
        count_of_type = sum(1 for e in events if e.product.type == product.type) + 1
        label = f"{product.type.capitalize()}{count_of_type}"

        events.append(NutritionEvent(
            time_min=round(current_min, 1),
            product=product,
            cumulative_carbs_g=round(cumulative, 1),
            label=label,
        ))
        current_min += interval_min
        idx += 1

    return events
