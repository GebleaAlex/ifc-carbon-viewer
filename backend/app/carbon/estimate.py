"""Embodied carbon estimation from material category, density and volume.

The approach is intentionally transparent:

    mass [kg]        = volume [m3] x density [kg/m3]
    carbon [kgCO2e]  = mass [kg]   x factor [kgCO2e/kg]

Volume comes from IFC base quantities when the model has them, and from the
tessellated geometry when it does not. Elements made of several materials are
split by layer thickness or constituent fraction, so a brick wall with mineral
wool and plaster is not counted as solid brick. Materials that cannot be
classified are reported as such rather than silently given a factor.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path

from app.schemas import CarbonBucket, CarbonSummary, ElementSummary, MaterialFactor, MaterialLayer, MaterialUsage

FACTORS_PATH = Path(__file__).with_name("factors.json")
UNCLASSIFIED = "unclassified"
UNCLASSIFIED_COLOR = "#64748b"


@lru_cache(maxsize=1)
def load_factors(path: Path = FACTORS_PATH) -> list[MaterialFactor]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MaterialFactor.model_validate(item) for item in payload["factors"]]


def factor_index() -> dict[str, MaterialFactor]:
    return {f.category: f for f in load_factors()}


@lru_cache(maxsize=1)
def _keyword_patterns() -> list[tuple[re.Pattern[str], bool, int, str]]:
    """One regex per keyword: specific keywords before weak ones (``~``), longest first.

    A keyword must not be glued to other letters, so ``ipe`` matches "IPE 300" but not "pipe",
    and ``hea`` matches "HEA200" but not "heating". Digits may follow (``c30`` in "C30/37").
    """
    patterns = []
    for factor in load_factors():
        for keyword in factor.keywords:
            weak = keyword.startswith("~")
            word = keyword.lstrip("~").strip().lower()
            if word:
                pattern = re.compile(rf"(?<![^\W\d_]){re.escape(word)}(?![^\W\d_])")
                patterns.append((pattern, weak, len(word), factor.category))
    return sorted(patterns, key=lambda p: (p[1], -p[2]))


def classify_name(name: str | None) -> str | None:
    """Classify one free-text material name. The most specific keyword wins ("glass wool" beats "glass")."""
    if not name:
        return None
    lowered = name.lower()
    if lowered in factor_index():
        return lowered
    for pattern, _, _, category in _keyword_patterns():
        if pattern.search(lowered):
            return category
    return None


def classify_material(material_names: list[str], ifc_category: str | None = None) -> str | None:
    """Map material names (and the optional IfcMaterial.Category) to a factor category.

    The IFC category is checked first because authoring tools fill it deliberately; after that
    the first material name that matches wins.
    """
    for candidate in [ifc_category, *material_names]:
        category = classify_name(candidate)
        if category:
            return category
    return None


def estimate_element(category: str | None, volume_m3: float | None) -> tuple[float | None, float | None]:
    """Return (mass_kg, carbon_kgco2e) or (None, None) when the estimate is not possible."""
    if category is None or volume_m3 is None:
        return None, None
    factor = factor_index().get(category)
    if factor is None:
        return None, None
    mass = volume_m3 * factor.density_kg_m3
    return mass, mass * factor.factor_kgco2e_per_kg


def auto_category(layer: MaterialLayer) -> str | None:
    return classify_material([layer.material], layer.ifc_category)


def make_resolver(overrides: dict[str, str] | None = None) -> Callable[[MaterialLayer], str | None]:
    """Return a function that gives the effective category of a layer, honouring per-model overrides."""
    overrides = overrides or {}

    def resolve(layer: MaterialLayer) -> str | None:
        if layer.material in overrides:
            value = overrides[layer.material]
            return None if value == UNCLASSIFIED else value
        return auto_category(layer)

    return resolve


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def estimate(element: ElementSummary, resolve: Callable[[MaterialLayer], str | None]) -> ElementSummary:
    """Fill in category, volume, mass and carbon for every layer and for the element as a whole."""
    layers = [layer.model_copy(update={"category": resolve(layer)}) for layer in element.layers]
    for layer in layers:
        layer.volume_m3 = layer.mass_kg = layer.carbon_kgco2e = None

    volume = element.volume_m3
    if not element.is_assembly and volume is not None and layers:
        fractions = [layer.fraction for layer in layers]
        if all(f is not None for f in fractions) and sum(fractions) > 0:  # type: ignore[arg-type]
            # Fractions below 1 in total leave room for voids such as air gaps; above 1 they are rescaled.
            total = max(sum(fractions), 1.0)  # type: ignore[arg-type]
            for layer in layers:
                layer.volume_m3 = volume * (layer.fraction or 0.0) / total
        else:
            # The model lists materials without saying how much of each: give the volume to the
            # first one we can classify (the structural material usually comes first).
            chosen = next((layer for layer in layers if layer.category), layers[0])
            chosen.volume_m3 = volume
        for layer in layers:
            mass, carbon = estimate_element(layer.category, layer.volume_m3)
            layer.mass_kg, layer.carbon_kgco2e = mass, carbon

    classified = [layer for layer in layers if layer.category and layer.volume_m3]
    if classified:
        dominant = max(classified, key=lambda layer: layer.volume_m3 or 0.0).category
    else:
        dominant = next((layer.category for layer in layers if layer.category), None)
    mass = sum(layer.mass_kg for layer in classified if layer.mass_kg is not None) if classified else None
    carbon = sum(layer.carbon_kgco2e for layer in classified if layer.carbon_kgco2e is not None) if classified else None
    partial = bool(classified) and any(layer.category is None and (layer.volume_m3 or 0) > 0 for layer in layers)

    for layer in layers:
        layer.volume_m3 = _round(layer.volume_m3, 4)
        layer.mass_kg = _round(layer.mass_kg, 1)
        layer.carbon_kgco2e = _round(layer.carbon_kgco2e, 2)

    return element.model_copy(
        update={
            "layers": layers,
            "material_category": dominant,
            "mass_kg": _round(mass, 1),
            "carbon_kgco2e": _round(carbon, 2),
            "partially_classified": partial,
        }
    )


def apply_estimates(
    elements: Iterable[ElementSummary], overrides: dict[str, str] | None = None
) -> list[ElementSummary]:
    resolve = make_resolver(overrides)
    return [estimate(element, resolve) for element in elements]


class _Acc:
    __slots__ = ("elements", "volume", "mass", "carbon")

    def __init__(self) -> None:
        self.elements: set[str] = set()
        self.volume = 0.0
        self.mass = 0.0
        self.carbon = 0.0

    def add(self, element_id: str, volume: float | None, mass: float | None, carbon: float | None) -> None:
        self.elements.add(element_id)
        self.volume += volume or 0.0
        self.mass += mass or 0.0
        self.carbon += carbon or 0.0


def _to_buckets(groups: dict[str, _Acc], label_fn: Callable[[str], str], total: float) -> list[CarbonBucket]:
    buckets = [
        CarbonBucket(
            key=key,
            label=label_fn(key),
            element_count=len(acc.elements),
            volume_m3=round(acc.volume, 3),
            mass_kg=round(acc.mass, 1),
            carbon_kgco2e=round(acc.carbon, 1),
            share_percent=round(100.0 * acc.carbon / total, 1) if total > 0 else 0.0,
        )
        for key, acc in groups.items()
    ]
    return sorted(buckets, key=lambda b: (b.carbon_kgco2e, b.element_count), reverse=True)


def summarize(
    elements: list[ElementSummary],
    top_n: int = 10,
    floor_area_m2: float | None = None,
    floor_area_source: str | None = None,
) -> CarbonSummary:
    """Totals and breakdowns. Assemblies are skipped because their parts already carry the carbon."""
    counted = [e for e in elements if not e.is_assembly]
    total = sum(e.carbon_kgco2e or 0.0 for e in counted)
    labels = {f.category: f.label for f in load_factors()}
    labels[UNCLASSIFIED] = "Unclassified"

    by_material: dict[str, _Acc] = defaultdict(_Acc)
    by_storey: dict[str, _Acc] = defaultdict(_Acc)
    by_class: dict[str, _Acc] = defaultdict(_Acc)
    for e in counted:
        layers_with_volume = [layer for layer in e.layers if layer.volume_m3]
        if layers_with_volume:
            for layer in layers_with_volume:
                by_material[layer.category or UNCLASSIFIED].add(
                    e.global_id, layer.volume_m3, layer.mass_kg, layer.carbon_kgco2e
                )
        else:
            by_material[e.material_category or UNCLASSIFIED].add(e.global_id, e.volume_m3, e.mass_kg, e.carbon_kgco2e)
        by_storey[e.storey or "No storey"].add(e.global_id, e.volume_m3, e.mass_kg, e.carbon_kgco2e)
        by_class[e.ifc_class].add(e.global_id, e.volume_m3, e.mass_kg, e.carbon_kgco2e)

    estimated = [e for e in counted if e.carbon_kgco2e is not None]
    intensity = round(total / floor_area_m2, 1) if floor_area_m2 else None
    return CarbonSummary(
        total_kgco2e=round(total, 1),
        estimated_elements=len(estimated),
        unclassified_elements=sum(1 for e in counted if e.material_category is None),
        partially_classified_elements=sum(1 for e in counted if e.partially_classified),
        missing_volume_elements=sum(1 for e in counted if e.volume_m3 is None),
        assembly_elements=len(elements) - len(counted),
        gross_floor_area_m2=round(floor_area_m2, 1) if floor_area_m2 else None,
        floor_area_source=floor_area_source if floor_area_m2 else None,
        intensity_kgco2e_m2=intensity,
        by_material_category=_to_buckets(by_material, lambda k: labels.get(k, k), total),
        by_storey=_to_buckets(by_storey, lambda k: k, total),
        by_ifc_class=_to_buckets(by_class, lambda k: k, total),
        top_elements=sorted(estimated, key=lambda e: e.carbon_kgco2e or 0.0, reverse=True)[:top_n],
    )


def material_usage(elements: list[ElementSummary], overrides: dict[str, str] | None = None) -> list[MaterialUsage]:
    """Every distinct material name in the model with its automatic and effective category."""
    overrides = overrides or {}
    rows: dict[str, MaterialUsage] = {}
    for e in elements:
        if e.is_assembly:
            continue
        for layer in e.layers:
            row = rows.get(layer.material)
            if row is None:
                auto = auto_category(layer)
                override = overrides.get(layer.material)
                row = rows[layer.material] = MaterialUsage(
                    material=layer.material,
                    ifc_category=layer.ifc_category,
                    auto_category=auto,
                    category=(None if override == UNCLASSIFIED else override) if override else auto,
                    overridden=layer.material in overrides,
                    element_count=0,
                    volume_m3=0.0,
                    carbon_kgco2e=0.0,
                )
            row.element_count += 1
            row.volume_m3 = round(row.volume_m3 + (layer.volume_m3 or 0.0), 4)
            row.carbon_kgco2e = round(row.carbon_kgco2e + (layer.carbon_kgco2e or 0.0), 2)
    return sorted(rows.values(), key=lambda r: (r.category is not None, -r.carbon_kgco2e, r.material))
