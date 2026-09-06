from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read once from environment variables."""

    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("IFC_DATA_DIR", BACKEND_ROOT / "data")))
    sample_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("IFC_SAMPLE_PATH", BACKEND_ROOT / "samples" / "sample-building.ifc")
        )
    )
    preload_sample: bool = field(default_factory=lambda: _env_bool("IFC_PRELOAD_SAMPLE", True))
    max_upload_mb: int = field(default_factory=lambda: int(os.environ.get("IFC_MAX_UPLOAD_MB", "200")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.environ.get("IFC_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        )
    )


settings = Settings()
