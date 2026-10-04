"""Flat exports of a parsed model: one CSV row per element and material layer, and a JSON report."""

from __future__ import annotations

import csv
import io

from app.schemas import CarbonSummary, ElementSummary, MaterialUsage, ModelSummary

CSV_COLUMNS = [
    "global_id",
    "name",
    "ifc_class",
    "type_name",
    "storey",
    "material",
    "material_category",
    "layer_fraction",
    "layer_thickness_m",
    "volume_m3",
    "volume_source",
    "mass_kg",
    "carbon_kgco2e",
    "is_assembly",
]


def elements_csv(elements: list[ElementSummary]) -> str:
    """One row per material layer, so the carbon column adds up to the model total (assemblies carry none)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for e in elements:
        base = [e.global_id, e.name or "", e.ifc_class, e.type_name or "", e.storey or ""]
        layers = [layer for layer in e.layers if layer.volume_m3 or layer.category] or None
        if not layers:
            writer.writerow(
                base
                + [
                    "; ".join(e.materials),
                    e.material_category or "",
                    "",
                    "",
                    _num(e.volume_m3),
                    e.volume_source or "",
                    _num(e.mass_kg),
                    _num(e.carbon_kgco2e),
                    str(e.is_assembly).lower(),
                ]
            )
            continue
        for layer in layers:
            writer.writerow(
                base
                + [
                    layer.material,
                    layer.category or "",
                    _num(layer.fraction),
                    _num(layer.thickness_m),
                    _num(layer.volume_m3),
                    e.volume_source or "",
                    _num(layer.mass_kg),
                    _num(layer.carbon_kgco2e),
                    str(e.is_assembly).lower(),
                ]
            )
    return buffer.getvalue()


def _num(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def report(meta: ModelSummary, carbon: CarbonSummary, materials: list[MaterialUsage]) -> dict:
    return {
        "model": meta.model_dump(),
        "carbon": carbon.model_dump(exclude={"top_elements"}),
        "top_elements": [
            {k: e.model_dump()[k] for k in ("global_id", "name", "ifc_class", "storey", "carbon_kgco2e")}
            for e in carbon.top_elements
        ],
        "materials": [m.model_dump() for m in materials],
        "disclaimer": "Indicative A1-A3 estimate from generic factors. Not suitable for reporting.",
    }
