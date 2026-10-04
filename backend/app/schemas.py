"""Pydantic schemas shared by the parser, the store and the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModelStatus = Literal["processing", "ready", "failed"]
VolumeSource = Literal["quantity", "geometry"]
FloorAreaSource = Literal["spaces", "slab quantities", "slab geometry"]


class MaterialLayer(BaseModel):
    """One material of an element and the share of the element's volume it takes.

    ``fraction`` comes from layer thicknesses (IfcMaterialLayerSet) or constituent fractions
    (IfcMaterialConstituentSet). It is ``None`` when the model lists several materials without
    saying how much of each there is; the estimator then attributes the whole volume to the
    first material it can classify.
    """

    material: str
    ifc_category: str | None = None
    thickness_m: float | None = None
    fraction: float | None = None
    category: str | None = None
    volume_m3: float | None = None
    mass_kg: float | None = None
    carbon_kgco2e: float | None = None


class ElementSummary(BaseModel):
    express_id: int
    global_id: str
    ifc_class: str
    name: str | None = None
    type_name: str | None = None
    storey: str | None = None
    materials: list[str] = Field(default_factory=list)
    layers: list[MaterialLayer] = Field(default_factory=list)
    material_category: str | None = None
    volume_m3: float | None = None
    volume_source: VolumeSource | None = None
    mass_kg: float | None = None
    carbon_kgco2e: float | None = None
    has_geometry: bool = False
    is_assembly: bool = False
    partially_classified: bool = False


class ElementDetail(ElementSummary):
    description: str | None = None
    object_type: str | None = None
    predefined_type: str | None = None
    parent_global_id: str | None = None
    part_global_ids: list[str] = Field(default_factory=list)
    property_sets: dict[str, dict[str, object]] = Field(default_factory=dict)
    quantity_sets: dict[str, dict[str, object]] = Field(default_factory=dict)


class ElementExtras(BaseModel):
    """The parts of an element detail that never change after parsing (stored separately from the summary)."""

    description: str | None = None
    object_type: str | None = None
    predefined_type: str | None = None
    parent_global_id: str | None = None
    part_global_ids: list[str] = Field(default_factory=list)
    property_sets: dict[str, dict[str, object]] = Field(default_factory=dict)
    quantity_sets: dict[str, dict[str, object]] = Field(default_factory=dict)


class CarbonBucket(BaseModel):
    key: str
    label: str
    element_count: int
    volume_m3: float
    mass_kg: float
    carbon_kgco2e: float
    share_percent: float


class CarbonSummary(BaseModel):
    total_kgco2e: float
    estimated_elements: int
    unclassified_elements: int
    partially_classified_elements: int = 0
    missing_volume_elements: int
    assembly_elements: int = 0
    gross_floor_area_m2: float | None = None
    floor_area_source: FloorAreaSource | None = None
    intensity_kgco2e_m2: float | None = None
    by_material_category: list[CarbonBucket]
    by_storey: list[CarbonBucket]
    by_ifc_class: list[CarbonBucket]
    top_elements: list[ElementSummary]


class MaterialFactor(BaseModel):
    category: str
    label: str
    density_kg_m3: float
    factor_kgco2e_per_kg: float
    color: str
    keywords: list[str]
    note: str | None = None


class MaterialUsage(BaseModel):
    """A material name as it appears in the model, how it was classified and what it contributes."""

    material: str
    ifc_category: str | None = None
    auto_category: str | None = None
    category: str | None = None
    overridden: bool = False
    element_count: int
    volume_m3: float
    carbon_kgco2e: float


class MaterialMapping(BaseModel):
    """Per-model overrides: material name -> factor category, or ``"unclassified"`` to leave it out."""

    overrides: dict[str, str] = Field(default_factory=dict)


class ModelSummary(BaseModel):
    id: str
    name: str
    status: ModelStatus
    error: str | None = None
    created_at: str
    schema_version: str | None = None
    file_size_bytes: int
    element_count: int = 0
    elements_with_geometry: int = 0
    storeys: list[str] = Field(default_factory=list)
    ifc_classes: dict[str, int] = Field(default_factory=dict)
    total_kgco2e: float | None = None
    gross_floor_area_m2: float | None = None
    intensity_kgco2e_m2: float | None = None
    length_unit: str | None = None
    parse_seconds: float | None = None
    is_sample: bool = False
