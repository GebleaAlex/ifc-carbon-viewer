"""Embodied carbon estimation from material category, density and volume.

The approach is intentionally transparent:

    mass [kg]        = volume [m3] x density [kg/m3]
    carbon [kgCO2e]  = mass [kg]   x factor [kgCO2e/kg]

Volume comes from IFC base quantities when the model has them, and from the
tessellated geometry when it does not. Elements whose material cannot be
classified are reported as such rather than silently given a factor.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from app.schemas import CarbonBucket, CarbonSummary, ElementSummary, MaterialFactor

FACTORS_PATH = Path(__file__).with_name("factors.json")
UNCLASSIFIED = "unclassified"
UNCLASSIFIED_COLOR = "#64748b"


@lru_cache(maxsize=1)
def load_factors(path: Path = FACTORS_PATH) -> list[MaterialFactor]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MaterialFactor.model_validate(item) for item in payload["factors"]]


def factor_index() -> dict[str, MaterialFactor]:
    return {f.category: f for f in load_factors()}


def classify_material(material_names: list[str], ifc_category: str | None = None) -> str | None:
    """Map free-text material names (and the optional IfcMaterial.Category) to a factor category.

    Matching is keyword based and case-insensitive. The first material that matches wins,
    since the first material in an IFC layer set is usually the structural one.
    """
    candidates = [n for n in ([ifc_category] + list(material_names)) if n]
    factors = load_factors()
    for candidate in candidates:
        lowered = f" {candidate.lower()} "
        for factor in factors:
            if factor.category == candidate.lower():
                return factor.category
            if any(keyword in lowered for keyword in factor.keywords):
                return factor.category
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


def _buckets(elements: list[ElementSummary], key_fn, label_fn, total: float) -> list[CarbonBucket]:
    grouped: dict[str, list[ElementSummary]] = defaultdict(list)
    for el in elements:
        grouped[key_fn(el)].append(el)
    buckets = []
    for key, items in grouped.items():
        carbon = sum(e.carbon_kgco2e or 0.0 for e in items)
        buckets.append(
            CarbonBucket(
                key=key,
                label=label_fn(key),
                element_count=len(items),
                volume_m3=round(sum(e.volume_m3 or 0.0 for e in items), 3),
                mass_kg=round(sum(e.mass_kg or 0.0 for e in items), 1),
                carbon_kgco2e=round(carbon, 1),
                share_percent=round(100.0 * carbon / total, 1) if total > 0 else 0.0,
            )
        )
    return sorted(buckets, key=lambda b: b.carbon_kgco2e, reverse=True)


def summarize(elements: list[ElementSummary], top_n: int = 10) -> CarbonSummary:
    total = sum(e.carbon_kgco2e or 0.0 for e in elements)
    labels = {f.category: f.label for f in load_factors()}
    labels[UNCLASSIFIED] = "Unclassified"
    estimated = [e for e in elements if e.carbon_kgco2e is not None]
    return CarbonSummary(
        total_kgco2e=round(total, 1),
        estimated_elements=len(estimated),
        unclassified_elements=sum(1 for e in elements if e.material_category is None),
        missing_volume_elements=sum(1 for e in elements if e.volume_m3 is None),
        by_material_category=_buckets(
            elements, lambda e: e.material_category or UNCLASSIFIED, lambda k: labels.get(k, k), total
        ),
        by_storey=_buckets(elements, lambda e: e.storey or "No storey", lambda k: k, total),
        by_ifc_class=_buckets(elements, lambda e: e.ifc_class, lambda k: k, total),
        top_elements=sorted(estimated, key=lambda e: e.carbon_kgco2e or 0.0, reverse=True)[:top_n],
    )
