"""File-backed model store.

Each model lives in ``<data_dir>/<id>/`` with the original IFC, a metadata JSON,
the element list, the per-element details and the GLB. Keeping everything on disk
means the API survives restarts and stays stateless enough to run in a container.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.ifc.parse import parse_ifc
from app.schemas import CarbonSummary, ElementDetail, ElementSummary, ModelSummary

log = logging.getLogger(__name__)


class ModelStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._models: dict[str, ModelSummary] = {}
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
            self._models[meta.id] = meta

    def _write_meta(self, meta: ModelSummary) -> None:
        (self._dir(meta.id) / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")

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
            (target_dir / "geometry.glb").write_bytes(parsed.glb)
            (target_dir / "elements.json").write_text(
                json.dumps([e.model_dump() for e in parsed.elements]), encoding="utf-8"
            )
            (target_dir / "details.json").write_text(
                json.dumps({k: v.model_dump() for k, v in parsed.details.items()}), encoding="utf-8"
            )
            (target_dir / "carbon.json").write_text(parsed.carbon.model_dump_json(), encoding="utf-8")
            meta = meta.model_copy(
                update={
                    "status": "ready",
                    "schema_version": parsed.schema_version,
                    "element_count": len(parsed.elements),
                    "elements_with_geometry": sum(1 for e in parsed.elements if e.has_geometry),
                    "storeys": parsed.storeys,
                    "ifc_classes": parsed.ifc_classes,
                    "total_kgco2e": parsed.carbon.total_kgco2e,
                    "parse_seconds": parsed.parse_seconds,
                }
            )
        except Exception as exc:
            log.exception("failed to parse model %s", model_id)
            meta = meta.model_copy(update={"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        with self._lock:
            self._models[model_id] = meta
            self._write_meta(meta)

    def delete(self, model_id: str) -> bool:
        with self._lock:
            meta = self._models.pop(model_id, None)
        if meta is None:
            return False
        shutil.rmtree(self._dir(model_id), ignore_errors=True)
        return True

    # -- derived artefacts ------------------------------------------------------------------

    def elements(self, model_id: str) -> list[ElementSummary]:
        raw = json.loads((self._dir(model_id) / "elements.json").read_text(encoding="utf-8"))
        return [ElementSummary.model_validate(item) for item in raw]

    def element_detail(self, model_id: str, global_id: str) -> ElementDetail | None:
        raw = json.loads((self._dir(model_id) / "details.json").read_text(encoding="utf-8"))
        item = raw.get(global_id)
        return ElementDetail.model_validate(item) if item else None

    def carbon(self, model_id: str) -> CarbonSummary:
        return CarbonSummary.model_validate_json((self._dir(model_id) / "carbon.json").read_text(encoding="utf-8"))

    def glb_path(self, model_id: str) -> Path:
        return self._dir(model_id) / "geometry.glb"
