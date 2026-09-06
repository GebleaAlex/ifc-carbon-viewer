"""Generate a small two-storey sample building as IFC4 using ifcopenshell.api.

The file is deliberately simple but structurally honest: it has a spatial tree
(project > site > building > storeys), walls, slabs, columns, a roof slab,
materials, and base quantities, so the parser and the carbon estimator have
something realistic to work on without shipping a third-party IFC file.

Run: python scripts/make_sample.py samples/sample-building.ifc
"""

from __future__ import annotations

import sys
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

FOOTPRINT_X = 12.0
FOOTPRINT_Y = 8.0
STOREY_HEIGHT = 3.2
SLAB_THICKNESS = 0.25
WALL_THICKNESS = 0.3
COLUMN_SIZE = 0.4
STEEL_SECTION_FILL = 0.15  # an open steel section is ~15% solid over its bounding box


def placement(x: float = 0.0, y: float = 0.0, z: float = 0.0, rotation_deg: float = 0.0) -> np.ndarray:
    m = np.eye(4)
    if rotation_deg:
        a = np.deg2rad(rotation_deg)
        m[0, 0], m[0, 1] = np.cos(a), -np.sin(a)
        m[1, 0], m[1, 1] = np.sin(a), np.cos(a)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def build(path: Path) -> None:
    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Sample Office")
    # Explicit SI base units so quantities in this script (metres) match the file's units.
    ifcopenshell.api.unit.assign_unit(
        f,
        length={"is_metric": True, "raw": "METERS"},
        area={"is_metric": True, "raw": "METERS"},
        volume={"is_metric": True, "raw": "METERS"},
    )
    model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Block A")
    ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)

    materials = {
        "concrete": ifcopenshell.api.material.add_material(f, name="Concrete C30/37", category="concrete"),
        "brick": ifcopenshell.api.material.add_material(f, name="Clay brick masonry", category="masonry"),
        "steel": ifcopenshell.api.material.add_material(f, name="Structural steel S355", category="steel"),
        "timber": ifcopenshell.api.material.add_material(f, name="CLT timber panel", category="wood"),
        "glass": ifcopenshell.api.material.add_material(f, name="Double glazing unit", category="glass"),
    }

    def add_element(ifc_class, name, rep, matrix, storey, material, qto_name, quantities):
        el = ifcopenshell.api.root.create_entity(f, ifc_class=ifc_class, name=name)
        ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(f, product=el, matrix=matrix)
        ifcopenshell.api.spatial.assign_container(f, products=[el], relating_structure=storey)
        ifcopenshell.api.material.assign_material(f, products=[el], material=materials[material])
        qto = ifcopenshell.api.pset.add_qto(f, product=el, name=qto_name)
        ifcopenshell.api.pset.edit_qto(f, qto=qto, properties=quantities)
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name="Pset_Sample")
        ifcopenshell.api.pset.edit_pset(
            f, pset=pset, properties={"MaterialCategory": material, "IsExternal": True, "FireRating": "REI 60"}
        )
        return el

    slab_polyline = [(0, 0), (FOOTPRINT_X, 0), (FOOTPRINT_X, FOOTPRINT_Y), (0, FOOTPRINT_Y), (0, 0)]
    storeys = []
    for level in range(2):
        z = level * STOREY_HEIGHT
        storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=f"Level {level}")
        ifcopenshell.api.geometry.edit_object_placement(f, product=storey, matrix=placement(z=z))
        ifcopenshell.api.aggregate.assign_object(f, products=[storey], relating_object=building)
        storeys.append(storey)

        # Floor slab: concrete on level 0, CLT on level 1 to get a material mix
        slab_rep = ifcopenshell.api.geometry.add_slab_representation(
            f, context=body, depth=SLAB_THICKNESS, polyline=slab_polyline
        )
        add_element(
            "IfcSlab",
            f"Floor slab L{level}",
            slab_rep,
            placement(z=z - SLAB_THICKNESS),
            storey,
            "concrete" if level == 0 else "timber",
            "Qto_SlabBaseQuantities",
            {
                "NetVolume": FOOTPRINT_X * FOOTPRINT_Y * SLAB_THICKNESS,
                "NetArea": FOOTPRINT_X * FOOTPRINT_Y,
                "Width": SLAB_THICKNESS,
            },
        )

        # Four perimeter walls; the south wall on level 1 is a glazed curtain wall
        wall_h = STOREY_HEIGHT - SLAB_THICKNESS
        walls = [
            ("South wall", FOOTPRINT_X, placement(0, 0, z), "glass" if level == 1 else "brick"),
            ("North wall", FOOTPRINT_X, placement(0, FOOTPRINT_Y - WALL_THICKNESS, z), "brick"),
            ("West wall", FOOTPRINT_Y, placement(WALL_THICKNESS, 0, z, 90), "brick"),
            ("East wall", FOOTPRINT_Y, placement(FOOTPRINT_X, 0, z, 90), "brick"),
        ]
        for name, length, matrix, mat in walls:
            thickness = 0.05 if mat == "glass" else WALL_THICKNESS
            rep = ifcopenshell.api.geometry.add_wall_representation(
                f, context=body, length=length, height=wall_h, thickness=thickness
            )
            add_element(
                "IfcCurtainWall" if mat == "glass" else "IfcWall",
                f"{name} L{level}",
                rep,
                matrix,
                storey,
                mat,
                "Qto_WallBaseQuantities",
                {"NetVolume": length * wall_h * thickness, "NetSideArea": length * wall_h, "Height": wall_h},
            )

        # Steel columns on a 4 m grid
        profile = f.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            ProfileName="HEB 400",
            XDim=COLUMN_SIZE,
            YDim=COLUMN_SIZE,
        )
        for i, x in enumerate((4.0, 8.0)):
            for j, y in enumerate((2.5, 5.5)):
                rep = ifcopenshell.api.geometry.add_profile_representation(
                    f, context=body, profile=profile, depth=wall_h
                )
                add_element(
                    "IfcColumn",
                    f"Column {chr(65 + i)}{j + 1} L{level}",
                    rep,
                    placement(x, y, z),
                    storey,
                    "steel",
                    "Qto_ColumnBaseQuantities",
                    {"NetVolume": COLUMN_SIZE * COLUMN_SIZE * wall_h * STEEL_SECTION_FILL, "Length": wall_h},
                )

    # Roof slab on top of the upper storey
    roof_rep = ifcopenshell.api.geometry.add_slab_representation(
        f, context=body, depth=SLAB_THICKNESS, polyline=slab_polyline
    )
    add_element(
        "IfcRoof",
        "Roof slab",
        roof_rep,
        placement(z=2 * STOREY_HEIGHT - SLAB_THICKNESS),
        storeys[-1],
        "timber",
        "Qto_SlabBaseQuantities",
        {"NetVolume": FOOTPRINT_X * FOOTPRINT_Y * SLAB_THICKNESS, "NetArea": FOOTPRINT_X * FOOTPRINT_Y},
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(path))
    print(f"wrote {path} ({path.stat().st_size / 1024:.1f} KiB, {len(f.by_type('IfcElement'))} elements)")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample-building.ifc"))
