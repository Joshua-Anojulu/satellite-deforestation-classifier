"""Predictors must not depend on the future; labels legitimately do.

A single combined comparison cannot express that.  Mutating every `lossyear`
after T changes `positive_{T+1}` by definition, so requiring the whole
transcript to stay byte-identical is impossible; and merely RECODING one future
year to another would not catch an implementation that read `lossyear > 0`,
since the value stays non-zero.  Hence: separate projections, and three
mutation families.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine

import forecast.gfc_censor as censor
from forecast._embargo_seal import build_seal
from forecast.gfc_censor import load_handoff, run_censoring

_APPROVED_TREE = "0123456789abcdef0123456789abcdef01234567"


def _write_tile(path: Path, values: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1],
        count=1, dtype="uint8", crs="EPSG:4326",
        transform=Affine(0.25, 0, 0, 0, -0.25, 1),
    ) as sink:
        sink.write(values, 1)
    return path


def _request(root: Path, lossyear: np.ndarray, *, phase: str) -> dict:
    import hashlib

    shape = lossyear.shape
    layers = {}
    for layer, values in (
        ("treecover2000", np.full(shape, 80, dtype=np.uint8)),
        ("datamask", np.ones(shape, dtype=np.uint8)),
        ("lossyear", lossyear),
    ):
        path = _write_tile(root / f"{layer}.tif", values)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        layers[layer] = [{"path": str(path), "sha256": digest}]
    return {
        "phase": phase,
        "gfc_release": censor.FROZEN_GFC_RELEASE,
        "bbox": [0.0, 0.0, 0.25 * shape[1], 0.25 * shape[0]],
        "layers": layers,
    }


def _seal(root: Path) -> censor.EmbargoSeal:
    store, artifacts = root / "store", root / "artifacts"
    store.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "manifest.json").write_text('{"frozen": true}', encoding="utf-8")
    (store / "seal.json").write_text(json.dumps(build_seal(
        artifacts, generating_tree_sha=_APPROVED_TREE,
        result_namespace="specification_w_exploratory", artifacts=["manifest.json"],
    )), encoding="utf-8")
    return censor.EmbargoSeal(
        seal_path=store / "seal.json", artifact_root=artifacts, seal_store=store,
        approved_tree_shas=(_APPROVED_TREE,), expected_artifacts=("manifest.json",),
    )


def _run_post_lift(tmp_path: Path, tag: str, lossyear: np.ndarray):
    result = run_censoring(
        _request(tmp_path / f"raw-{tag}", lossyear, phase="post_lift"),
        tmp_path / f"out-{tag}.container",
        temp_parent=tmp_path / f"sandbox-{tag}",
        seal=_seal(tmp_path / f"seal-{tag}"),
        transition_log=tmp_path / f"lift-{tag}.json",
        transition_utc="2030-01-01T00:00:00+00:00",
    )
    assert result.succeeded, result.supervisor_error_code
    return result


# Base scene: one 2023 loss (the label year), one 2022, one 2024, rest clear.
BASE = np.array([
    [23, 0, 0, 0],
    [0, 22, 0, 0],
    [0, 0, 24, 0],
    [0, 0, 0, 0],
], dtype=np.uint8)


def test_erasure_of_post_T_loss_leaves_predictors_identical(tmp_path):
    """Erasure: future codes -> 0. Recoding alone would not catch `lossyear > 0`."""

    erased = BASE.copy()
    erased[2, 2] = 0  # remove the 2024 loss entirely

    base = _run_post_lift(tmp_path, "base-erase", BASE)
    other = _run_post_lift(tmp_path, "erased", erased)
    assert base.predictor_projection() == other.predictor_projection()


def test_relocation_of_post_T_loss_leaves_predictors_identical(tmp_path):
    """Relocation: same future code, different pixel."""

    moved = BASE.copy()
    moved[2, 2] = 0
    moved[3, 3] = 24

    base = _run_post_lift(tmp_path, "base-move", BASE)
    other = _run_post_lift(tmp_path, "moved", moved)
    assert base.predictor_projection() == other.predictor_projection()


def test_recoding_of_post_T_loss_leaves_predictors_identical(tmp_path):
    """Recoding: one future code -> another future code."""

    recoded = BASE.copy()
    recoded[2, 2] = 23 if BASE[2, 2] == 24 else 24
    recoded[2, 2] = 24  # keep it strictly after the eligibility horizon

    base = _run_post_lift(tmp_path, "base-recode", BASE)
    other = _run_post_lift(tmp_path, "recoded", recoded)
    assert base.predictor_projection() == other.predictor_projection()


def test_label_year_changes_the_label_but_never_the_predictors(tmp_path):
    """The case that makes the split necessary rather than cosmetic.

    Mutating code 23 changes `positive_2023` by definition, so the COMBINED
    transcript differs -- while `eligible_2022` must not move at all.
    """

    changed = BASE.copy()
    changed[0, 0] = 0  # remove the 2023 positive

    base = _run_post_lift(tmp_path, "base-label", BASE)
    other = _run_post_lift(tmp_path, "label", changed)

    assert base.predictor_projection() == other.predictor_projection()
    assert base.label_projection() != other.label_projection()
    # And the naive whole-transcript comparison would have failed here, which
    # is exactly why noninterference is compared on the projection.
    assert base.observable() != other.observable()


def test_labels_match_their_exact_target_formula(tmp_path):
    """Labels are checked against the formula, never under future mutation."""

    _run_post_lift(tmp_path, "formula", BASE)
    document, masks = load_handoff(tmp_path / "out-formula.container")

    treecover_ok = np.full(BASE.shape, True)          # treecover 80 >= 30
    eligible_2022 = treecover_ok & ((BASE == 0) | (BASE > 22))
    expected_positive = eligible_2022 & (BASE == 23)

    assert masks["eligible_2022"].tolist() == eligible_2022.tolist()
    assert masks["positive_2023"].tolist() == expected_positive.tolist()
    assert document["masks"]["positive_2023"]["formula"] == "eligible_2022 & lossyear == 23"


def test_projections_partition_the_inventory(tmp_path):
    result = _run_post_lift(tmp_path, "partition", BASE)
    predictor = set(result.predictor_projection()["file_names"])
    label = set(result.label_projection()["file_names"])

    assert predictor & label == set(), "projections must not overlap"
    assert predictor | label == set(result.file_names), "projections must be exhaustive"
    assert "positive_2023.npy" in label
    assert "eligible_2022.npy" in predictor
    assert "handoff.json" in predictor


def test_label_hashes_are_excluded_from_the_predictor_projection(tmp_path):
    result = _run_post_lift(tmp_path, "hashes", BASE)
    hashed = dict(result.predictor_projection()["file_sha256"])
    assert not any(name.startswith("positive_") for name in hashed)
