from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import ModelStore


@pytest.fixture()
def client(tmp_path: Path):
    store = ModelStore(tmp_path / "data")
    app = create_app(store=store, preload_sample=False)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_factors_are_exposed(client):
    factors = client.get("/api/carbon/factors").json()
    assert {f["category"] for f in factors} >= {"concrete", "steel", "timber"}


def test_upload_rejects_non_ifc(client):
    response = client.post("/api/models", files={"file": ("model.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_upload_parse_and_query(client, sample_path: Path):
    with sample_path.open("rb") as fh:
        response = client.post("/api/models", files={"file": (sample_path.name, fh, "application/octet-stream")})
    assert response.status_code == 202
    model_id = response.json()["id"]

    # TestClient runs background tasks before returning, so the model is ready now.
    meta = client.get(f"/api/models/{model_id}").json()
    assert meta["status"] == "ready", meta.get("error")
    assert meta["element_count"] == 19
    assert meta["storeys"] == ["Level 0", "Level 1"]

    elements = client.get(f"/api/models/{model_id}/elements", params={"storey": "Level 1"}).json()
    assert elements and all(e["storey"] == "Level 1" for e in elements)

    detail = client.get(f"/api/models/{model_id}/elements/{elements[0]['global_id']}").json()
    assert detail["global_id"] == elements[0]["global_id"]
    assert "property_sets" in detail

    carbon = client.get(f"/api/models/{model_id}/carbon").json()
    assert carbon["total_kgco2e"] == pytest.approx(meta["total_kgco2e"])

    glb = client.get(f"/api/models/{model_id}/geometry.glb")
    assert glb.status_code == 200
    assert glb.headers["content-type"] == "model/gltf-binary"
    assert glb.content[:4] == b"glTF"

    assert client.delete(f"/api/models/{model_id}").status_code == 204
    assert client.get(f"/api/models/{model_id}").status_code == 404


def test_unknown_model_is_404(client):
    assert client.get("/api/models/nope/elements").status_code == 404
