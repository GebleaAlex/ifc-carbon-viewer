from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import numpy as np
import pytest

from app.ifc.parse import ParsedModel, parse_ifc

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample-building.ifc"


@pytest.fixture(scope="session")
def sample_path() -> Path:
    assert SAMPLE.exists(), "run `python scripts/make_sample.py` first"
    return SAMPLE


@pytest.fixture(scope="session")
def parsed(sample_path: Path) -> ParsedModel:
    return parse_ifc(sample_path)


def _build_box_model(path: Path, length_unit: str, volume_unit: str, with_quantities: bool) -> Path:
    """A 2 m x 1 m x 0.5 m concrete wall and a 4 m x 3 m x 0.2 m slab in the given units.

    Dimensions are passed in metres; ifcopenshell.api converts them to the file's length unit,
    exactly like an authoring tool writing millimetres would.
    """
    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Units")
    ifcopenshell.api.unit.assign_unit(
        f,
        length={"is_metric": True, "raw": length_unit},
        area={"is_metric": True, "raw": "METERS"},
        volume={"is_metric": True, "raw": volume_unit},
    )
    model = ifcopenshell.api.context.add_context(f, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )
    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="L0")
    ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(f, products=[storey], relating_object=building)
    concrete = ifcopenshell.api.material.add_material(f, name="Concrete C30/37")

    wall = ifcopenshell.api.root.create_entity(f, ifc_class="IfcWall", name="Wall")
    rep = ifcopenshell.api.geometry.add_wall_representation(f, context=body, length=2.0, height=1.0, thickness=0.5)
    ifcopenshell.api.geometry.assign_representation(f, product=wall, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(f, product=wall, matrix=np.eye(4))
    ifcopenshell.api.spatial.assign_container(f, products=[wall], relating_structure=storey)
    ifcopenshell.api.material.assign_material(f, products=[wall], material=concrete)

    slab = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSlab", name="Slab", predefined_type="FLOOR")
    rep = ifcopenshell.api.geometry.add_slab_representation(
        f, context=body, depth=0.2, polyline=[(0, 0), (4, 0), (4, 3), (0, 3), (0, 0)]
    )
    ifcopenshell.api.geometry.assign_representation(f, product=slab, representation=rep)
    placement = np.eye(4)
    placement[0, 3] = 5.0
    ifcopenshell.api.geometry.edit_object_placement(f, product=slab, matrix=placement)
    ifcopenshell.api.spatial.assign_container(f, products=[slab], relating_structure=storey)
    ifcopenshell.api.material.assign_material(f, products=[slab], material=concrete)

    if with_quantities:
        scale = {"METERS": 1.0, "MILLIMETERS": 1e-3}[volume_unit] ** 3
        qto = ifcopenshell.api.pset.add_qto(f, product=wall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.pset.edit_qto(f, qto=qto, properties={"NetVolume": 1.0 / scale})
    f.write(str(path))
    return path


@pytest.fixture()
def box_model():
    """Factory fixture: ``box_model(path, length_unit, volume_unit, with_quantities)`` writes a small IFC."""
    return _build_box_model
