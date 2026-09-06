"""A minimal, dependency-free glTF 2.0 binary (GLB) writer.

One node + one mesh per IFC element, so the viewer can pick elements by name
(GlobalId) and recolour them individually. Geometry is written non-indexed with
flat per-face normals, which is what you want for the sharp edges of building
elements and avoids smoothing artefacts from welded vertices.

Coordinates are converted from IFC (Z up) to glTF (Y up): (x, y, z) -> (x, z, -y).
"""

from __future__ import annotations

import json
import struct
from collections.abc import Iterable

import numpy as np

from app.ifc.geometry import ElementMesh

GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
FLOAT = 5126
ARRAY_BUFFER = 34962


def _pad4(data: bytes, pad_byte: bytes) -> bytes:
    remainder = len(data) % 4
    return data if remainder == 0 else data + pad_byte * (4 - remainder)


def _ifc_to_gltf(vertices: np.ndarray) -> np.ndarray:
    out = np.empty_like(vertices)
    out[:, 0] = vertices[:, 0]
    out[:, 1] = vertices[:, 2]
    out[:, 2] = -vertices[:, 1]
    return out


def _flat_triangles(mesh: ElementMesh) -> tuple[np.ndarray, np.ndarray]:
    """Expand an indexed mesh into non-indexed triangles with per-face normals."""
    tri = mesh.vertices[mesh.faces.reshape(-1)].astype(np.float32).reshape(-1, 3, 3)
    edge1 = tri[:, 1] - tri[:, 0]
    edge2 = tri[:, 2] - tri[:, 0]
    normals = np.cross(edge1, edge2)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals = (normals / lengths).astype(np.float32)
    positions = tri.reshape(-1, 3)
    normals = np.repeat(normals, 3, axis=0)
    return _ifc_to_gltf(positions), _ifc_to_gltf(normals)


def build_glb(meshes: Iterable[ElementMesh]) -> bytes:
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    materials: list[dict] = []
    material_lookup: dict[tuple[float, float, float, float], int] = {}
    gltf_meshes: list[dict] = []
    nodes: list[dict] = []
    binary = bytearray()

    def add_view(array: np.ndarray) -> int:
        data = _pad4(array.astype(np.float32).tobytes(), b"\x00")
        buffer_views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data), "target": ARRAY_BUFFER})
        binary.extend(data)
        return len(buffer_views) - 1

    def add_accessor(array: np.ndarray, with_bounds: bool) -> int:
        accessor = {
            "bufferView": add_view(array),
            "componentType": FLOAT,
            "count": int(array.shape[0]),
            "type": "VEC3",
        }
        if with_bounds:
            accessor["min"] = [float(v) for v in array.min(axis=0)]
            accessor["max"] = [float(v) for v in array.max(axis=0)]
        accessors.append(accessor)
        return len(accessors) - 1

    def material_for(color: tuple[float, float, float, float]) -> int:
        key = tuple(round(c, 3) for c in color)
        if key not in material_lookup:
            rgba = [float(c) for c in key]
            material = {
                "pbrMetallicRoughness": {"baseColorFactor": rgba, "metallicFactor": 0.0, "roughnessFactor": 0.85},
                "doubleSided": True,
            }
            if rgba[3] < 0.999:
                material["alphaMode"] = "BLEND"
            materials.append(material)
            material_lookup[key] = len(materials) - 1
        return material_lookup[key]

    for mesh in meshes:
        positions, normals = _flat_triangles(mesh)
        gltf_meshes.append(
            {
                "name": mesh.global_id,
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": add_accessor(positions, with_bounds=True),
                            "NORMAL": add_accessor(normals, with_bounds=False),
                        },
                        "material": material_for(mesh.color),
                        "mode": 4,
                    }
                ],
            }
        )
        nodes.append(
            {
                "name": mesh.global_id,
                "mesh": len(gltf_meshes) - 1,
                "extras": {"expressId": mesh.express_id, "ifcClass": mesh.ifc_class},
            }
        )

    document = {
        "asset": {"version": "2.0", "generator": "ifc-carbon-viewer"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": gltf_meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary)}],
    }
    json_chunk = _pad4(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = _pad4(bytes(binary), b"\x00")
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return b"".join(
        [
            struct.pack("<III", GLB_MAGIC, GLB_VERSION, total),
            struct.pack("<II", len(json_chunk), CHUNK_JSON),
            json_chunk,
            struct.pack("<II", len(bin_chunk), CHUNK_BIN),
            bin_chunk,
        ]
    )


def read_glb_json(data: bytes) -> dict:
    """Parse the JSON chunk of a GLB (used by tests and the CLI to validate output)."""
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or version != GLB_VERSION or length != len(data):
        raise ValueError("not a valid GLB container")
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != CHUNK_JSON:
        raise ValueError("first GLB chunk must be JSON")
    return json.loads(data[20 : 20 + chunk_length].decode("utf-8"))
