from __future__ import annotations

from pathlib import Path

import pytest

from app.ifc.parse import ParsedModel, parse_ifc

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample-building.ifc"


@pytest.fixture(scope="session")
def sample_path() -> Path:
    assert SAMPLE.exists(), "run `python scripts/make_sample.py` first"
    return SAMPLE


@pytest.fixture(scope="session")
def parsed(sample_path: Path) -> ParsedModel:
    return parse_ifc(sample_path)
