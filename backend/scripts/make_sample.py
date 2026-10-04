"""Generate a three-storey sample office as IFC4 using ifcopenshell.api.

The file is written the way common authoring tools export: lengths in millimetres, areas
and volumes in square and cubic metres. It is small but structurally honest, so the parser
and the estimator have realistic cases to handle without shipping a third-party IFC file:

- layered external walls and slabs (IfcMaterialLayerSetUsage) with windows in real openings,
- windows and a door with frame/glazing constituents (IfcMaterialConstituentSet),
- steel I-section columns and beams with profile sets and no volume quantities (geometry volume),
- a curtain wall, a stair and a roof that are assemblies of plates, members, flights and slabs,
- spaces with floor-area quantities (for the kgCO2e/m2 intensity),
- one deliberately unknown material, so the mapping panel has something to do.

Run: python scripts/make_sample.py samples/sample-building.ifc
"""

from __future__ import annotations

import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import numpy as np

# Dimensions in metres; the API converts them to the file's millimetres.
LENGTH_X = 24.0
LENGTH_Y = 14.0
STOREYS = 3
STOREY_HEIGHT = 3.6
WALL_LAYERS = [
    ("Clay brick facing", 0.10),
    ("Mineral wool", 0.15),
    ("Reinforced concrete C30/37", 0.20),
    ("Gypsum plaster", 0.015),
]
WALL_T = sum(t for _, t in WALL_LAYERS)
PARTITION_LAYERS = [("Plasterboard", 0.0125), ("Mineral wool", 0.075), ("Plasterboard", 0.0125)]
FLOOR_LAYERS = {
    0: [("Reinforced concrete C30/37", 0.30), ("Cement screed", 0.05)],
    1: [("Precast concrete hollow-core", 0.25), ("Cement screed", 0.05)],
    2: [("CLT floor panel", 0.20), ("Cement screed", 0.05)],
}
ROOF_LAYERS = [
    ("CLT roof panel", 0.20),
    ("PIR insulation board", 0.20),
    ("EPDM membrane", 0.003),
    ("Gravel ballast", 0.05),
]
WINDOW_W, WINDOW_H, SILL = 1.8, 1.6, 0.9
GRID_X = (6.0, 12.0, 18.0)
GRID_Y = (4.7, 9.4)
MM = 1000.0


def matrix(x: float = 0.0, y: float = 0.0, z: float = 0.0, rotation_deg: float = 0.0, axes=None) -> np.ndarray:
    m = np.eye(4)
    if axes is not None:
        m[:3, :3] = np.array(axes, dtype=float).T  # columns are the images of local X, Y, Z
    elif rotation_deg:
        a = np.deg2rad(rotation_deg)
        m[0, 0], m[0, 1] = np.cos(a), -np.sin(a)
        m[1, 0], m[1, 1] = np.sin(a), np.cos(a)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


class Builder:
    def __init__(self) -> None:
        f = self.f = ifcopenshell.api.project.create_file(version="IFC4")
        self.project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Sample Office")
        ifcopenshell.api.unit.assign_unit(
            f,
            length={"is_metric": True, "raw": "MILLIMETERS"},
            area={"is_metric": True, "raw": "METERS"},
            volume={"is_metric": True, "raw": "METERS"},
        )
        model = ifcopenshell.api.context.add_context(f, context_type="Model")
        self.body = ifcopenshell.api.context.add_context(
            f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
        )
        self.site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Site")
        self.building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Block A")
        ifcopenshell.api.aggregate.assign_object(f, products=[self.site], relating_object=self.project)
        ifcopenshell.api.aggregate.assign_object(f, products=[self.building], relating_object=self.site)
        self.materials: dict[str, ifcopenshell.entity_instance] = {}
        self.layer_sets: dict[str, ifcopenshell.entity_instance] = {}

    # -- materials -------------------------------------------------------------------------------

    CATEGORIES = {
        "Reinforced concrete C30/37": "concrete",
        "Structural steel S355": "steel",
        "CLT floor panel": "wood",
        "CLT roof panel": "wood",
        "Clay brick facing": "masonry",
    }

    def material(self, name: str):
        if name not in self.materials:
            self.materials[name] = ifcopenshell.api.material.add_material(
                self.f, name=name, category=self.CATEGORIES.get(name)
            )
        return self.materials[name]

    def layer_set(self, name: str, layers: list[tuple[str, float]]):
        if name not in self.layer_sets:
            layer_set = ifcopenshell.api.material.add_material_set(self.f, name=name, set_type="IfcMaterialLayerSet")
            for material, thickness in layers:
                layer = ifcopenshell.api.material.add_layer(
                    self.f, layer_set=layer_set, material=self.material(material)
                )
                ifcopenshell.api.material.edit_layer(self.f, layer=layer, attributes={"LayerThickness": thickness * MM})
            self.layer_sets[name] = layer_set
        return self.layer_sets[name]

    def constituents(self, name: str, parts: list[tuple[str, float]]):
        cset = ifcopenshell.api.material.add_material_set(self.f, name=name, set_type="IfcMaterialConstituentSet")
        for material, fraction in parts:
            c = ifcopenshell.api.material.add_constituent(
                self.f, constituent_set=cset, material=self.material(material)
            )
            c.Fraction = fraction
        return cset

    # -- elements --------------------------------------------------------------------------------

    def element(self, ifc_class, name, rep, placement, container=None, predefined_type=None):
        el = ifcopenshell.api.root.create_entity(
            self.f, ifc_class=ifc_class, name=name, predefined_type=predefined_type
        )
        if rep is not None:
            ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(self.f, product=el, matrix=placement)
        if container is not None:
            ifcopenshell.api.spatial.assign_container(self.f, products=[el], relating_structure=container)
        return el

    def qto(self, el, name: str, values: dict) -> None:
        qto = ifcopenshell.api.pset.add_qto(self.f, product=el, name=name)
        ifcopenshell.api.pset.edit_qto(self.f, qto=qto, properties=values)

    def pset(self, el, name: str, values: dict) -> None:
        pset = ifcopenshell.api.pset.add_pset(self.f, product=el, name=name)
        ifcopenshell.api.pset.edit_pset(self.f, pset=pset, properties=values)

    def aggregate(self, parts, whole) -> None:
        ifcopenshell.api.aggregate.assign_object(self.f, products=parts, relating_object=whole)


def wall_point(origin: tuple[float, float], rotation_deg: float, along: float, across: float) -> tuple[float, float]:
    a = np.deg2rad(rotation_deg)
    return (
        origin[0] + along * np.cos(a) - across * np.sin(a),
        origin[1] + along * np.sin(a) + across * np.cos(a),
    )


def build(path: Path) -> None:
    b = Builder()
    f = b.f
    footprint = [(0, 0), (LENGTH_X, 0), (LENGTH_X, LENGTH_Y), (0, LENGTH_Y), (0, 0)]
    heb = f.create_entity(
        "IfcIShapeProfileDef",
        ProfileType="AREA",
        ProfileName="HEB 300",
        OverallWidth=300.0,
        OverallDepth=300.0,
        WebThickness=11.0,
        FlangeThickness=19.0,
        FilletRadius=27.0,
    )
    ipe = f.create_entity(
        "IfcIShapeProfileDef",
        ProfileType="AREA",
        ProfileName="IPE 400",
        OverallWidth=180.0,
        OverallDepth=400.0,
        WebThickness=8.6,
        FlangeThickness=13.5,
        FilletRadius=21.0,
    )
    steel_profiles = {}
    for profile in (heb, ipe):
        pset = ifcopenshell.api.material.add_material_set(f, name=profile.ProfileName, set_type="IfcMaterialProfileSet")
        ifcopenshell.api.material.add_profile(
            f, profile_set=pset, material=b.material("Structural steel S355"), profile=profile
        )
        steel_profiles[profile.ProfileName] = pset

    storeys = []
    for level in range(STOREYS):
        z = level * STOREY_HEIGHT
        storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=f"Level {level}")
        ifcopenshell.api.geometry.edit_object_placement(f, product=storey, matrix=matrix(z=z))
        storey.Elevation = z * MM
        ifcopenshell.api.aggregate.assign_object(f, products=[storey], relating_object=b.building)
        storeys.append(storey)

        # -- floor slab -------------------------------------------------------------------------
        layers = FLOOR_LAYERS[level]
        depth = sum(t for _, t in layers)
        slab = b.element(
            "IfcSlab",
            f"Floor slab L{level}",
            ifcopenshell.api.geometry.add_slab_representation(f, context=b.body, depth=depth, polyline=footprint),
            matrix(z=z - depth),
            storey,
            predefined_type="BASESLAB" if level == 0 else "FLOOR",
        )
        ifcopenshell.api.material.assign_material(
            f, products=[slab], type="IfcMaterialLayerSetUsage", material=b.layer_set(f"Floor L{level}", layers)
        )
        b.qto(
            slab,
            "Qto_SlabBaseQuantities",
            {"NetVolume": LENGTH_X * LENGTH_Y * depth, "GrossArea": LENGTH_X * LENGTH_Y, "Depth": depth * MM},
        )
        b.pset(slab, "Pset_SlabCommon", {"IsExternal": level == 0, "LoadBearing": True, "FireRating": "REI 90"})

        # -- spaces carry the floor area --------------------------------------------------------
        space = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSpace", name=f"Open office L{level}")
        ifcopenshell.api.aggregate.assign_object(f, products=[space], relating_object=storey)
        b.qto(
            space,
            "Qto_SpaceBaseQuantities",
            {"GrossFloorArea": LENGTH_X * LENGTH_Y, "NetFloorArea": (LENGTH_X - 2 * WALL_T) * (LENGTH_Y - 2 * WALL_T)},
        )

        # -- external walls with windows --------------------------------------------------------
        if level + 1 < STOREYS:
            next_bottom = (level + 1) * STOREY_HEIGHT - sum(t for _, t in FLOOR_LAYERS[level + 1])
        else:
            next_bottom = STOREYS * STOREY_HEIGHT - 0.05
        wall_h = next_bottom - z
        walls = [
            ("South", LENGTH_X, (0.0, 0.0), 0.0),
            ("North", LENGTH_X, (LENGTH_X, LENGTH_Y), 180.0),
            ("West", LENGTH_Y, (0.0, LENGTH_Y), 270.0),
            ("East", LENGTH_Y, (LENGTH_X, 0.0), 90.0),
        ]
        for side, length, origin, rot in walls:
            if side == "South" and level == 0:
                build_curtain_wall(b, storey, length, wall_h)
                continue
            rep = ifcopenshell.api.geometry.add_wall_representation(
                f, context=b.body, length=length, height=wall_h, thickness=WALL_T
            )
            wall = b.element("IfcWall", f"{side} wall L{level}", rep, matrix(*origin, z, rot), storey)
            ifcopenshell.api.material.assign_material(
                f, products=[wall], type="IfcMaterialLayerSetUsage", material=b.layer_set("External wall", WALL_LAYERS)
            )
            positions = [s + 0.6 for s in np.arange(1.5, length - WINDOW_W - 0.5, 3.0)]
            if side == "North" and level == 0:
                door_at = length / 2 - 0.6
                positions = [p for p in positions if abs(p - door_at) > WINDOW_W + 0.4]
                add_filled_opening(
                    b, wall, storey, origin, rot, z, door_at, 1.2, 2.2, 0.0, "door", f"Entrance door L{level}"
                )
            for i, s in enumerate(positions):
                add_filled_opening(
                    b,
                    wall,
                    storey,
                    origin,
                    rot,
                    z,
                    s,
                    WINDOW_W,
                    WINDOW_H,
                    SILL,
                    "window",
                    f"Window {side[0]}{i + 1} L{level}",
                )
            openings = len(positions) * WINDOW_W * WINDOW_H + (1.2 * 2.2 if side == "North" and level == 0 else 0)
            b.qto(
                wall,
                "Qto_WallBaseQuantities",
                {
                    "Length": length * MM,
                    "Height": wall_h * MM,
                    "Width": WALL_T * MM,
                    "GrossVolume": length * wall_h * WALL_T,
                    "NetVolume": (length * wall_h - openings) * WALL_T,
                    "NetSideArea": length * wall_h - openings,
                },
            )
            b.pset(
                wall,
                "Pset_WallCommon",
                {"IsExternal": True, "LoadBearing": True, "FireRating": "REI 60", "ThermalTransmittance": 0.21},
            )

        # -- partitions ---------------------------------------------------------------------------
        for i, x in enumerate((8.0, 16.0)):
            t = sum(t for _, t in PARTITION_LAYERS)
            rep = ifcopenshell.api.geometry.add_wall_representation(
                f, context=b.body, length=4.0, height=wall_h, thickness=t
            )
            wall = b.element(
                "IfcWall",
                f"Partition P{i + 1} L{level}",
                rep,
                matrix(x, LENGTH_Y - WALL_T - 4.0, z, 90),
                storey,
                predefined_type="PARTITIONING",
            )
            ifcopenshell.api.material.assign_material(
                f,
                products=[wall],
                type="IfcMaterialLayerSetUsage",
                material=b.layer_set("Drywall partition", PARTITION_LAYERS),
            )
            b.qto(
                wall, "Qto_WallBaseQuantities", {"NetVolume": 4.0 * wall_h * t, "Length": 4000.0, "Height": wall_h * MM}
            )
            b.pset(wall, "Pset_WallCommon", {"IsExternal": False, "LoadBearing": False, "AcousticRating": "Rw 52 dB"})

        # -- steel frame: columns everywhere, beams under the slab above ---------------------------
        col_h = wall_h
        for i, x in enumerate(GRID_X):
            for j, y in enumerate(GRID_Y):
                rep = ifcopenshell.api.geometry.add_profile_representation(f, context=b.body, profile=heb, depth=col_h)
                col = b.element("IfcColumn", f"Column {chr(65 + i)}{j + 1} L{level}", rep, matrix(x, y, z), storey)
                ifcopenshell.api.material.assign_material(
                    f, products=[col], type="IfcMaterialProfileSet", material=steel_profiles["HEB 300"]
                )
                b.pset(col, "Pset_ColumnCommon", {"LoadBearing": True, "FireRating": "R 90"})
        if level < STOREYS - 1:
            beam_z = next_bottom - 0.4
            for j, y in enumerate(GRID_Y):
                rep = ifcopenshell.api.geometry.add_profile_representation(
                    f, context=b.body, profile=ipe, depth=LENGTH_X - 2 * WALL_T
                )
                beam = b.element(
                    "IfcBeam",
                    f"Beam B{j + 1} L{level}",
                    rep,
                    matrix(WALL_T, y, beam_z + 0.2, axes=[(0, 1, 0), (0, 0, 1), (1, 0, 0)]),
                    storey,
                )
                ifcopenshell.api.material.assign_material(
                    f, products=[beam], type="IfcMaterialProfileSet", material=steel_profiles["IPE 400"]
                )

        # -- acoustic ceiling: a material the factor table does not know ---------------------------
        ceiling = b.element(
            "IfcCovering",
            f"Acoustic ceiling L{level}",
            ifcopenshell.api.geometry.add_slab_representation(
                f,
                context=b.body,
                depth=0.04,
                polyline=[(2, 2), (LENGTH_X - 2, 2), (LENGTH_X - 2, 7.5), (2, 7.5), (2, 2)],
            ),
            matrix(z=z + col_h - 0.55),
            storey,
            predefined_type="CEILING",
        )
        ifcopenshell.api.material.assign_material(
            f, products=[ceiling], material=b.material("Sto Silent acoustic panel")
        )

        if level == 0:
            build_stair(b, storey)

    # -- roof: an IfcRoof assembly with one layered roof slab ---------------------------------------
    top = storeys[-1]
    roof_z = STOREYS * STOREY_HEIGHT - 0.05
    depth = sum(t for _, t in ROOF_LAYERS)
    roof = b.element("IfcRoof", "Flat roof", None, matrix(z=roof_z), top, predefined_type="FLAT_ROOF")
    roof_slab = b.element(
        "IfcSlab",
        "Roof slab",
        ifcopenshell.api.geometry.add_slab_representation(f, context=b.body, depth=depth, polyline=footprint),
        matrix(z=roof_z),
        None,
        predefined_type="ROOF",
    )
    b.aggregate([roof_slab], roof)
    ifcopenshell.api.material.assign_material(
        f, products=[roof_slab], type="IfcMaterialLayerSetUsage", material=b.layer_set("Warm roof", ROOF_LAYERS)
    )
    b.qto(
        roof_slab,
        "Qto_SlabBaseQuantities",
        {"NetVolume": LENGTH_X * LENGTH_Y * depth, "GrossArea": LENGTH_X * LENGTH_Y},
    )
    b.pset(roof_slab, "Pset_SlabCommon", {"IsExternal": True, "ThermalTransmittance": 0.13})

    path.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(path))
    print(f"wrote {path} ({path.stat().st_size / 1024:.1f} KiB, {len(f.by_type('IfcElement'))} elements)")


def add_filled_opening(b: Builder, wall, storey, origin, rot, z, along, width, height, sill, kind, name) -> None:
    f = b.f
    ox, oy = wall_point(origin, rot, along, -0.05)
    opening_rep = ifcopenshell.api.geometry.add_wall_representation(
        f, context=b.body, length=width, height=height, thickness=WALL_T + 0.1
    )
    opening = b.element("IfcOpeningElement", f"Opening for {name}", opening_rep, matrix(ox, oy, z + sill, rot))
    ifcopenshell.api.feature.add_feature(f, feature=opening, element=wall)

    fx, fy = wall_point(origin, rot, along, WALL_T * 0.35)
    if kind == "window":
        rep = ifcopenshell.api.geometry.add_window_representation(
            f,
            context=b.body,
            overall_height=height * MM,
            overall_width=width * MM,
        )
        filler = b.element("IfcWindow", name, rep, matrix(fx, fy, z + sill, rot), storey, predefined_type="WINDOW")
        filler.OverallHeight, filler.OverallWidth = height * MM, width * MM
        ifcopenshell.api.material.assign_material(
            f,
            products=[filler],
            type="IfcMaterialConstituentSet",
            material=b.constituents("Aluminium window", [("Aluminium frame", 0.3), ("Triple glazing unit", 0.7)]),
        )
        b.pset(
            filler, "Pset_WindowCommon", {"IsExternal": True, "ThermalTransmittance": 0.8, "GlazingAreaFraction": 0.7}
        )
    else:
        rep = ifcopenshell.api.geometry.add_door_representation(
            f, context=b.body, overall_height=height * MM, overall_width=width * MM
        )
        filler = b.element("IfcDoor", name, rep, matrix(fx, fy, z + sill, rot), storey, predefined_type="DOOR")
        filler.OverallHeight, filler.OverallWidth = height * MM, width * MM
        ifcopenshell.api.material.assign_material(
            f,
            products=[filler],
            type="IfcMaterialConstituentSet",
            material=b.constituents("Oak door", [("Oak timber", 0.85), ("Steel hardware", 0.15)]),
        )
        b.pset(filler, "Pset_DoorCommon", {"IsExternal": True, "FireRating": "EI 30"})
    ifcopenshell.api.feature.add_filling(f, opening=opening, element=filler)


def build_curtain_wall(b: Builder, storey, length: float, height: float) -> None:
    """A stick-system curtain wall: aluminium mullions and transoms with glass plates in between."""
    f = b.f
    cw = b.element("IfcCurtainWall", "Entrance curtain wall L0", None, matrix(0, 0, 0), storey)
    parts = []
    mullion = f.create_entity(
        "IfcRectangleProfileDef", ProfileType="AREA", ProfileName="Mullion 60x150", XDim=60.0, YDim=150.0
    )
    bays = int(round(length / 2.0))
    bay = length / bays
    xs = [i * bay for i in range(bays + 1)]
    for i, x in enumerate(xs):
        rep = ifcopenshell.api.geometry.add_profile_representation(f, context=b.body, profile=mullion, depth=height)
        m = b.element(
            "IfcMember",
            f"Mullion M{i + 1}",
            rep,
            matrix(min(max(x, 0.03), length - 0.03), 0.075, 0),
            None,
            predefined_type="MULLION",
        )
        ifcopenshell.api.material.assign_material(f, products=[m], material=b.material("Aluminium extrusion"))
        parts.append(m)
    for k, zt in enumerate((0.03, 1.1, height - 0.03)):
        rep = ifcopenshell.api.geometry.add_profile_representation(f, context=b.body, profile=mullion, depth=length)
        t = b.element(
            "IfcMember",
            f"Transom T{k + 1}",
            rep,
            matrix(0, 0.075, zt, axes=[(0, 0, -1), (0, 1, 0), (1, 0, 0)]),
            None,
            predefined_type="TRANSOM",
        )
        ifcopenshell.api.material.assign_material(f, products=[t], material=b.material("Aluminium extrusion"))
        parts.append(t)
    for i in range(bays):
        for k, (z0, z1) in enumerate(((0.06, 1.07), (1.13, height - 0.06))):
            rep = ifcopenshell.api.geometry.add_wall_representation(
                f, context=b.body, length=bay - 0.06, height=z1 - z0, thickness=0.028
            )
            p = b.element(
                "IfcPlate",
                f"Glass panel {i + 1}.{k + 1}",
                rep,
                matrix(xs[i] + 0.03, 0.061, z0),
                None,
                predefined_type="CURTAIN_PANEL",
            )
            ifcopenshell.api.material.assign_material(f, products=[p], material=b.material("Laminated safety glass"))
            parts.append(p)
    b.aggregate(parts, cw)
    b.pset(cw, "Pset_CurtainWallCommon", {"IsExternal": True, "ThermalTransmittance": 1.1})


def build_stair(b: Builder, storey) -> None:
    """A straight concrete flight from level 0 to level 1, as an IfcStair assembly."""
    f = b.f
    risers, rise, going, width = 20, STOREY_HEIGHT / 20, 0.28, 1.2
    points = [(0.0, 0.0)]
    for i in range(risers):
        points += [(i * going, (i + 1) * rise), ((i + 1) * going, (i + 1) * rise)]
    points += [(risers * going, risers * rise - 0.3), (going, 0.0), (0.0, 0.0)]
    polyline = f.create_entity("IfcPolyline", [f.createIfcCartesianPoint((x * MM, y * MM)) for x, y in points])
    profile = f.create_entity(
        "IfcArbitraryClosedProfileDef", ProfileType="AREA", ProfileName="Flight", OuterCurve=polyline
    )
    stair = b.element(
        "IfcStair",
        "Main stair",
        None,
        matrix(1.0, LENGTH_Y - WALL_T - 0.1, 0),
        storey,
        predefined_type="STRAIGHT_RUN_STAIR",
    )
    rep = ifcopenshell.api.geometry.add_profile_representation(f, context=b.body, profile=profile, depth=width)
    flight = b.element(
        "IfcStairFlight",
        "Flight 1",
        rep,
        matrix(1.0, LENGTH_Y - WALL_T - 0.1, 0, axes=[(1, 0, 0), (0, 0, 1), (0, -1, 0)]),
        None,
        predefined_type="STRAIGHT",
    )
    flight.NumberOfRisers, flight.RiserHeight, flight.TreadLength = risers, rise * MM, going * MM
    ifcopenshell.api.material.assign_material(f, products=[flight], material=b.material("Precast concrete stair"))
    b.aggregate([flight], stair)


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample-building.ifc"))
