"""Tessellate IFC products with IfcOpenShell into per-element triangle meshes."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import ifcopenshell
import ifcopenshell.geom
import numpy as np

log = logging.getLogger(__name__)

DEFAULT_COLOR = (0.78, 0.78, 0.78, 1.0)


@dataclass
class ElementMesh:
    express_id: int
    global_id: str
    ifc_class: str
    vertices: np.ndarray  # (n, 3) float32, IFC coordinates (Z up), metres
    faces: np.ndarray  # (m, 3) uint32
    color: tuple[float, float, float, float]  # dominant RGBA of the element

    @property
    def volume_m3(self) -> float:
        """Signed-tetrahedron volume of the closed triangle mesh, in cubic metres."""
        v = self.vertices.astype(np.float64)
        a, b, c = v[self.faces[:, 0]], v[self.faces[:, 1]], v[self.faces[:, 2]]
        return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)

    @property
    def top_area_m2(self) -> float:
        """Plan area of the upward-facing triangles, in square metres (the top of a slab)."""
        v = self.vertices.astype(np.float64)
        a, b, c = v[self.faces[:, 0]], v[self.faces[:, 1]], v[self.faces[:, 2]]
        normals = np.cross(b - a, c - a)
        lengths = np.linalg.norm(normals, axis=1)
        up = (lengths > 0) & (normals[:, 2] > 0.7 * lengths)
        return float(normals[up, 2].sum() / 2.0)

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)


def _style_rgba(style) -> tuple[float, float, float, float]:
    """Read the diffuse colour from an IfcOpenShell style, tolerating API differences between versions."""
    try:
        diffuse = style.diffuse
        rgb = (diffuse.r(), diffuse.g(), diffuse.b()) if callable(getattr(diffuse, "r", None)) else tuple(diffuse)[:3]
        transparency = getattr(style, "transparency", 0.0)
        alpha = 1.0 if transparency is None or transparency != transparency else 1.0 - float(transparency)
        return (float(rgb[0]), float(rgb[1]), float(rgb[2]), max(0.05, min(1.0, alpha)))
    except Exception:  # pragma: no cover - defensive against wrapper changes
        return DEFAULT_COLOR


def _dominant_color(geometry) -> tuple[float, float, float, float]:
    materials = list(geometry.materials)
    if not materials:
        return DEFAULT_COLOR
    material_ids = np.asarray(geometry.material_ids, dtype=np.int64)
    if material_ids.size == 0:
        return _style_rgba(materials[0])
    valid = material_ids[(material_ids >= 0) & (material_ids < len(materials))]
    if valid.size == 0:
        return _style_rgba(materials[0])
    dominant = int(np.bincount(valid).argmax())
    return _style_rgba(materials[dominant])


def make_settings() -> ifcopenshell.geom.settings:
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("weld-vertices", True)
    settings.set("apply-default-materials", True)
    settings.set("disable-opening-subtractions", False)
    return settings


def tessellate(model: ifcopenshell.file, threads: int = 1) -> dict[int, ElementMesh]:
    """Return a mapping express_id -> ElementMesh for every product that has a body representation.

    Spaces and openings are excluded on purpose: they are useful for analysis but only
    clutter a viewer that is about built elements.
    """
    settings = make_settings()
    exclude = {"IfcSpace", "IfcOpeningElement"}
    iterator = ifcopenshell.geom.iterator(settings, model, threads)
    meshes: dict[int, ElementMesh] = {}
    if not iterator.initialize():
        log.warning("geometry iterator produced no shapes")
        return meshes
    while True:
        shape = iterator.get()
        if shape.type not in exclude:
            geometry = shape.geometry
            verts = np.asarray(geometry.verts, dtype=np.float32).reshape(-1, 3)
            faces = np.asarray(geometry.faces, dtype=np.uint32).reshape(-1, 3)
            if len(verts) and len(faces):
                meshes[shape.id] = ElementMesh(
                    express_id=shape.id,
                    global_id=shape.guid,
                    ifc_class=shape.type,
                    vertices=verts,
                    faces=faces,
                    color=_dominant_color(geometry),
                )
        if not iterator.next():
            break
    return meshes
