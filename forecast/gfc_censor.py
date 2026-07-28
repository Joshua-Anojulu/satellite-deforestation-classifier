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

from ._atomic_publish import (
    create_placeholder,
    publish_container,
    read_container,
    write_container,
)
from ._embargo_seal import verify_seal
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
class EmbargoSeal:
    """The trust root a post-lift run is checked against.

    Replaces the old ``sealed_artifact_hashes`` mapping, which proved nothing:
    any non-empty mapping of 64-character strings was admitted, so
    ``{"all-frozen-artifacts": "a" * 64}`` passed with no artifact existing.
    """

    seal_path: Path
    artifact_root: Path
    seal_store: Path
    approved_tree_shas: tuple[str, ...]
    expected_artifacts: tuple[str, ...]


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
    seal: EmbargoSeal | None = None,
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
    if phase == "post_lift" and (seal is None or transition_log is None):
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

        transcript = CensorTranscript(
            child_exit_status=result.returncode,
            supervisor_error_code="OK",
            stdout_bytes=0,
            stderr_bytes=0,
            file_names=names,
            file_sizes=sizes,
            file_sha256=digests,
        )

        if phase == "pre_lift":
            publish_dir = destination.with_name(destination.name + ".publishing")
            if publish_dir.exists():
                raise FileExistsError(f"Publish staging path exists: {publish_dir}")
            try:
                shutil.copytree(output_dir, publish_dir)
                os.replace(publish_dir, destination)
            finally:
                if publish_dir.exists():
                    shutil.rmtree(publish_dir)
            return transcript

        # --- post-lift: one sealed container, one commit ---------------------
        #
        # The masks and the transition record are published as a SINGLE object,
        # so a crash can never leave `positive_2023` readable with no record
        # that the embargo lifted.  "Exactly one of the two published" is not
        # representable.
        return _publish_post_lift(
            output_dir=output_dir,
            names=names,
            destination=destination,
            seal=seal,  # type: ignore[arg-type]
            transition_log=Path(transition_log),  # type: ignore[arg-type]
            transition_utc=transition_utc,
            transcript=transcript,
        )


def _publish_post_lift(
    *,
    output_dir: Path,
    names: tuple[str, ...],
    destination: Path,
    seal: EmbargoSeal,
    transition_log: Path,
    transition_utc: str | None,
    transcript: CensorTranscript,
) -> CensorTranscript:
    """Verify the seal under the transition lock, then commit one container."""

    # A separate exclusive lock file provides mutual exclusion.  It is NOT the
    # transition record: `open("x")` creates a durable object a crash can
    # strand, which is why the record travels inside the committed container.
    lock_path = destination.with_name(destination.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_handle = open(lock_path, "x")
    except FileExistsError:
        return _empty_transcript(returncode=64, code="TRANSITION_IN_PROGRESS")

    try:
        # Hashes are recomputed here, while the lock is held: a verification
        # taken outside it is only a statement about the instant it was taken.
        verification = verify_seal(
            seal.seal_path,
            seal.artifact_root,
            approved_tree_shas=seal.approved_tree_shas,
            expected_artifacts=seal.expected_artifacts,
            seal_store=seal.seal_store,
        )
        if not verification.verified:
            return _empty_transcript(returncode=64, code="EMBARGO_NOT_SEALED")

        if transition_log.exists():
            raise FileExistsError(f"Embargo transition record already exists: {transition_log}")

        record = {
            "event": "gfc_2023_embargo_lift",
            "timestamp_utc": transition_utc or datetime.now(timezone.utc).isoformat(),
            "generating_tree_sha": verification.generating_tree_sha,
            "sealed_artifact_count": verification.artifact_count,
            "handoff_files": dict(transcript.file_sha256),
        }
        payload = {name: (output_dir / name).read_bytes() for name in names}

        # Staging and backup sit beside the destination so all three share one
        # volume, which ReplaceFileW requires.
        staging = destination.with_name(destination.name + ".staging")
        backup = destination.with_name(destination.name + ".backup")
        write_container(payload, record, staging)
        create_placeholder(destination)
        outcome = publish_container(staging, destination, backup)

        if not outcome.committed:
            # `exposed` is never downgraded to a rollback here; the caller reads
            # the status and follows the roll-forward action.
            code = "EMBARGO_EXPOSED" if outcome.exposed else "PUBLISH_FAILED"
            return _empty_transcript(returncode=65, code=code)

        transition_log.parent.mkdir(parents=True, exist_ok=True)
        transition_log.write_text(
            json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        if staging.exists():
            staging.unlink()
        return transcript
    finally:
        lock_handle.close()
        if lock_path.exists():
            lock_path.unlink()


def _load_handoff_container(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Read a published post-lift container back into handoff form."""

    import io

    payload, record = read_container(path)
    document = json.loads(payload["handoff.json"].decode("utf-8"))
    document["transition_record"] = record
    arrays = {
        name: np.load(io.BytesIO(payload[entry["file"]]), allow_pickle=False)
        for name, entry in document["masks"].items()
    }
    return document, arrays


def load_transition_record(path: str | Path) -> dict[str, Any]:
    """Read only the transition record from a published container."""

    return read_container(Path(path))[1]


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
    """Load an already-censored handoff; no raw GFC capability is involved.

    Accepts either a pre-lift handoff directory or a post-lift container file,
    since post-lift publishes masks and the transition record as one object.
    """

    directory = Path(directory)
    if directory.is_file():
        return _load_handoff_container(directory)
    document = json.loads((directory / "handoff.json").read_text(encoding="utf-8"))
    phase = str(document.get("phase", ""))
    _validate_handoff(directory, phase)
    arrays = {
        name: np.load(directory / record["file"], allow_pickle=False)
        for name, record in document["masks"].items()
    }
    return document, arrays
