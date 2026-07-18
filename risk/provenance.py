"""Provenance helpers because every result must identify its exact inputs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT

PINNED_PACKAGES = ("scikit-learn", "rasterio", "numpy", "openeo")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in PINNED_PACKAGES}


def git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True,
        capture_output=True, text=True,
    )
    return proc.stdout.strip()


def git_dirty() -> bool:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=PROJECT_ROOT, check=True,
        capture_output=True, text=True,
    )
    return bool(proc.stdout.strip())


def backend_provenance(connection: Any) -> dict[str, Any]:
    caps = connection.capabilities()
    return {
        "url": connection.root_url,
        "api_version": caps.api_version(),
        "backend_version": caps.get("backend_version"),
        "title": caps.get("title"),
        "processing_software": caps.get("processing:software"),
    }


def base_provenance() -> dict[str, Any]:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "package_versions": package_versions(),
    }


def write_json(path: str | Path, payload: Any) -> Path:
    """Write deterministic, human-readable JSON without hidden global state."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination
