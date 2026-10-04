from __future__ import annotations

import ifcopenshell
import numpy as np
import pytest

from app.ifc.geometry import ElementMesh, tessellate
from app.ifc.glb import build_glb, read_glb_json
from app.ifc.parse import parse_ifc


def by_name(parsed, name):
    return next(e for e in parsed.elements if e.name == name)


def test_sample_parses_with_expected_structure(parsed):
    assert parsed.schema_version == "IFC4"
    assert parsed.length_unit == "mm"
    assert parsed.storeys == ["Level 0", "Level 1", "Level 2"]
    assert len(parsed.elements) == 149
    assert {"IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcWindow", "IfcCurtainWall", "IfcPlate"} <= set(
        parsed.ifc_classes
    )


@pytest.mark.parametrize(
    ("length_unit", "volume_unit"), [("METERS", "METERS"), ("MILLIMETERS", "METERS"), ("MILLIMETERS", "MILLIMETERS")]
)
def test_volumes_are_in_cubic_metres_whatever_the_units(tmp_path, box_model, length_unit, volume_unit):
    # Revit and ArchiCAD write millimetre lengths with cubic-metre volumes; v0.1 cubed the length scale.
    with_qto = parse_ifc(box_model(tmp_path / "q.ifc", length_unit, volume_unit, with_quantities=True))
    wall = by_name(with_qto, "Wall")
    assert wall.volume_source == "quantity"
    assert wall.volume_m3 == pytest.approx(1.0, rel=1e-6)

    from_geometry = parse_ifc(box_model(tmp_path / "g.ifc", length_unit, volume_unit, with_quantities=False))
    wall = by_name(from_geometry, "Wall")
    assert wall.volume_source == "geometry"
    assert wall.volume_m3 == pytest.approx(1.0, rel=1e-3)
    assert wall.carbon_kgco2e == pytest.approx(1.0 * 2400 * 0.13, rel=1e-3)


def test_floor_area_falls_back_to_slab_geometry(tmp_path, box_model):
    parsed = parse_ifc(box_model(tmp_path / "m.ifc", "MILLIMETERS", "METERS", with_quantities=False))
    assert parsed.floor_area_source == "slab geometry"
    assert parsed.floor_area_m2 == pytest.approx(12.0, rel=1e-3)


def test_floor_area_prefers_spaces(parsed):
    assert parsed.floor_area_source == "spaces"
    assert parsed.floor_area_m2 == pytest.approx(3 * 24 * 14)
    assert parsed.carbon.intensity_kgco2e_m2 == pytest.approx(parsed.carbon.total_kgco2e / (3 * 24 * 14), abs=0.1)


def test_layered_wall_is_split_by_thickness(parsed):
    wall = by_name(parsed, "South wall L1")
    assert wall.volume_source == "quantity"
    assert [layer.category for layer in wall.layers] == ["masonry", "insulation", "concrete", "gypsum"]
    assert [layer.thickness_m for layer in wall.layers] == [0.1, 0.15, 0.2, 0.015]
    assert sum(layer.fraction for layer in wall.layers) == pytest.approx(1.0, abs=1e-3)
    assert sum(layer.volume_m3 for layer in wall.layers) == pytest.approx(wall.volume_m3, rel=1e-3)
    assert wall.carbon_kgco2e == pytest.approx(sum(layer.carbon_kgco2e for layer in wall.layers), rel=1e-3)
    assert wall.material_category == "concrete"  # the thickest classified layer


def test_constituents_use_their_fractions(parsed):
    window = by_name(parsed, "Window S1 L1")
    assert [(layer.material, layer.fraction) for layer in window.layers] == [
        ("Aluminium frame", 0.3),
        ("Triple glazing unit", 0.7),
    ]
    assert window.layers[0].volume_m3 == pytest.approx(0.3 * window.volume_m3, rel=1e-2)


def test_steel_profiles_use_geometry_volume(parsed):
    column = by_name(parsed, "Column A1 L0")
    assert column.volume_source == "geometry"
    # HEB 300 has a section of about 149 cm2; the column is 3.3 m tall.
    assert column.volume_m3 == pytest.approx(0.0149 * 3.3, rel=0.03)
    assert column.material_category == "steel"


def test_assemblies_carry_no_carbon_of_their_own(parsed):
    curtain_wall = by_name(parsed, "Entrance curtain wall L0")
    assert curtain_wall.is_assembly
    assert curtain_wall.carbon_kgco2e is None
    mullion = by_name(parsed, "Mullion M1")
    assert mullion.storey == "Level 0"  # found through the aggregate
    assert mullion.carbon_kgco2e and mullion.carbon_kgco2e > 0
    assert parsed.extras[mullion.global_id].parent_global_id == curtain_wall.global_id
    assert parsed.carbon.assembly_elements == 3  # curtain wall, stair, roof


def test_unknown_material_is_reported_not_guessed(parsed):
    ceiling = by_name(parsed, "Acoustic ceiling L0")
    assert ceiling.material_category is None
    assert ceiling.carbon_kgco2e is None
    assert parsed.carbon.unclassified_elements == 3


def test_geometry_volume_matches_analytic_box(parsed, sample_path):
    meshes = tessellate(ifcopenshell.open(str(sample_path)))
    slab = by_name(parsed, "Floor slab L0")
    assert meshes[slab.express_id].volume_m3 == pytest.approx(24.0 * 14.0 * 0.35, rel=1e-3)
    assert meshes[slab.express_id].top_area_m2 == pytest.approx(24.0 * 14.0, rel=1e-3)


def test_element_extras_include_psets(parsed):
    wall = by_name(parsed, "South wall L1")
    extras = parsed.extras[wall.global_id]
    assert extras.property_sets["Pset_WallCommon"]["FireRating"] == "REI 60"
    assert "Qto_WallBaseQuantities" in extras.quantity_sets


def test_carbon_summary_adds_up(parsed):
    counted = [e for e in parsed.elements if not e.is_assembly]
    assert parsed.carbon.total_kgco2e == pytest.approx(sum(e.carbon_kgco2e or 0 for e in counted), abs=0.5)
    assert sum(b.carbon_kgco2e for b in parsed.carbon.by_material_category) == pytest.approx(
        parsed.carbon.total_kgco2e, abs=1.0
    )
    assert sum(b.element_count for b in parsed.carbon.by_storey) == len(counted)


def test_glb_is_well_formed(parsed):
    doc = read_glb_json(parsed.glb)
    assert doc["asset"]["version"] == "2.0"
    assert len(doc["nodes"]) == sum(1 for e in parsed.elements if e.has_geometry)
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
