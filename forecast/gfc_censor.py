"""Trusted supervisor for leakage-censored GFC handoffs.

Only this supervisor may launch the privileged reader.  Child streams are sealed,
temporary state is destroyed on every exit path, and only an exact phase-specific
allow-list can be published.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .sandbox_process import run_sealed_process

PRE_LIFT_MASKS = (
    "eligible_2020",
    "eligible_2021",
    "eligible_2022",
    "positive_2021",
    "positive_2022",
)
POST_LIFT_MASKS = ("eligible_2022", "positive_2023")
CENSOR_WORKER = Path(__file__).with_name("gfc_censor_worker.py")
FROZEN_GFC_RELEASE = "GFC-2024-v1.12"


@dataclass(frozen=True)
class CensorTranscript:
    child_exit_status: int
    supervisor_error_code: str
    stdout_bytes: int
    stderr_bytes: int
    file_names: tuple[str, ...]
    file_sizes: tuple[tuple[str, int], ...]
    file_sha256: tuple[tuple[str, str], ...]

    @property
    def succeeded(self) -> bool:
        return self.supervisor_error_code == "OK"

    def observable(self) -> dict[str, object]:
        """Return every externally observable, non-secret transcript field."""

        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_names(phase: str) -> tuple[str, ...]:
    masks = PRE_LIFT_MASKS if phase == "pre_lift" else POST_LIFT_MASKS
    return tuple(sorted(("handoff.json", *(f"{name}.npy" for name in masks))))


def _inventory(output_dir: Path) -> tuple[str, ...]:
    return tuple(sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file() or path.is_symlink()
    ))


def _validate_handoff(output_dir: Path, phase: str) -> None:
    expected_masks = PRE_LIFT_MASKS if phase == "pre_lift" else POST_LIFT_MASKS
    document = json.loads((output_dir / "handoff.json").read_text(encoding="utf-8"))
    required = {"phase", "gfc_release", "treecover_threshold", "shape", "crs", "transform", "masks"}
    if set(document) != required or document["phase"] != phase:
        raise ValueError("handoff schema mismatch")
    if document["treecover_threshold"] != 30:
        raise ValueError("tree-cover threshold changed")
    if tuple(document["masks"]) != expected_masks:
        raise ValueError("mask allow-list mismatch")
    shape = tuple(int(value) for value in document["shape"])
    if len(shape) != 2 or any(value <= 0 for value in shape):
        raise ValueError("invalid handoff shape")
    if len(document["transform"]) != 6 or not document["crs"]:
        raise ValueError("unsafe alignment metadata")
    for name in expected_masks:
        record = document["masks"][name]
        if set(record) != {"file", "dtype", "formula"}:
            raise ValueError("mask metadata mismatch")
        if record["file"] != f"{name}.npy" or record["dtype"] != "bool":
            raise ValueError("mask storage mismatch")
        values = np.load(output_dir / record["file"], allow_pickle=False)
        if values.dtype != np.bool_ or values.shape != shape:
            raise ValueError("mask array mismatch")


def _minimal_environment(temp_dir: Path) -> dict[str, str]:
    keep = ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP")
    environment = {key: os.environ[key] for key in keep if key in os.environ}
    environment.update({
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "GDAL_PAM_ENABLED": "NO",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": "",
        "TEMP": str(temp_dir),
        "TMP": str(temp_dir),
    })
    return environment


def _empty_transcript(
    *, returncode: int, code: str, stdout_bytes: int = 0, stderr_bytes: int = 0
) -> CensorTranscript:
    return CensorTranscript(returncode, code, stdout_bytes, stderr_bytes, (), (), ())


def run_censoring(
    request: Mapping[str, Any],
    destination: str | Path,
    *,
    timeout_seconds: float = 60.0,
    temp_parent: str | Path | None = None,
    sealed_artifact_hashes: Mapping[str, str] | None = None,
    transition_log: str | Path | None = None,
    transition_utc: str | None = None,
) -> CensorTranscript:
    """Run the privileged utility and publish only a validated safe handoff."""

    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"Censor destination must not exist: {destination}")
    phase = str(request.get("phase", ""))
    if phase not in {"pre_lift", "post_lift"}:
        return _empty_transcript(returncode=64, code="INVALID_REQUEST")
    if phase == "post_lift":
        if not sealed_artifact_hashes or transition_log is None:
            return _empty_transcript(returncode=64, code="EMBARGO_NOT_SEALED")
        for name, digest in sealed_artifact_hashes.items():
            if not name or len(str(digest)) != 64:
                return _empty_transcript(returncode=64, code="EMBARGO_NOT_SEALED")

    parent = Path(temp_parent).resolve() if temp_parent is not None else None
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gfc-censor-", dir=parent) as temporary:
        temp_dir = Path(temporary)
        request_path = temp_dir / "request.json"
        output_dir = temp_dir / "output"
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        result = run_sealed_process(
            [sys.executable, "-I", str(CENSOR_WORKER), str(request_path), str(output_dir)],
            cwd=temp_dir,
            env=_minimal_environment(temp_dir),
            timeout_seconds=timeout_seconds,
        )
        if result.timed_out:
            return _empty_transcript(
                returncode=result.returncode, code="CHILD_TIMEOUT",
                stdout_bytes=result.stdout_bytes, stderr_bytes=result.stderr_bytes,
            )
        if result.returncode != 0:
            return _empty_transcript(
                returncode=result.returncode, code="CHILD_FAILED",
                stdout_bytes=result.stdout_bytes, stderr_bytes=result.stderr_bytes,
            )
        if result.stdout_bytes or result.stderr_bytes:
            return _empty_transcript(
                returncode=result.returncode, code="STREAM_POLICY_VIOLATION",
                stdout_bytes=result.stdout_bytes, stderr_bytes=result.stderr_bytes,
            )
        try:
            names = _inventory(output_dir)
            if names != _expected_names(phase):
                raise ValueError("output allow-list violation")
            if any((output_dir / name).is_symlink() for name in names):
                raise ValueError("symlink output denied")
            _validate_handoff(output_dir, phase)
            sizes = tuple((name, (output_dir / name).stat().st_size) for name in names)
            digests = tuple((name, _sha256(output_dir / name)) for name in names)
        except (OSError, ValueError, json.JSONDecodeError):
            return _empty_transcript(returncode=65, code="OUTPUT_POLICY_VIOLATION")

        publish_dir = destination.with_name(destination.name + ".publishing")
        if publish_dir.exists():
            raise FileExistsError(f"Publish staging path exists: {publish_dir}")
        try:
            shutil.copytree(output_dir, publish_dir)
            os.replace(publish_dir, destination)
        finally:
            if publish_dir.exists():
                shutil.rmtree(publish_dir)

        transcript = CensorTranscript(
            child_exit_status=result.returncode,
            supervisor_error_code="OK",
            stdout_bytes=0,
            stderr_bytes=0,
            file_names=names,
            file_sizes=sizes,
            file_sha256=digests,
        )

    if phase == "post_lift":
        log_path = Path(transition_log).resolve()  # type: ignore[arg-type]
        if log_path.exists():
            raise FileExistsError(f"Embargo transition log already exists: {log_path}")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "event": "gfc_2023_embargo_lift",
            "timestamp_utc": transition_utc or datetime.now(timezone.utc).isoformat(),
            "sealed_artifact_hashes": dict(sorted(sealed_artifact_hashes.items())),  # type: ignore[union-attr]
            "handoff_files": dict(transcript.file_sha256),
        }
        log_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return transcript


def request_from_frozen_pin(
    pin_path: str | Path,
    bbox: tuple[float, float, float, float],
    *,
    phase: str,
) -> dict[str, object]:
    """Build a child request from the frozen release/per-tile checksum pin."""

    pin = json.loads(Path(pin_path).read_text(encoding="utf-8"))
    if set(pin) != {"schema_version", "gfc_release", "layers"}:
        raise ValueError("GFC pin schema mismatch")
    if pin["schema_version"] != 1 or pin["gfc_release"] != FROZEN_GFC_RELEASE:
        raise ValueError("GFC release is not the frozen study release")
    if set(pin["layers"]) != {"treecover2000", "datamask", "lossyear"}:
        raise ValueError("GFC pin layer allow-list mismatch")
    for layer, records in pin["layers"].items():
        if not isinstance(records, list) or not records:
            raise ValueError(f"GFC pin has no tiles for {layer}")
        for record in records:
            if set(record) != {"path", "sha256"} or len(str(record["sha256"])) != 64:
                raise ValueError("GFC pin tile schema mismatch")
    return {
        "phase": phase,
        "gfc_release": FROZEN_GFC_RELEASE,
        "bbox": list(bbox),
        "layers": pin["layers"],
    }


def load_handoff(directory: str | Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Load an already-censored handoff; no raw GFC capability is involved."""

    directory = Path(directory)
    document = json.loads((directory / "handoff.json").read_text(encoding="utf-8"))
    phase = str(document.get("phase", ""))
    _validate_handoff(directory, phase)
    arrays = {
        name: np.load(directory / record["file"], allow_pickle=False)
        for name, record in document["masks"].items()
    }
    return document, arrays
