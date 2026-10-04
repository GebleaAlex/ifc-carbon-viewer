from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app
from app.store import ModelStore


@pytest.fixture()
def client(tmp_path: Path):
    store = ModelStore(tmp_path / "data")
    app = create_app(store=store, preload_sample=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def model_id(client, sample_path: Path) -> str:
    with sample_path.open("rb") as fh:
        response = client.post("/api/models", files={"file": (sample_path.name, fh, "application/octet-stream")})
    assert response.status_code == 202
    # TestClient runs background tasks before returning, so the model is ready now.
    return response.json()["id"]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "version": __version__}


def test_factors_are_exposed(client):
    factors = client.get("/api/carbon/factors").json()
    assert {f["category"] for f in factors} >= {"concrete", "steel", "timber", "foam_insulation"}


def test_upload_rejects_non_ifc(client):
    response = client.post("/api/models", files={"file": ("model.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_upload_parse_and_query(client, model_id):
    meta = client.get(f"/api/models/{model_id}").json()
    assert meta["status"] == "ready", meta.get("error")
    assert meta["element_count"] == 149
    assert meta["storeys"] == ["Level 0", "Level 1", "Level 2"]
    assert meta["length_unit"] == "mm"
    assert meta["gross_floor_area_m2"] == pytest.approx(1008.0)

    elements = client.get(f"/api/models/{model_id}/elements", params={"storey": "Level 1"}).json()
    assert elements and all(e["storey"] == "Level 1" for e in elements)

    wall = next(e for e in elements if e["name"] == "South wall L1")
    detail = client.get(f"/api/models/{model_id}/elements/{wall['global_id']}").json()
    assert detail["global_id"] == wall["global_id"]
    assert len(detail["layers"]) == 4
    assert "Pset_WallCommon" in detail["property_sets"]

    carbon = client.get(f"/api/models/{model_id}/carbon").json()
    assert carbon["total_kgco2e"] == pytest.approx(meta["total_kgco2e"])
    assert carbon["intensity_kgco2e_m2"] == pytest.approx(meta["intensity_kgco2e_m2"])

    glb = client.get(f"/api/models/{model_id}/geometry.glb")
    assert glb.status_code == 200
    assert glb.headers["content-type"] == "model/gltf-binary"
    assert glb.content[:4] == b"glTF"

    assert client.delete(f"/api/models/{model_id}").status_code == 204
    assert client.get(f"/api/models/{model_id}").status_code == 404


def test_material_mapping_recomputes_without_reparsing(client, model_id):
    materials = client.get(f"/api/models/{model_id}/materials").json()
    unknown = materials[0]
    assert unknown["material"] == "Sto Silent acoustic panel"
    assert unknown["category"] is None
    before = client.get(f"/api/models/{model_id}").json()["total_kgco2e"]

    meta = client.put(
        f"/api/models/{model_id}/mapping", json={"overrides": {"Sto Silent acoustic panel": "mortar"}}
    ).json()
    assert meta["total_kgco2e"] > before
    carbon = client.get(f"/api/models/{model_id}/carbon").json()
    assert carbon["unclassified_elements"] == 0
    assert carbon["total_kgco2e"] == pytest.approx(meta["total_kgco2e"])
    row = next(
        m for m in client.get(f"/api/models/{model_id}/materials").json() if m["material"] == unknown["material"]
    )
    assert row["overridden"] and row["category"] == "mortar" and row["auto_category"] is None
    assert client.get(f"/api/models/{model_id}/mapping").json() == {
        "overrides": {"Sto Silent acoustic panel": "mortar"}
    }

    assert client.put(f"/api/models/{model_id}/mapping", json={"overrides": {}}).json()["total_kgco2e"] == before


def test_mapping_rejects_unknown_categories(client, model_id):
    response = client.put(f"/api/models/{model_id}/mapping", json={"overrides": {"Concrete": "kryptonite"}})
    assert response.status_code == 422
    assert "kryptonite" in response.json()["detail"]


def test_csv_export_adds_up_to_the_total(client, model_id):
    response = client.get(f"/api/models/{model_id}/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "sample-building-carbon.csv" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    total = sum(float(r["carbon_kgco2e"] or 0) for r in rows)
    assert total == pytest.approx(client.get(f"/api/models/{model_id}").json()["total_kgco2e"], abs=1.0)
    assert {r["material"] for r in rows if r["name"] == "South wall L1"} == {
        "Clay brick facing",
        "Mineral wool",
        "Reinforced concrete C30/37",
        "Gypsum plaster",
    }


def test_report_json(client, model_id):
    report = client.get(f"/api/models/{model_id}/report.json").json()
    assert report["model"]["id"] == model_id
    assert report["carbon"]["by_material_category"]
    assert report["materials"]
    assert "Not suitable for reporting" in report["disclaimer"]


def test_models_from_older_versions_are_parsed_again(tmp_path, sample_path):
    data = tmp_path / "data"
    store = ModelStore(data)
    meta = store.register(sample_path, sample_path.name)
    store.process(meta.id)
    (data / meta.id / "extras.json").unlink()  # what a v0.1 data folder looks like

    reopened = ModelStore(data)
    assert reopened.stale == [meta.id]
    assert reopened.get(meta.id).status == "processing"
    reopened.process(meta.id)
    assert reopened.get(meta.id).status == "ready"
    assert json.loads((data / meta.id / "meta.json").read_text())["length_unit"] == "mm"


def test_unknown_model_is_404(client):
    assert client.get("/api/models/nope/elements").status_code == 404
