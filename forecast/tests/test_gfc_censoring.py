from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine

import forecast.gfc_censor as censor
from forecast.gfc_censor import (
    FROZEN_GFC_RELEASE,
    load_handoff,
    request_from_frozen_pin,
    run_censoring,
)
from forecast.prelift_sandbox import PRE_LIFT_ROLES, run_pre_lift_role
from forecast.sandbox_process import run_sealed_process


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_tile(path: Path, values: np.ndarray, transform: Affine) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
    ) as destination:
        destination.write(values.astype(np.uint8), 1)
    return path


def _request_for_layout(
    root: Path,
    lossyear: np.ndarray,
    layout: list[tuple[slice, slice, Affine]],
    *,
    phase: str = "pre_lift",
) -> dict[str, object]:
    arrays = {
        "treecover2000": np.full(lossyear.shape, 80, dtype=np.uint8),
        "datamask": np.ones(lossyear.shape, dtype=np.uint8),
        "lossyear": lossyear.astype(np.uint8),
    }
    layers: dict[str, list[dict[str, str]]] = {}
    for layer, values in arrays.items():
        records = []
        for index, (rows, columns, transform) in enumerate(layout):
            path = _write_tile(root / f"{layer}_{index}.tif", values[rows, columns], transform)
            records.append({"path": str(path), "sha256": _sha256(path)})
        layers[layer] = records
    height, width = lossyear.shape
    return {
        "phase": phase,
        "gfc_release": "SYNTHETIC-GFC",
        "bbox": [0.0, 0.0, float(width), float(height)],
        "layers": layers,
    }


def _one_tile_request(root: Path, lossyear: np.ndarray, phase: str = "pre_lift"):
    height, _ = lossyear.shape
    return _request_for_layout(
        root,
        lossyear,
        [(slice(None), slice(None), Affine(1, 0, 0, 0, -1, height))],
        phase=phase,
    )


def _published_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


@pytest.mark.parametrize(
    "layout",
    [
        [
            (slice(None), slice(0, 2), Affine(1, 0, 0, 0, -1, 4)),
            (slice(None), slice(2, 4), Affine(1, 0, 2, 0, -1, 4)),
        ],
        [
            (slice(0, 2), slice(None), Affine(1, 0, 0, 0, -1, 4)),
            (slice(2, 4), slice(None), Affine(1, 0, 0, 0, -1, 2)),
        ],
        [
            (slice(0, 2), slice(0, 2), Affine(1, 0, 0, 0, -1, 4)),
            (slice(0, 2), slice(2, 4), Affine(1, 0, 2, 0, -1, 4)),
            (slice(2, 4), slice(0, 2), Affine(1, 0, 0, 0, -1, 2)),
            (slice(2, 4), slice(2, 4), Affine(1, 0, 2, 0, -1, 2)),
        ],
    ],
    ids=("east-west", "north-south", "four-corner"),
)
def test_transform_aware_seam_mosaics(layout, tmp_path):
    lossyear = np.array([
        [21, 21, 0, 0],
        [0, 0, 22, 22],
        [0, 23, 24, 0],
        [0, 0, 0, 0],
    ], dtype=np.uint8)
    request = _request_for_layout(tmp_path / "raw", lossyear, layout)
    output = tmp_path / "handoff"
    transcript = run_censoring(request, output, temp_parent=tmp_path / "sandbox")

    assert transcript.succeeded
    document, masks = load_handoff(output)
    assert document["shape"] == [4, 4]
    assert masks["positive_2021"].tolist() == (lossyear == 21).tolist()
    assert masks["positive_2022"].tolist() == (lossyear == 22).tolist()
    assert masks["eligible_2022"].tolist() == ((lossyear == 0) | (lossyear > 22)).tolist()
    assert list((tmp_path / "sandbox").iterdir()) == []


def test_missing_required_seam_tile_fails_closed(tmp_path):
    lossyear = np.zeros((4, 4), dtype=np.uint8)
    layout = [(slice(None), slice(0, 2), Affine(1, 0, 0, 0, -1, 4))]
    request = _request_for_layout(tmp_path / "raw", lossyear, layout)
    transcript = run_censoring(
        request, tmp_path / "handoff", temp_parent=tmp_path / "sandbox"
    )
    assert transcript.supervisor_error_code == "CHILD_FAILED"
    assert transcript.stdout_bytes == transcript.stderr_bytes == 0
    assert not (tmp_path / "handoff").exists()
    assert list((tmp_path / "sandbox").iterdir()) == []


def test_pre_lift_complete_transcript_is_invariant_to_future_loss(tmp_path):
    fixed = np.array([
        [21, 21, 0, 0],
        [0, 0, 22, 22],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ], dtype=np.uint8)
    variants = []
    none = fixed.copy()
    variants.append(none)
    added = fixed.copy()
    added[2, 0] = 23
    added[2, 1] = 24
    variants.append(added)
    moved = fixed.copy()
    moved[0, 3] = 24
    moved[3, 3] = 23
    variants.append(moved)
    removed = added.copy()
    removed[2, :] = 0
    variants.append(removed)

    transcripts = []
    contents = []
    for index, lossyear in enumerate(variants):
        request = _one_tile_request(tmp_path / f"raw-{index}", lossyear)
        output = tmp_path / f"handoff-{index}"
        result = run_censoring(request, output, temp_parent=tmp_path / "sandbox")
        transcripts.append(result.observable())
        contents.append(_published_bytes(output))

    assert transcripts.count(transcripts[0]) == len(transcripts)
    assert contents.count(contents[0]) == len(contents)
    assert list((tmp_path / "sandbox").iterdir()) == []


def test_post_lift_complete_transcript_collapses_every_year_after_2023(tmp_path):
    fixed = np.array([
        [23, 23, 0, 0],
        [0, 0, 22, 22],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ], dtype=np.uint8)
    variants = [fixed.copy() for _ in range(3)]
    variants[0][2, 0] = 24
    variants[1][3, 3] = 24
    # variants[2] removes every post-2023 loss pixel.
    transcripts = []
    contents = []
    logs = []
    for index, lossyear in enumerate(variants):
        request = _one_tile_request(tmp_path / f"raw-{index}", lossyear, phase="post_lift")
        output = tmp_path / f"handoff-{index}"
        log = tmp_path / f"lift-{index}.json"
        result = run_censoring(
            request,
            output,
            temp_parent=tmp_path / "sandbox",
            sealed_artifact_hashes={"all-frozen-artifacts": "a" * 64},
            transition_log=log,
            transition_utc="2030-01-01T00:00:00+00:00",
        )
        transcripts.append(result.observable())
        contents.append(_published_bytes(output))
        logs.append(log.read_bytes())

    assert transcripts.count(transcripts[0]) == len(transcripts)
    assert contents.count(contents[0]) == len(contents)
    assert logs.count(logs[0]) == len(logs)
    _, masks = load_handoff(tmp_path / "handoff-0")
    assert masks["positive_2023"].tolist() == (fixed == 23).tolist()


def test_post_lift_refuses_to_run_before_artifacts_are_sealed(tmp_path):
    request = _one_tile_request(
        tmp_path / "raw", np.zeros((2, 2), dtype=np.uint8), phase="post_lift"
    )
    transcript = run_censoring(request, tmp_path / "handoff")
    assert transcript.supervisor_error_code == "EMBARGO_NOT_SEALED"
    assert not (tmp_path / "handoff").exists()


def test_frozen_pin_drives_release_and_per_tile_checksum_verification(tmp_path):
    request = _one_tile_request(tmp_path / "raw", np.zeros((2, 2), dtype=np.uint8))
    pin = tmp_path / "gfc_pin.json"
    pin.write_text(json.dumps({
        "schema_version": 1,
        "gfc_release": FROZEN_GFC_RELEASE,
        "layers": request["layers"],
    }), encoding="utf-8")
    pinned_request = request_from_frozen_pin(
        pin, (0.0, 0.0, 2.0, 2.0), phase="pre_lift"
    )
    result = run_censoring(pinned_request, tmp_path / "handoff")
    assert result.succeeded
    document, _ = load_handoff(tmp_path / "handoff")
    assert document["gfc_release"] == FROZEN_GFC_RELEASE

    tampered = request["layers"]["lossyear"][0]
    Path(tampered["path"]).write_bytes(b"changed")
    failed = run_censoring(pinned_request, tmp_path / "failed")
    assert failed.supervisor_error_code == "CHILD_FAILED"
    assert failed.stdout_bytes == failed.stderr_bytes == 0


def test_grandchild_cannot_escape_the_job_object(tmp_path):
    """A detached grandchild is still killed with the tree.

    The child is created suspended and assigned to the Job Object before it is
    resumed, so there is no window in which it can spawn an uncontained
    descendant.  This asserts the containment end-to-end: the grandchild is
    launched detached, in its own process group, and would outlive its parent —
    but the job kills it, so its marker is never written.
    """

    marker = tmp_path / "escaped.txt"
    worker = tmp_path / "spawner.py"
    worker.write_text(
        "import subprocess, sys, time, os\n"
        "flags = 0\n"
        "if os.name == 'nt':\n"
        "    flags = 0x00000008 | 0x00000200\n"  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        "subprocess.Popen(\n"
        "    [sys.executable, '-c',\n"
        "     \"import time,sys; time.sleep(4); open(sys.argv[1],'w').write('escaped')\",\n"
        "     sys.argv[1]],\n"
        "    creationflags=flags,\n"
        "    start_new_session=os.name != 'nt',\n"
        ")\n"
        "time.sleep(600)\n",
        encoding="utf-8",
    )

    result = run_sealed_process(
        [sys.executable, "-I", str(worker), str(marker)],
        cwd=tmp_path,
        env={"SystemRoot": os.environ.get("SystemRoot", ""), "PATH": os.environ.get("PATH", "")},
        timeout_seconds=1.0,
    )
    assert result.timed_out

    # Outlive the grandchild's own delay: if containment failed it would have
    # written the marker by now.
    time.sleep(6)
    assert not marker.exists(), "grandchild escaped the Job Object"


# Only the timeout case may starve the child; the other faults need a budget
# comfortably above interpreter startup or they race into CHILD_TIMEOUT.
_STARVING_TIMEOUT = 0.1
_GENEROUS_TIMEOUT = 30.0


@pytest.mark.parametrize(
    ("program", "expected_code", "timeout_seconds"),
    [
        (
            "import sys; print('sealed'); sys.exit(0)",
            "STREAM_POLICY_VIOLATION",
            _GENEROUS_TIMEOUT,
        ),
        ("import os; os._exit(5)", "CHILD_FAILED", _GENEROUS_TIMEOUT),
        ("import time; time.sleep(600)", "CHILD_TIMEOUT", _STARVING_TIMEOUT),
        (
            "import pathlib,sys; p=pathlib.Path(sys.argv[2]); p.mkdir(); "
            "(p/'unexpected').write_bytes(b'x')",
            "OUTPUT_POLICY_VIOLATION",
            _GENEROUS_TIMEOUT,
        ),
    ],
    ids=("stream", "crash", "timeout", "stray-file"),
)
def test_supervisor_destroys_temp_directory_on_every_exit_path(
    tmp_path, monkeypatch, program, expected_code, timeout_seconds
):
    worker = tmp_path / "fault_worker.py"
    worker.write_text(program, encoding="utf-8")
    monkeypatch.setattr(censor, "CENSOR_WORKER", worker)
    request = {"phase": "pre_lift", "gfc_release": "SYNTHETIC", "bbox": [0, 0, 1, 1], "layers": {}}
    transcript = run_censoring(
        request,
        tmp_path / "handoff",
        timeout_seconds=timeout_seconds,
        temp_parent=tmp_path / "sandbox",
    )
    assert transcript.supervisor_error_code == expected_code
    assert not (tmp_path / "handoff").exists()
    assert list((tmp_path / "sandbox").iterdir()) == []


@pytest.mark.parametrize("role", PRE_LIFT_ROLES)
@pytest.mark.parametrize("attack", ("raw", "network"))
def test_every_pre_lift_role_denies_raw_path_and_network(role, attack, tmp_path):
    raw_root = tmp_path / "raw-gfc"
    raw_root.mkdir()
    secret = raw_root / "lossyear.tif"
    secret.write_bytes(b"synthetic future outcome")
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import socket,sys\n"
        "if sys.argv[1] == 'raw':\n"
        "    open(sys.argv[2], 'rb').read()\n"
        "else:\n"
        "    socket.create_connection(('127.0.0.1', 9), timeout=0.01)\n",
        encoding="utf-8",
    )
    transcript = run_pre_lift_role(
        role,
        probe,
        (attack, str(secret)),
        raw_denied_roots=(raw_root,),
        temp_parent=tmp_path / "sandbox",
    )
    assert transcript.supervisor_error_code == "CAPABILITY_DENIED", transcript
    assert transcript.child_exit_status in {71, 72}
    assert transcript.stdout_bytes == transcript.stderr_bytes == 0
    assert list((tmp_path / "sandbox").iterdir()) == []


def test_pre_lift_launcher_allows_a_silent_role_without_denied_capabilities(tmp_path):
    probe = tmp_path / "silent.py"
    probe.write_text("value = 1 + 1\n", encoding="utf-8")
    raw_root = tmp_path / "raw-gfc"
    raw_root.mkdir()
    transcript = run_pre_lift_role(
        "freezing",
        probe,
        raw_denied_roots=(raw_root,),
        temp_parent=tmp_path / "sandbox",
    )
    assert transcript.succeeded, transcript
    assert transcript.child_exit_status == 0
    assert transcript.stdout_bytes == transcript.stderr_bytes == 0
