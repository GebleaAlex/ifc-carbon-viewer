"""Turn an IFC file into element metadata, geometry (GLB) and a carbon estimate."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element as element_util
import ifcopenshell.util.placement as placement_util
import ifcopenshell.util.unit as unit_util

from app.carbon.estimate import classify_material, estimate_element, summarize
from app.ifc.geometry import ElementMesh, tessellate
from app.ifc.glb import build_glb
from app.schemas import CarbonSummary, ElementDetail, ElementSummary

log = logging.getLogger(__name__)

VOLUME_QUANTITY_NAMES = ("NetVolume", "GrossVolume", "Volume")


@dataclass
class ParsedModel:
    schema_version: str
    elements: list[ElementSummary]
    details: dict[str, ElementDetail]
    glb: bytes
    carbon: CarbonSummary
    storeys: list[str]
    parse_seconds: float
    ifc_classes: dict[str, int] = field(default_factory=dict)


def _clean(value):
    """Make pset values JSON friendly (entity references become their string form)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if k != "id"}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, ifcopenshell.entity_instance):
        return str(value)
    return value


def _material_names(element) -> tuple[list[str], str | None]:
    """Collect material names for an element and the IfcMaterial.Category of the first one, if any."""
    names: list[str] = []
    category: str | None = None
    try:
        materials = element_util.get_materials(element, should_inherit=True)
    except Exception:  # pragma: no cover
        materials = []
    for material in materials or []:
        name = getattr(material, "Name", None)
        if name and name not in names:
            names.append(name)
        if category is None:
            category = getattr(material, "Category", None)
    return names, category


def _storey_name(element) -> str | None:
    container = element_util.get_container(element)
    while container is not None and not container.is_a("IfcBuildingStorey"):
        container = element_util.get_aggregate(container)
    if container is not None:
        return container.Name or f"Storey #{container.id()}"
    return None


def _storey_elevation(storey) -> float:
    try:
        return float(placement_util.get_local_placement(storey.ObjectPlacement)[2][3])
    except Exception:  # pragma: no cover
        return float(getattr(storey, "Elevation", 0.0) or 0.0)


def _volume_from_quantities(qtos: dict[str, dict], unit_scale: float) -> float | None:
    for qto in qtos.values():
        for name in VOLUME_QUANTITY_NAMES:
            value = qto.get(name)
            if isinstance(value, (int, float)) and value > 0:
                return float(value) * unit_scale**3
    return None


def parse_ifc(path: Path, threads: int = 1) -> ParsedModel:
    started = time.perf_counter()
    model = ifcopenshell.open(str(path))
    unit_scale = unit_util.calculate_unit_scale(model)  # project length unit -> metres
    meshes: dict[int, ElementMesh] = tessellate(model, threads=threads)

    storeys = sorted(model.by_type("IfcBuildingStorey"), key=_storey_elevation)
    storey_names = [s.Name or f"Storey #{s.id()}" for s in storeys]

    elements: list[ElementSummary] = []
    details: dict[str, ElementDetail] = {}
    ifc_classes: dict[str, int] = {}

    for product in model.by_type("IfcElement"):
        if product.is_a("IfcOpeningElement") or product.is_a("IfcFeatureElement"):
            continue
        psets = element_util.get_psets(product, psets_only=True)
        qtos = element_util.get_psets(product, qtos_only=True)
        material_names, ifc_category = _material_names(product)
        mesh = meshes.get(product.id())

        volume = _volume_from_quantities(qtos, unit_scale)
        volume_source = "quantity" if volume is not None else None
        if volume is None and mesh is not None:
            volume = mesh.volume_m3 * unit_scale**3
            volume_source = "geometry" if volume > 0 else None
            if volume <= 0:
                volume = None

        category = classify_material(material_names, ifc_category)
        mass, carbon = estimate_element(category, volume)
        element_type = element_util.get_type(product)

        summary = ElementSummary(
            express_id=product.id(),
            global_id=product.GlobalId,
            ifc_class=product.is_a(),
            name=product.Name,
            type_name=element_type.Name if element_type is not None else None,
            storey=_storey_name(product),
            materials=material_names,
            material_category=category,
            volume_m3=round(volume, 4) if volume is not None else None,
            volume_source=volume_source,
            mass_kg=round(mass, 1) if mass is not None else None,
            carbon_kgco2e=round(carbon, 2) if carbon is not None else None,
            has_geometry=mesh is not None,
        )
        elements.append(summary)
        ifc_classes[summary.ifc_class] = ifc_classes.get(summary.ifc_class, 0) + 1
        details[summary.global_id] = ElementDetail(
            **summary.model_dump(),
            description=product.Description,
            object_type=getattr(product, "ObjectType", None),
            predefined_type=element_util.get_predefined_type(product),
            property_sets=_clean(psets),
            quantity_sets=_clean(qtos),
        )

    known_ids = {e.express_id for e in elements}
    glb = build_glb(m for eid, m in meshes.items() if eid in known_ids)
    carbon = summarize(elements)
    elapsed = time.perf_counter() - started
    log.info("parsed %s: %d elements, %d meshes in %.1fs", path.name, len(elements), len(meshes), elapsed)
    return ParsedModel(
        schema_version=model.schema,
        elements=elements,
        details=details,
        glb=glb,
        carbon=carbon,
        storeys=storey_names,
        parse_seconds=round(time.perf_counter() - started, 2),
        ifc_classes=dict(sorted(ifc_classes.items(), key=lambda kv: kv[1], reverse=True)),
    )
