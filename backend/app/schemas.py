"""Pydantic schemas shared by the parser, the store and the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModelStatus = Literal["processing", "ready", "failed"]
VolumeSource = Literal["quantity", "geometry"]


class ElementSummary(BaseModel):
    express_id: int
    global_id: str
    ifc_class: str
    name: str | None = None
    type_name: str | None = None
    storey: str | None = None
    materials: list[str] = Field(default_factory=list)
    material_category: str | None = None
    volume_m3: float | None = None
    volume_source: VolumeSource | None = None
    mass_kg: float | None = None
    carbon_kgco2e: float | None = None
    has_geometry: bool = False


class ElementDetail(ElementSummary):
    description: str | None = None
    object_type: str | None = None
    predefined_type: str | None = None
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
    missing_volume_elements: int
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
    parse_seconds: float | None = None
    is_sample: bool = False
