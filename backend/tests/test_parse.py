from __future__ import annotations

import ifcopenshell
import numpy as np
import pytest

from app.ifc.geometry import ElementMesh, tessellate
from app.ifc.glb import build_glb, read_glb_json


def test_sample_parses_with_expected_structure(parsed):
    assert parsed.schema_version == "IFC4"
    assert parsed.storeys == ["Level 0", "Level 1"]
    assert len(parsed.elements) == 19
    assert all(e.has_geometry for e in parsed.elements)
    assert set(parsed.ifc_classes) == {"IfcWall", "IfcSlab", "IfcColumn", "IfcCurtainWall", "IfcRoof"}


def test_quantities_are_preferred_over_geometry(parsed):
    wall = next(e for e in parsed.elements if e.name == "South wall L0")
    assert wall.volume_source == "quantity"
    assert wall.volume_m3 == pytest.approx(12.0 * 2.95 * 0.3, rel=1e-3)
    assert wall.material_category == "masonry"
    assert wall.carbon_kgco2e is not None and wall.carbon_kgco2e > 0


def test_geometry_volume_matches_analytic_box(parsed, sample_path):
    # The floor slab is a 12 x 8 x 0.25 box; the mesh volume must agree with the quantity.
    meshes = tessellate(ifcopenshell.open(str(sample_path)))
    slab = next(e for e in parsed.elements if e.name == "Floor slab L0")
    assert meshes[slab.express_id].volume_m3 == pytest.approx(12.0 * 8.0 * 0.25, rel=1e-3)


def test_element_details_include_psets(parsed):
    detail = parsed.details[parsed.elements[0].global_id]
    assert "Pset_Sample" in detail.property_sets
    assert detail.property_sets["Pset_Sample"]["FireRating"] == "REI 60"
    assert any(name.startswith("Qto_") for name in detail.quantity_sets)


def test_carbon_summary_covers_every_element(parsed):
    assert parsed.carbon.estimated_elements == 19
    assert parsed.carbon.unclassified_elements == 0
    assert parsed.carbon.total_kgco2e > 0
    assert sum(b.element_count for b in parsed.carbon.by_storey) == 19


def test_glb_is_well_formed(parsed):
    doc = read_glb_json(parsed.glb)
    assert doc["asset"]["version"] == "2.0"
    assert len(doc["nodes"]) == 19
    node = doc["nodes"][0]
    assert node["name"] == doc["meshes"][node["mesh"]]["name"]
    assert node["extras"]["ifcClass"].startswith("Ifc")
    for accessor in doc["accessors"]:
        assert accessor["componentType"] == 5126
        assert accessor["type"] == "VEC3"
    assert parsed.glb[:4] == b"glTF"


def test_glb_writer_converts_z_up_to_y_up():
    tri = ElementMesh(
        express_id=1,
        global_id="abc",
        ifc_class="IfcWall",
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 2, 0]], dtype=np.float32),
        faces=np.array([[0, 1, 2]], dtype=np.uint32),
        color=(1.0, 0.0, 0.0, 0.5),
    )
    doc = read_glb_json(build_glb([tri]))
    position = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert position["count"] == 3
    assert position["min"] == [0.0, 0.0, -2.0]  # IFC +Y becomes glTF -Z
    assert position["max"] == [1.0, 0.0, 0.0]
    assert doc["materials"][0]["alphaMode"] == "BLEND"
