"""Ernährungsdaten: Produktverwaltung und Berechnung der Verpflegungsstrategie."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

PRODUCTS_FILE = Path("data") / "nutrition_products.json"


BOTTLE_SIZES_ML = [500, 750, 950]
DEFAULT_FLUID_RATE_ML_PER_HOUR = 500.0
NUTRITION_START_DELAY_MIN = 20.0  # keine Verpflegung direkt ab Minute 0 nötig (Anfahrphase)


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
    product_name: str = ""  # leer bedeutet: alle Drink-Produkte der Marke verwenden


@dataclass
class NutritionEvent:
    """Ein geplanter Verpflegungszeitpunkt während des Rennens."""

    time_min: float
    product: NutritionProduct
    cumulative_carbs_g: float
    label: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    is_feed_zone: bool = False  # markiert eine Übergabe an einer Feedzone (für Hervorhebung)


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
    keine Kohlenhydrate, bekommen aber ein Platzhalter-Wasser-Produkt (0g KH),
    damit auch reine Trinkflaschen eine Erinnerung im Plan/auf der Karte
    erzeugen. Ist `gel_product_name` gesetzt, wird nur diese eine
    Produktlinie des Herstellers verwendet statt aller seiner Gel-Produkte.
    """
    selected: list[NutritionProduct] = []

    if gel_brand:
        gel_products = get_products_by_brand(products, "gel", gel_brand)
        if gel_product_name:
            gel_products = [p for p in gel_products if p.name == gel_product_name] or gel_products
        selected.extend(gel_products)

    for i, bottle in enumerate(bottles):
        if bottle.brand:
            drink_products = get_products_by_brand(products, "drink", bottle.brand)
            if bottle.product_name:
                drink_products = [p for p in drink_products if p.name == bottle.product_name] or drink_products
            for p in drink_products:
                selected.append(scale_product_for_bottle(p, bottle.size_ml, bottle_index=i))
        else:
            selected.append(NutritionProduct(
                name="Wasser", type="drink", carbs_g=0.0,
                brand="Wasser", volume_ml=bottle.size_ml, bottle_index=i,
            ))

    return selected


def check_hydration_capacity(
    bottles: list[Bottle],
    target_time_h: float,
    feed_zones: Optional[list[dict]] = None,
    min_ml_per_hour: float = DEFAULT_FLUID_RATE_ML_PER_HOUR,
) -> Optional[dict]:
    """
    Prüft, ob das mitgeführte + an Feedzonen nachgefüllte Flüssigkeitsvolumen
    kumulativ ausreicht, um durchgängig mindestens `min_ml_per_hour` zu decken.

    `feed_zones` ist eine Liste von {"time_min": float, "bottles": list[Bottle]}
    (die an dieser Feedzone tatsächlich übergebenen Flaschen). Geprüft wird an
    jedem Checkpoint (jede Feedzone-Ankunft sowie das Ziel), ob die BIS DAHIN
    insgesamt erhaltene Menge (Startflaschen + alle bisherigen Feedzonen) für
    die bis dahin verstrichene Zeit reicht - nicht wie zuvor ein Reset auf 0
    bei jeder Feedzone. So wird Restvolumen aus einer beim Erreichen der
    Feedzone noch nicht leeren Flasche korrekt mitgezählt, statt fälschlich
    zu verschwinden.

    Gibt None zurück, wenn ausreichend, sonst die Werte für den kritischsten
    Checkpoint für einen Warnhinweis.
    """
    if target_time_h <= 0 or not bottles:
        return None

    zones = sorted((feed_zones or []), key=lambda z: z["time_min"])
    checkpoints_min = [z["time_min"] for z in zones] + [target_time_h * 60.0]
    capacities_ml = [sum(b.size_ml for b in bottles)] + [
        sum(b.size_ml for b in z.get("bottles", [])) for z in zones
    ]

    worst_ml_per_hour = None
    worst_checkpoint_h = 0.0
    worst_capacity_ml = 0.0
    cumulative_ml = 0.0
    for checkpoint_min, capacity_ml in zip(checkpoints_min, capacities_ml):
        cumulative_ml += capacity_ml
        # Wie im Verpflegungsplan startet der tatsächliche Flüssigkeitsbedarf
        # erst nach der Anfahrphase (NUTRITION_START_DELAY_MIN), nicht ab
        # Minute 0 - sonst wäre die Prüfung strenger als der Plan selbst.
        active_min = checkpoint_min - NUTRITION_START_DELAY_MIN
        if active_min <= 0:
            continue
        ml_per_hour = cumulative_ml / (active_min / 60.0)
        if worst_ml_per_hour is None or ml_per_hour < worst_ml_per_hour:
            worst_ml_per_hour = ml_per_hour
            worst_checkpoint_h = checkpoint_min / 60.0
            worst_capacity_ml = cumulative_ml

    if worst_ml_per_hour is None or worst_ml_per_hour >= min_ml_per_hour:
        return None
    return {
        "total_ml": worst_capacity_ml,
        "ml_per_hour": round(worst_ml_per_hour, 0),
        "min_ml_per_hour": min_ml_per_hour,
        "longest_segment_h": round(worst_checkpoint_h, 2),
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
    fluid_rate_ml_per_hour: float = DEFAULT_FLUID_RATE_ML_PER_HOUR,
    feed_zones: Optional[list[dict]] = None,
) -> list[NutritionEvent]:
    """
    Berechnet einen Verpflegungsplan für ein Rennen.

    `products` ist die bereits ausgewählte Produktliste (siehe
    build_selected_products) - z.B. der gewählte Gel-Hersteller plus die
    Drink-Mix-Produkte der Flaschen, die keine "Wasser"-Flaschen sind, plus
    Platzhalter-Wasser-Produkte für reine Trinkflaschen.

    `feed_zones` (optional) ist eine Liste von
    {"time_min": float, "label": str, "bottle_products": list[NutritionProduct], "num_gels": int}
    - die an einer Feedzone tatsächlich übergebenen Flaschen/Gels. Die dort
    übergebenen Flaschen reihen sich chronologisch in den Flaschen-Zeitplan
    ein (frühestens ab dem Feedzone-Zeitpunkt) und erzeugen zusätzlich einen
    gelb hervorgehobenen "Feedzone"-Eintrag im Plan (is_feed_zone=True).

    Flaschen werden nacheinander geleert statt parallel: Flasche 2 wird erst
    ab dem Zeitpunkt aktiv, an dem Flasche 1 bei `fluid_rate_ml_per_hour`
    rechnerisch leer wäre (Flaschenvolumen / Trinkrate) - bzw. ab einer
    Feedzone, falls diese später liegt. Jede Flasche erzeugt genau einen
    Eintrag - zu dem Zeitpunkt, an dem sie rechnerisch leer ist und zur
    nächsten gewechselt werden sollte (nicht mehrere Teil-Portionen).

    Die Kohlenhydrate aus einer aktiven Drink-Mix-Flasche werden bei der
    Gel-Planung berücksichtigt und priorisiert: Gels füllen pro Zeitfenster
    nur die Lücke zwischen der Ziel-KH-Rate (carbs_per_hour) und dem, was die
    gerade aktive Flasche bereits liefert (Flaschen-KH / Flaschen-Dauer).
    Liefert die Flasche bereits genug oder mehr, werden in diesem Zeitfenster
    keine Gels eingeplant. Erste Gel-Einnahme nach 20 Minuten, letzte
    mindestens 10 Minuten vor dem Ziel.
    """
    if not products or target_time_h <= 0:
        return []

    end_min = target_time_h * 60.0 - 10.0
    raw: list[tuple[float, NutritionProduct, str, bool]] = []

    gel_products = [p for p in products if p.type == "gel"]
    bottle_products: dict[int, list[NutritionProduct]] = {}
    for p in products:
        if p.type != "gel" and p.bottle_index is not None:
            bottle_products.setdefault(p.bottle_index, []).append(p)

    # Flaschen-"Stufen" bauen: zuerst die Start-Flaschen, danach je Feedzone
    # (in Zeitreihenfolge) deren übergebene Flaschen - jede Stufe darf
    # frühestens ab ihrem eigenen Mindest-Startzeitpunkt aktiv werden.
    stages: list[tuple[str, list[NutritionProduct], float]] = [
        (f"F{bidx + 1}", bottle_products[bidx], 0.0) for bidx in sorted(bottle_products)
    ]
    for zone in sorted(feed_zones or [], key=lambda z: z["time_min"]):
        zone_bottles: dict[int, list[NutritionProduct]] = {}
        for p in zone.get("bottle_products", []):
            if p.bottle_index is not None:
                zone_bottles.setdefault(p.bottle_index, []).append(p)
        for bidx in sorted(zone_bottles):
            stages.append((f"{zone['label']}-F{bidx + 1}", zone_bottles[bidx], zone["time_min"]))
        num_gels = zone.get("num_gels", 0)
        handover_bits = []
        if zone.get("bottle_products"):
            handover_bits.append(f"{len(zone_bottles)} Flasche(n)")
        if num_gels:
            handover_bits.append(f"{num_gels} Gel(e)")
        handover_product = NutritionProduct(
            name=", ".join(handover_bits) or "Nachfüllen", type="feed_zone", carbs_g=0.0, brand=zone["label"],
        )
        raw.append((round(zone["time_min"], 1), handover_product, zone["label"], True))

    # Flaschen-Zeitplan (sequentiell) aufbauen und dabei je Zeitfenster die
    # KH-Rate merken, die die aktive Flasche liefert - für die Gel-Planung.
    gel_segments: list[tuple[float, float, float]] = []  # (start, end, bottle_carbs_per_hour)
    cursor_min = NUTRITION_START_DELAY_MIN
    for label_prefix, bottle_group, min_start in stages:
        volume_ml = bottle_group[0].volume_ml or 500.0
        duration_min = (volume_ml / fluid_rate_ml_per_hour) * 60.0
        window_start = max(cursor_min, min_start)
        natural_end = window_start + duration_min
        window_end = min(natural_end, end_min)

        if window_start <= end_min:
            carb_items = [p for p in bottle_group if p.carbs_g > 0]
            if carb_items:
                template = carb_items[0]
                total_carbs = sum(p.carbs_g for p in carb_items)
                bottle_product = NutritionProduct(
                    name=template.name if len(carb_items) == 1 else " + ".join(p.name for p in carb_items),
                    type=template.type,
                    carbs_g=total_carbs,
                    caffeine_mg=sum(p.caffeine_mg for p in carb_items),
                    brand=template.brand,
                    volume_ml=template.volume_ml,
                    bottle_index=template.bottle_index,
                )
                label = f"{label_prefix}-Drink"
                duration_h = duration_min / 60.0
                bottle_carbs_per_hour = total_carbs / duration_h if duration_h > 0 else 0.0
            else:
                bottle_product = bottle_group[0]
                label = f"{label_prefix}-Wasser"
                bottle_carbs_per_hour = 0.0
            # Wird die Flasche rechnerisch erst nach dem Ende des Plans leer,
            # ist sie am Ziel noch nicht ganz ausgetrunken - der Eintrag zeigt
            # dann "leer im Ziel" statt eines künstlich vorgezogenen Zeitpunkts,
            # und vermerkt, wie viel davon bis dahin tatsächlich nötig ist
            # (Hilfe bei der Wahl der Flaschengröße an der Feedzone).
            if natural_end <= end_min:
                event_time = window_end
            else:
                event_time = target_time_h * 60.0
                available_min = max(0.0, event_time - window_start)
                consumed_ml = min(volume_ml, fluid_rate_ml_per_hour * available_min / 60.0)
                consumed_fraction = consumed_ml / volume_ml if volume_ml > 0 else 0.0
                bottle_product = replace(
                    bottle_product,
                    name=f"{bottle_product.name}\n(nur ca. {consumed_ml:.0f} von {volume_ml:.0f} ml nötig)",
                    carbs_g=round(bottle_product.carbs_g * consumed_fraction, 1),
                    caffeine_mg=round(bottle_product.caffeine_mg * consumed_fraction, 1),
                )
            raw.append((round(event_time, 1), bottle_product, label, False))
            gel_segments.append((window_start, window_end, bottle_carbs_per_hour))

        cursor_min = natural_end

    # Zeitfenster ohne (weitere) Flasche: volle Ziel-KH-Rate muss aus Gels kommen.
    tail_start = gel_segments[-1][1] if gel_segments else NUTRITION_START_DELAY_MIN
    if tail_start < end_min:
        gel_segments.append((tail_start, end_min, 0.0))

    if gel_products:
        avg_gel_carbs = sum(p.carbs_g for p in gel_products) / len(gel_products)
        t, idx, count = NUTRITION_START_DELAY_MIN, 0, 0
        for seg_start, seg_end, bottle_carbs_per_hour in gel_segments:
            if t < seg_start:
                t = seg_start
            gel_carbs_per_hour_needed = max(0.0, carbs_per_hour - bottle_carbs_per_hour)
            if gel_carbs_per_hour_needed <= 0:
                t = seg_end
                continue
            interval_min = max(15.0, (avg_gel_carbs / gel_carbs_per_hour_needed) * 60.0)
            while t <= seg_end and t <= end_min:
                product = gel_products[idx % len(gel_products)]
                count += 1
                raw.append((round(t, 1), product, f"Gel{count}", False))
                t += interval_min
                idx += 1

    raw.sort(key=lambda item: item[0])

    events: list[NutritionEvent] = []
    cumulative = 0.0
    for time_min, product, label, is_feed_zone in raw:
        cumulative += product.carbs_g
        events.append(NutritionEvent(
            time_min=time_min,
            product=product,
            cumulative_carbs_g=round(cumulative, 1),
            label=label,
            is_feed_zone=is_feed_zone,
        ))

    return events
