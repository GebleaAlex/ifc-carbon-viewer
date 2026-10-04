"""File-backed model store.

Each model lives in ``<data_dir>/<id>/`` with the original IFC, a metadata JSON, the estimated
element list, the per-element extras (property and quantity sets), the carbon summary, the
material mapping and the GLB. Keeping everything on disk means the API survives restarts and
stays stateless enough to run in a container. The element lists of recently used models are
cached in memory because every element request needs them.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from app.carbon.estimate import UNCLASSIFIED, apply_estimates, factor_index, material_usage, summarize
from app.ifc.parse import parse_ifc
from app.schemas import (
    CarbonSummary,
    ElementDetail,
    ElementExtras,
    ElementSummary,
    MaterialMapping,
    MaterialUsage,
    ModelSummary,
)

log = logging.getLogger(__name__)

CACHE_SIZE = 4


class MappingError(ValueError):
    """Raised when a material mapping names a category that does not exist."""


class ModelStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._models: dict[str, ModelSummary] = {}
        self._cache: OrderedDict[str, tuple[list[ElementSummary], dict[str, ElementExtras]]] = OrderedDict()
        self.stale: list[str] = []
        self._load_existing()

    # -- persistence -------------------------------------------------------------------

    def _dir(self, model_id: str) -> Path:
        return self.data_dir / model_id

    def _load_existing(self) -> None:
        for meta_path in self.data_dir.glob("*/meta.json"):
            try:
                meta = ModelSummary.model_validate_json(meta_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover
                log.warning("skipping unreadable model %s: %s", meta_path.parent.name, exc)
                continue
            if meta.status == "processing":
                meta.status = "failed"
                meta.error = "server restarted while processing"
                self._write_meta(meta)
            elif meta.status == "ready" and not (meta_path.parent / "extras.json").exists():
                # Parsed by an older version: parse again so the new fields (layers, floor area) exist.
                meta.status = "processing"
                self.stale.append(meta.id)
            self._models[meta.id] = meta

    def _write_meta(self, meta: ModelSummary) -> None:
        (self._dir(meta.id) / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    def _write_elements(self, model_id: str, elements: list[ElementSummary]) -> None:
        (self._dir(model_id) / "elements.json").write_text(
            json.dumps([e.model_dump() for e in elements]), encoding="utf-8"
        )

    # -- public API -----------------------------------------------------------------------

    def list(self) -> list[ModelSummary]:
        return sorted(self._models.values(), key=lambda m: m.created_at, reverse=True)

    def get(self, model_id: str) -> ModelSummary | None:
        return self._models.get(model_id)

    def has_sample(self) -> bool:
        return any(m.is_sample for m in self._models.values())

    def register(self, source: Path, name: str, is_sample: bool = False) -> ModelSummary:
        """Copy an IFC file into the store and return its (still processing) summary."""
        model_id = uuid.uuid4().hex[:12]
        target_dir = self._dir(model_id)
        target_dir.mkdir(parents=True)
        shutil.copyfile(source, target_dir / "model.ifc")
        meta = ModelSummary(
            id=model_id,
            name=name,
            status="processing",
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            file_size_bytes=(target_dir / "model.ifc").stat().st_size,
            is_sample=is_sample,
        )
        with self._lock:
            self._models[model_id] = meta
            self._write_meta(meta)
        return meta

    def process(self, model_id: str) -> None:
        """Parse the stored IFC and persist the derived artefacts. Safe to run in a worker thread."""
        meta = self._models[model_id]
        target_dir = self._dir(model_id)
        try:
            parsed = parse_ifc(target_dir / "model.ifc")
            overrides = self.mapping(model_id).overrides
            elements = apply_estimates(parsed.elements, overrides) if overrides else parsed.elements
            carbon = (
                summarize(elements, floor_area_m2=parsed.floor_area_m2, floor_area_source=parsed.floor_area_source)
                if overrides
                else parsed.carbon
            )
            (target_dir / "geometry.glb").write_bytes(parsed.glb)
            self._write_elements(model_id, elements)
            (target_dir / "extras.json").write_text(
                json.dumps({k: v.model_dump() for k, v in parsed.extras.items()}), encoding="utf-8"
            )
            (target_dir / "carbon.json").write_text(carbon.model_dump_json(), encoding="utf-8")
            (target_dir / "details.json").unlink(missing_ok=True)  # v0.1 artefact
            meta = meta.model_copy(
                update={
                    "status": "ready",
                    "error": None,
                    "schema_version": parsed.schema_version,
                    "element_count": len(elements),
                    "elements_with_geometry": sum(1 for e in elements if e.has_geometry),
                    "storeys": parsed.storeys,
                    "ifc_classes": parsed.ifc_classes,
                    "total_kgco2e": carbon.total_kgco2e,
                    "gross_floor_area_m2": carbon.gross_floor_area_m2,
                    "intensity_kgco2e_m2": carbon.intensity_kgco2e_m2,
                    "length_unit": parsed.length_unit,
                    "parse_seconds": parsed.parse_seconds,
                }
            )
        except Exception as exc:
            log.exception("failed to parse model %s", model_id)
            meta = meta.model_copy(update={"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        with self._lock:
            self._cache.pop(model_id, None)
            self._models[model_id] = meta
            self._write_meta(meta)

    def delete(self, model_id: str) -> bool:
        with self._lock:
            meta = self._models.pop(model_id, None)
            self._cache.pop(model_id, None)
        if meta is None:
            return False
        shutil.rmtree(self._dir(model_id), ignore_errors=True)
        return True

    # -- derived artefacts ------------------------------------------------------------------

    def _load(self, model_id: str) -> tuple[list[ElementSummary], dict[str, ElementExtras]]:
        with self._lock:
            if model_id in self._cache:
                self._cache.move_to_end(model_id)
                return self._cache[model_id]
            folder = self._dir(model_id)
            elements = [
                ElementSummary.model_validate(item)
                for item in json.loads((folder / "elements.json").read_text(encoding="utf-8"))
            ]
            extras = {
                key: ElementExtras.model_validate(value)
                for key, value in json.loads((folder / "extras.json").read_text(encoding="utf-8")).items()
            }
            self._cache[model_id] = (elements, extras)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
            return elements, extras

    def elements(self, model_id: str) -> list[ElementSummary]:
        return self._load(model_id)[0]

    def element_detail(self, model_id: str, global_id: str) -> ElementDetail | None:
        elements, extras = self._load(model_id)
        summary = next((e for e in elements if e.global_id == global_id), None)
        if summary is None:
            return None
        extra = extras.get(global_id, ElementExtras())
        return ElementDetail(**summary.model_dump(), **extra.model_dump())

    def carbon(self, model_id: str) -> CarbonSummary:
        return CarbonSummary.model_validate_json((self._dir(model_id) / "carbon.json").read_text(encoding="utf-8"))

    def glb_path(self, model_id: str) -> Path:
        return self._dir(model_id) / "geometry.glb"

    # -- material mapping ---------------------------------------------------------------------

    def mapping(self, model_id: str) -> MaterialMapping:
        path = self._dir(model_id) / "mapping.json"
        if not path.exists():
            return MaterialMapping()
        return MaterialMapping.model_validate_json(path.read_text(encoding="utf-8"))

    def materials(self, model_id: str) -> list[MaterialUsage]:
        return material_usage(self.elements(model_id), self.mapping(model_id).overrides)

    def set_mapping(self, model_id: str, mapping: MaterialMapping) -> ModelSummary:
        """Store the overrides and recompute every estimate without parsing the IFC again."""
        valid = set(factor_index()) | {UNCLASSIFIED}
        unknown = sorted({v for v in mapping.overrides.values() if v not in valid})
        if unknown:
            raise MappingError(f"unknown categories: {', '.join(unknown)}")
        with self._lock:
            meta = self._models[model_id]
            previous = self.carbon(model_id)
            elements = apply_estimates(self.elements(model_id), mapping.overrides)
            carbon = summarize(
                elements,
                floor_area_m2=previous.gross_floor_area_m2,
                floor_area_source=previous.floor_area_source,
            )
            folder = self._dir(model_id)
            (folder / "mapping.json").write_text(mapping.model_dump_json(indent=2), encoding="utf-8")
            self._write_elements(model_id, elements)
            (folder / "carbon.json").write_text(carbon.model_dump_json(), encoding="utf-8")
            extras = self._load(model_id)[1]
            self._cache[model_id] = (elements, extras)
            meta = meta.model_copy(
                update={"total_kgco2e": carbon.total_kgco2e, "intensity_kgco2e_m2": carbon.intensity_kgco2e_m2}
            )
            self._models[model_id] = meta
            self._write_meta(meta)
            return meta
