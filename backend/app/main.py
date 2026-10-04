"""FastAPI application exposing parsed IFC models, their geometry and carbon estimates."""

from __future__ import annotations

import logging
import re
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from app import __version__
from app.carbon.estimate import load_factors
from app.config import settings
from app.export import elements_csv, report
from app.schemas import (
    CarbonSummary,
    ElementDetail,
    ElementSummary,
    MaterialFactor,
    MaterialMapping,
    MaterialUsage,
    ModelSummary,
)
from app.store import MappingError, ModelStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app(store: ModelStore | None = None, preload_sample: bool | None = None) -> FastAPI:
    model_store = store or ModelStore(settings.data_dir)
    should_preload = settings.preload_sample if preload_sample is None else preload_sample

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if should_preload and settings.sample_path.exists() and not model_store.has_sample():
            meta = model_store.register(settings.sample_path, settings.sample_path.name, is_sample=True)
            model_store.process(meta.id)
            log.info("preloaded sample model %s", meta.id)
        if model_store.stale:
            # Models parsed by an older version are parsed again in the background.
            stale, model_store.stale = model_store.stale, []
            threading.Thread(target=lambda: [model_store.process(i) for i in stale], daemon=True).start()
        yield

    app = FastAPI(
        title="IFC Carbon Viewer API",
        version=__version__,
        description="Parses IFC/BIM models with IfcOpenShell, serves glTF geometry and indicative embodied carbon.",
        lifespan=lifespan,
    )
    app.state.store = model_store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def ready_model(model_id: str) -> ModelSummary:
        meta = model_store.get(model_id)
        if meta is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "model not found")
        if meta.status != "ready":
            raise HTTPException(status.HTTP_409_CONFLICT, f"model is {meta.status}")
        return meta

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/carbon/factors", response_model=list[MaterialFactor], tags=["carbon"])
    def carbon_factors() -> list[MaterialFactor]:
        return load_factors()

    @app.get("/api/models", response_model=list[ModelSummary], tags=["models"])
    def list_models() -> list[ModelSummary]:
        return model_store.list()

    @app.post("/api/models", response_model=ModelSummary, status_code=status.HTTP_202_ACCEPTED, tags=["models"])
    async def upload_model(file: UploadFile, background: BackgroundTasks) -> ModelSummary:
        filename = file.filename or "model.ifc"
        if not filename.lower().endswith(".ifc"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "only .ifc files are accepted")
        limit = settings.max_upload_mb * 1024 * 1024
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            written = 0
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file exceeds {settings.max_upload_mb} MB"
                    )
                tmp.write(chunk)
        tmp_path = Path(tmp.name)
        try:
            meta = model_store.register(tmp_path, filename)
        finally:
            tmp_path.unlink(missing_ok=True)
        background.add_task(model_store.process, meta.id)
        return meta

    @app.get("/api/models/{model_id}", response_model=ModelSummary, tags=["models"])
    def get_model(model_id: str) -> ModelSummary:
        meta = model_store.get(model_id)
        if meta is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "model not found")
        return meta

    @app.delete("/api/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["models"])
    def delete_model(model_id: str) -> None:
        if not model_store.delete(model_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "model not found")

    @app.get("/api/models/{model_id}/elements", response_model=list[ElementSummary], tags=["elements"])
    def list_elements(
        model_id: str,
        storey: str | None = Query(default=None),
        ifc_class: str | None = Query(default=None),
        material_category: str | None = Query(default=None),
    ) -> list[ElementSummary]:
        ready_model(model_id)
        elements = model_store.elements(model_id)
        if storey is not None:
            elements = [e for e in elements if e.storey == storey]
        if ifc_class is not None:
            elements = [e for e in elements if e.ifc_class == ifc_class]
        if material_category is not None:
            elements = [e for e in elements if e.material_category == material_category]
        return elements

    @app.get("/api/models/{model_id}/elements/{global_id}", response_model=ElementDetail, tags=["elements"])
    def get_element(model_id: str, global_id: str) -> ElementDetail:
        ready_model(model_id)
        detail = model_store.element_detail(model_id, global_id)
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "element not found")
        return detail

    @app.get("/api/models/{model_id}/carbon", response_model=CarbonSummary, tags=["carbon"])
    def get_carbon(model_id: str) -> CarbonSummary:
        ready_model(model_id)
        return model_store.carbon(model_id)

    @app.get("/api/models/{model_id}/materials", response_model=list[MaterialUsage], tags=["carbon"])
    def list_materials(model_id: str) -> list[MaterialUsage]:
        ready_model(model_id)
        return model_store.materials(model_id)

    @app.get("/api/models/{model_id}/mapping", response_model=MaterialMapping, tags=["carbon"])
    def get_mapping(model_id: str) -> MaterialMapping:
        ready_model(model_id)
        return model_store.mapping(model_id)

    @app.put("/api/models/{model_id}/mapping", response_model=ModelSummary, tags=["carbon"])
    def put_mapping(model_id: str, mapping: MaterialMapping) -> ModelSummary:
        """Replace the material overrides and recompute the estimates (no re-parse needed)."""
        ready_model(model_id)
        try:
            return model_store.set_mapping(model_id, mapping)
        except MappingError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    @app.get("/api/models/{model_id}/export.csv", tags=["export"])
    def export_csv(model_id: str) -> Response:
        meta = ready_model(model_id)
        filename = f"{re.sub(r'[^A-Za-z0-9._-]+', '-', Path(meta.name).stem) or 'model'}-carbon.csv"
        return Response(
            elements_csv(model_store.elements(model_id)),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/models/{model_id}/report.json", tags=["export"])
    def export_report(model_id: str) -> dict:
        meta = ready_model(model_id)
        return report(meta, model_store.carbon(model_id), model_store.materials(model_id))

    @app.get("/api/models/{model_id}/geometry.glb", tags=["geometry"])
    def get_geometry(model_id: str) -> FileResponse:
        ready_model(model_id)
        return FileResponse(
            model_store.glb_path(model_id),
            media_type="model/gltf-binary",
            filename=f"{model_id}.glb",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

    return app


app = create_app()
