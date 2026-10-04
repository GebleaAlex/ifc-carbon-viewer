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

from app.carbon.estimate import apply_estimates, summarize
from app.ifc.geometry import ElementMesh, tessellate
from app.ifc.glb import build_glb
from app.schemas import CarbonSummary, ElementExtras, ElementSummary, MaterialLayer

log = logging.getLogger(__name__)

VOLUME_QUANTITY_NAMES = ("NetVolume", "GrossVolume", "Volume")
SLAB_AREA_QUANTITY_NAMES = ("GrossArea", "NetArea", "Area")
SPACE_AREA_QUANTITY_NAMES = ("GrossFloorArea", "NetFloorArea")
NON_FLOOR_SLAB_TYPES = {"ROOF", "LANDING"}
UNIT_NAMES = {1.0: "m", 0.1: "dm", 0.01: "cm", 0.001: "mm", 0.3048: "ft", 0.0254: "in"}


@dataclass
class ParsedModel:
    schema_version: str
    elements: list[ElementSummary]
    extras: dict[str, ElementExtras]
    glb: bytes
    carbon: CarbonSummary
    storeys: list[str]
    parse_seconds: float
    floor_area_m2: float | None = None
    floor_area_source: str | None = None
    length_unit: str | None = None
    ifc_classes: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class UnitScales:
    """Factors that turn project units into SI. IFC allows volumes and areas in units unrelated to the length unit
    (Revit exports millimetres for lengths and cubic metres for volumes), so each one is read separately."""

    length: float
    area: float
    volume: float

    @classmethod
    def of(cls, model: ifcopenshell.file) -> UnitScales:
        def scale(unit_type: str, power: int, fallback: float) -> float:
            try:
                unit = unit_util.get_project_unit(model, unit_type)
                if unit is None:
                    return fallback
                if unit.is_a("IfcSIUnit"):
                    # The prefix applies to the metre, so MILLI + CUBIC_METRE is (1e-3)^3. calculate_unit_scale
                    # would return 1e-3 here.
                    return float(unit_util.get_prefix_multiplier(unit.Prefix)) ** power
                return float(unit_util.calculate_unit_scale(model, unit_type))
            except Exception:  # pragma: no cover - malformed unit assignments
                return fallback

        length = scale("LENGTHUNIT", 1, 1.0)
        return cls(length=length, area=scale("AREAUNIT", 2, length**2), volume=scale("VOLUMEUNIT", 3, length**3))

    @property
    def length_name(self) -> str:
        return next((name for value, name in UNIT_NAMES.items() if abs(value - self.length) < 1e-9), f"{self.length} m")


def _clean(value):
    """Make pset values JSON friendly (entity references become their string form)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if k != "id"}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, ifcopenshell.entity_instance):
        return str(value)
    return value


def _material_name(material) -> str:
    return (getattr(material, "Name", None) or "").strip() or f"Unnamed material #{material.id()}"


def _category(*candidates) -> str | None:
    for candidate in candidates:
        value = getattr(candidate, "Category", None) if candidate is not None else None
        if value:
            return value
    return None


def material_layers(element, length_scale: float) -> list[MaterialLayer]:
    """Read the element's materials with the share of its volume each one takes, where the model says so."""
    try:
        material = element_util.get_material(element, should_skip_usage=True, should_inherit=True)
    except Exception:  # pragma: no cover - defensive against odd material assignments
        material = None
    if material is None:
        return []

    if material.is_a("IfcMaterialLayerSet"):
        layers = list(material.MaterialLayers or [])
        total = sum(float(layer.LayerThickness or 0.0) for layer in layers)
        out = []
        for layer in layers:
            if layer.Material is None:  # air gaps and other voids still count towards the total thickness
                continue
            thickness = float(layer.LayerThickness or 0.0)
            out.append(
                MaterialLayer(
                    material=_material_name(layer.Material),
                    ifc_category=_category(layer, layer.Material),
                    thickness_m=round(thickness * length_scale, 4),
                    fraction=round(thickness / total, 4) if total > 0 else None,
                )
            )
        return out

    if material.is_a("IfcMaterialConstituentSet"):
        constituents = [c for c in (material.MaterialConstituents or []) if c.Material is not None]
        fractions = [getattr(c, "Fraction", None) for c in constituents]
        known = all(f is not None for f in fractions) and sum(fractions) > 0
        return [
            MaterialLayer(
                material=_material_name(c.Material),
                ifc_category=_category(c, c.Material),
                fraction=float(f) if known else None,
            )
            for c, f in zip(constituents, fractions, strict=True)
        ]

    if material.is_a("IfcMaterialProfileSet"):
        profiles = [p for p in (material.MaterialProfiles or []) if p.Material is not None]
        return [
            MaterialLayer(
                material=_material_name(p.Material),
                ifc_category=_category(p, p.Material),
                fraction=1.0 if len(profiles) == 1 else None,
            )
            for p in profiles
        ]

    if material.is_a("IfcMaterialList"):
        materials = [m for m in (material.Materials or []) if m is not None]
        return [
            MaterialLayer(
                material=_material_name(m), ifc_category=_category(m), fraction=1.0 if len(materials) == 1 else None
            )
            for m in materials
        ]

    if material.is_a("IfcMaterial"):
        return [MaterialLayer(material=_material_name(material), ifc_category=_category(material), fraction=1.0)]
    return []


def _storey_of(element) -> str | None:
    """The storey that contains the element, looking through aggregates (curtain wall plates, stair flights)."""
    obj = element
    container = None
    while obj is not None and container is None:
        container = element_util.get_container(obj)
        if container is None:
            obj = element_util.get_aggregate(obj)
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


def _first_quantity(qtos: dict[str, dict], names: tuple[str, ...]) -> float | None:
    for name in names:
        for qto in qtos.values():
            value = qto.get(name)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return None


def _is_built_element(product) -> bool:
    return product.is_a("IfcElement") and not (product.is_a("IfcOpeningElement") or product.is_a("IfcFeatureElement"))


def _parts(product) -> list:
    return [
        obj
        for rel in getattr(product, "IsDecomposedBy", None) or []
        for obj in rel.RelatedObjects
        if _is_built_element(obj)
    ]


def _parent(product):
    for rel in getattr(product, "Decomposes", None) or []:
        if _is_built_element(rel.RelatingObject):
            return rel.RelatingObject
    return None


def floor_area(
    model: ifcopenshell.file, scales: UnitScales, meshes: dict[int, ElementMesh]
) -> tuple[float | None, str | None]:
    """Floor area for the kgCO2e/m2 intensity.

    Spaces with floor-area quantities are the best source. Without them, floor slabs (not roofs or landings)
    are used: their area quantity when present, otherwise the plan area of the slab's top faces.
    """
    space_total = 0.0
    for space in model.by_type("IfcSpace"):
        area = _first_quantity(element_util.get_psets(space, qtos_only=True), SPACE_AREA_QUANTITY_NAMES)
        if area:
            space_total += area * scales.area
    if space_total > 0:
        return space_total, "spaces"

    slab_total, used_geometry, used_quantity = 0.0, False, False
    for slab in model.by_type("IfcSlab"):
        parent = _parent(slab)
        if (element_util.get_predefined_type(slab) or "") in NON_FLOOR_SLAB_TYPES or (
            parent is not None and parent.is_a("IfcRoof")
        ):
            continue
        area = _first_quantity(element_util.get_psets(slab, qtos_only=True), SLAB_AREA_QUANTITY_NAMES)
        if area:
            slab_total += area * scales.area
            used_quantity = True
        elif (mesh := meshes.get(slab.id())) is not None and mesh.top_area_m2 > 0:
            slab_total += mesh.top_area_m2
            used_geometry = True
    if slab_total > 0:
        return slab_total, "slab geometry" if used_geometry and not used_quantity else "slab quantities"
    return None, None


def parse_ifc(path: Path, threads: int = 1) -> ParsedModel:
    started = time.perf_counter()
    model = ifcopenshell.open(str(path))
    scales = UnitScales.of(model)
    meshes: dict[int, ElementMesh] = tessellate(model, threads=threads)  # IfcOpenShell outputs metres

    storeys = sorted(model.by_type("IfcBuildingStorey"), key=_storey_elevation)
    storey_names = [s.Name or f"Storey #{s.id()}" for s in storeys]

    raw: list[ElementSummary] = []
    extras: dict[str, ElementExtras] = {}
    ifc_classes: dict[str, int] = {}

    for product in model.by_type("IfcElement"):
        if not _is_built_element(product):
            continue
        qtos = element_util.get_psets(product, qtos_only=True)
        psets = element_util.get_psets(product, psets_only=True)
        mesh = meshes.get(product.id())
        parts = _parts(product)
        parent = _parent(product)

        volume = _first_quantity(qtos, VOLUME_QUANTITY_NAMES)
        volume_source = None
        if volume is not None:
            volume *= scales.volume
            volume_source = "quantity"
        elif mesh is not None and mesh.volume_m3 > 0:
            volume = mesh.volume_m3
            volume_source = "geometry"

        layers = material_layers(product, scales.length)
        element_type = element_util.get_type(product)
        summary = ElementSummary(
            express_id=product.id(),
            global_id=product.GlobalId,
            ifc_class=product.is_a(),
            name=product.Name,
            type_name=element_type.Name if element_type is not None else None,
            storey=_storey_of(product),
            materials=list(dict.fromkeys(layer.material for layer in layers)),
            layers=layers,
            volume_m3=round(volume, 4) if volume is not None and not parts else None,
            volume_source=volume_source if not parts else None,
            has_geometry=mesh is not None,
            is_assembly=bool(parts),
        )
        raw.append(summary)
        ifc_classes[summary.ifc_class] = ifc_classes.get(summary.ifc_class, 0) + 1
        extras[summary.global_id] = ElementExtras(
            description=product.Description,
            object_type=getattr(product, "ObjectType", None),
            predefined_type=element_util.get_predefined_type(product),
            parent_global_id=parent.GlobalId if parent is not None else None,
            part_global_ids=[p.GlobalId for p in parts],
            property_sets=_clean(psets),
            quantity_sets=_clean(qtos),
        )

    elements = apply_estimates(raw)
    area, area_source = floor_area(model, scales, meshes)
    known_ids = {e.express_id for e in elements}
    glb = build_glb(m for eid, m in meshes.items() if eid in known_ids)
    carbon = summarize(elements, floor_area_m2=area, floor_area_source=area_source)
    elapsed = round(time.perf_counter() - started, 2)
    log.info("parsed %s: %d elements, %d meshes in %.1fs", path.name, len(elements), len(meshes), elapsed)
    return ParsedModel(
        schema_version=model.schema,
        elements=elements,
        extras=extras,
        glb=glb,
        carbon=carbon,
        storeys=storey_names,
        parse_seconds=elapsed,
        floor_area_m2=area,
        floor_area_source=area_source,
        length_unit=scales.length_name,
        ifc_classes=dict(sorted(ifc_classes.items(), key=lambda kv: kv[1], reverse=True)),
    )
