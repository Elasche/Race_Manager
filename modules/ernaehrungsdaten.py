"""Ernährungsdaten: Produktverwaltung und Berechnung der Verpflegungsstrategie."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PRODUCTS_FILE = Path("data") / "nutrition_products.json"


BOTTLE_SIZES_ML = [500, 750, 950]


@dataclass
class NutritionProduct:
    """Repräsentiert ein Ernährungsprodukt mit seinen Nährstoffangaben."""

    name: str
    type: str  # 'gel' | 'drink' | 'food'
    carbs_g: float
    caffeine_mg: float = 0.0
    notes: str = ""
    brand: str = ""
    volume_ml: Optional[float] = None  # Referenz-Flaschengröße für carbs_g (nur bei 'drink')
    bottle_index: Optional[int] = None  # gesetzt für Drink-Produkte, die einer Flasche zugeordnet sind

    def __post_init__(self) -> None:
        if not self.brand:
            self.brand = self.name.split()[0]
        if self.type == "drink" and self.volume_ml is None:
            self.volume_ml = 500.0


@dataclass
class Bottle:
    """Konfiguration einer einzelnen Trinkflasche am Rad."""

    size_ml: int = 750
    brand: str = ""  # leer bedeutet: nur Wasser, kein Kohlenhydrat-Produkt


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
              "caffeine_mg": p.caffeine_mg, "notes": p.notes,
              "brand": p.brand, "volume_ml": p.volume_ml} for p in products]
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"products": data}, f, indent=2, ensure_ascii=False)


def _default_products() -> list[NutritionProduct]:
    """Gibt eine Liste von Standard-Produkten zurück."""
    return [
        NutritionProduct("Maurten Gel 100", "gel", 25.0),
        NutritionProduct("SiS Go Isotonic Gel", "gel", 22.0),
        NutritionProduct("MNSTRY Gel", "gel", 40.0),
        NutritionProduct("Maurten Drink Mix 160", "drink", 40.0),
        NutritionProduct("MNSTRY Sports Drink", "drink", 40.0),
        NutritionProduct("Banana", "food", 27.0),
    ]


def get_brands_by_type(products: list[NutritionProduct], nutrition_type: str) -> list[str]:
    """Gibt die verfügbaren Hersteller für einen Produkttyp zurück, alphabetisch sortiert."""
    return sorted({p.brand for p in products if p.type == nutrition_type and p.brand})


def get_products_by_brand(
    products: list[NutritionProduct], nutrition_type: str, brand: str
) -> list[NutritionProduct]:
    """Gibt alle Produkte eines Herstellers für einen Produkttyp zurück."""
    return [p for p in products if p.type == nutrition_type and p.brand == brand]


def scale_product_for_bottle(product: NutritionProduct, bottle_size_ml: int, bottle_index: int) -> NutritionProduct:
    """
    Skaliert ein Drink-Mix-Produkt auf eine abweichende Flaschengröße.

    Die Kohlenhydratangabe eines Produkts bezieht sich auf eine Referenz-
    Flaschengröße (volume_ml, i.d.R. 500ml); bei größeren Flaschen wird
    proportional mehr Pulver angerührt.
    """
    factor = bottle_size_ml / (product.volume_ml or 500.0)
    return NutritionProduct(
        name=f"{product.name} ({bottle_size_ml}ml)",
        type=product.type,
        carbs_g=round(product.carbs_g * factor, 1),
        caffeine_mg=round(product.caffeine_mg * factor, 1),
        notes=product.notes,
        brand=product.brand,
        volume_ml=bottle_size_ml,
        bottle_index=bottle_index,
    )


def build_selected_products(
    products: list[NutritionProduct],
    bottles: list[Bottle],
    gel_brand: str,
    gel_product_name: str = "",
) -> list[NutritionProduct]:
    """
    Baut die tatsächlich zu verwendende Produktliste aus Flaschen-Setup und Gel-Wahl.

    Flaschen mit Drink-Mix werden auf ihre individuelle Größe skaliert und
    behalten ihren bottle_index, damit sie später der richtigen Flasche
    zugeordnet werden können. Flaschen mit "Wasser" (leerer brand) liefern
    keine Kohlenhydrate. Ist `gel_product_name` gesetzt, wird nur diese eine
    Produktlinie des Herstellers verwendet statt aller seiner Gel-Produkte.
    """
    selected: list[NutritionProduct] = []

    if gel_brand:
        gel_products = get_products_by_brand(products, "gel", gel_brand)
        if gel_product_name:
            gel_products = [p for p in gel_products if p.name == gel_product_name] or gel_products
        selected.extend(gel_products)

    for i, bottle in enumerate(bottles):
        if not bottle.brand:
            continue
        for p in get_products_by_brand(products, "drink", bottle.brand):
            selected.append(scale_product_for_bottle(p, bottle.size_ml, bottle_index=i))

    return selected


def check_hydration_capacity(
    bottles: list[Bottle], target_time_h: float, min_ml_per_hour: float = 500.0
) -> Optional[dict]:
    """
    Prüft, ob das mitgeführte Flaschenvolumen für die Zielzeit ausreicht, um im
    Schnitt mindestens `min_ml_per_hour` zu decken (ohne Nachfüllen unterwegs).

    Gibt None zurück, wenn ausreichend, sonst die berechneten Werte für einen
    Warnhinweis.
    """
    if target_time_h <= 0 or not bottles:
        return None
    total_ml = sum(b.size_ml for b in bottles)
    ml_per_hour = total_ml / target_time_h
    if ml_per_hour >= min_ml_per_hour:
        return None
    return {
        "total_ml": total_ml,
        "ml_per_hour": round(ml_per_hour, 0),
        "min_ml_per_hour": min_ml_per_hour,
    }


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
) -> list[NutritionEvent]:
    """
    Berechnet einen Verpflegungsplan für ein Rennen.

    `products` ist die bereits ausgewählte Produktliste (siehe
    build_selected_products) - z.B. der gewählte Gel-Hersteller plus die
    Drink-Mix-Produkte der Flaschen, die keine "Wasser"-Flaschen sind.
    Verteilt diese Produkte so, dass das Kohlenhydratziel (carbs_per_hour)
    möglichst genau erreicht wird. Erste Einnahme nach 20 Minuten,
    letzte Einnahme mindestens 10 Minuten vor dem Ziel.
    """
    if not products or target_time_h <= 0:
        return []

    selected = products
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
        if product.type == "drink" and product.bottle_index is not None:
            label = f"F{product.bottle_index + 1}-Drink{count_of_type}"
        else:
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
