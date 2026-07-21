"""Privileged GFC reader used only through :mod:`forecast.gfc_censor`.

This module deliberately has no public import-time API.  It is launched as an
isolated child, reads checksum-pinned raster tiles, and emits boolean ``.npy``
masks plus safe alignment metadata.  It never emits a value-bearing GFC array.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import Resampling, reproject

TREECOVER_THRESHOLD = 30
PRE_LIFT_MASKS = (
    "eligible_2020",
    "eligible_2021",
    "eligible_2022",
    "positive_2021",
    "positive_2022",
)
POST_LIFT_MASKS = ("eligible_2022", "positive_2023")
FORMULAS = {
    "eligible_2020": "datamask == 1 & treecover2000 >= 30 & (lossyear == 0 | lossyear > 20)",
    "eligible_2021": "datamask == 1 & treecover2000 >= 30 & (lossyear == 0 | lossyear > 21)",
    "eligible_2022": "datamask == 1 & treecover2000 >= 30 & (lossyear == 0 | lossyear > 22)",
    "positive_2021": "eligible_2020 & lossyear == 21",
    "positive_2022": "eligible_2021 & lossyear == 22",
    "positive_2023": "eligible_2022 & lossyear == 23",
}
REQUIRED_LAYERS = ("treecover2000", "datamask", "lossyear")


def _disable_crash_artifacts() -> None:
    try:
        import faulthandler

        faulthandler.disable()
    except Exception:
        pass
    if os.name == "nt":
        import ctypes

        # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
        ctypes.WinDLL("kernel32", use_last_error=True).SetErrorMode(0x0001 | 0x0002 | 0x8000)
    else:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _install_capability_guard(
    request_path: Path,
    output_dir: Path,
    raw_paths: Sequence[Path],
) -> None:
    """Deny network/process escape and non-allow-listed file access."""

    readable_files = {request_path.resolve(), *(path.resolve() for path in raw_paths)}
    runtime_roots = {
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path(np.__file__).resolve().parent,
        Path(rasterio.__file__).resolve().parent,
    }
    system_root = os.environ.get("SystemRoot")
    if system_root:
        runtime_roots.add(Path(system_root).resolve())
    output_root = output_dir.resolve()

    def audit(event: str, args: tuple[object, ...]) -> None:
        if event.startswith("socket.") or event in {
            "subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn",
            "ctypes.dlopen",
        }:
            raise PermissionError("sandbox capability denied")
        if event != "open" or not args or isinstance(args[0], int):
            return
        try:
            path = Path(os.fspath(args[0])).resolve()
        except (TypeError, ValueError, OSError):
            raise PermissionError("sandbox path denied") from None
        mode = str(args[1]) if len(args) > 1 else "r"
        writing = any(flag in mode for flag in ("w", "a", "x", "+"))
        if writing:
            if not _inside(path, output_root):
                raise PermissionError("sandbox write denied")
            return
        if path in readable_files or any(_inside(path, root) for root in runtime_roots):
            return
        raise PermissionError("sandbox read denied")

    sys.addaudithook(audit)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_request(payload: Mapping[str, Any]) -> tuple[str, tuple[float, ...], list[Path]]:
    if set(payload) != {"phase", "gfc_release", "bbox", "layers"}:
        raise ValueError("request schema mismatch")
    phase = str(payload["phase"])
    if phase not in {"pre_lift", "post_lift"}:
        raise ValueError("invalid phase")
    bbox = tuple(float(value) for value in payload["bbox"])
    if len(bbox) != 4 or not all(np.isfinite(bbox)):
        raise ValueError("invalid bbox")
    west, south, east, north = bbox
    if not west < east or not south < north:
        raise ValueError("empty bbox")
    layers = payload["layers"]
    if not isinstance(layers, dict) or tuple(sorted(layers)) != tuple(sorted(REQUIRED_LAYERS)):
        raise ValueError("layer allow-list mismatch")
    paths: list[Path] = []
    for layer in REQUIRED_LAYERS:
        records = layers[layer]
        if not isinstance(records, list) or not records:
            raise ValueError("every layer requires at least one tile")
        for record in records:
            if set(record) != {"path", "sha256"}:
                raise ValueError("tile schema mismatch")
            path = Path(record["path"]).resolve()
            expected = str(record["sha256"]).lower()
            if len(expected) != 64 or _sha256(path) != expected:
                raise ValueError("tile checksum mismatch")
            paths.append(path)
    return phase, bbox, paths


def _grid_from_first(path: Path, bbox: tuple[float, ...]) -> tuple[Any, Affine, int, int]:
    west, south, east, north = bbox
    with rasterio.open(path) as source:
        if source.count != 1 or source.crs is None:
            raise ValueError("GFC tiles must be single-band and georeferenced")
        transform = source.transform
        if not np.isclose(transform.b, 0.0) or not np.isclose(transform.d, 0.0):
            raise ValueError("rotated GFC grids are not supported")
        xres, yres = float(transform.a), float(-transform.e)
        crs = source.crs
    if xres <= 0 or yres <= 0:
        raise ValueError("invalid raster resolution")
    width_float = (east - west) / xres
    height_float = (north - south) / yres
    width, height = int(round(width_float)), int(round(height_float))
    if not np.isclose(width_float, width, atol=1e-7) or not np.isclose(
        height_float, height, atol=1e-7
    ):
        raise ValueError("bbox is not aligned to the GFC grid")
    return crs, Affine(xres, 0.0, west, 0.0, -yres, north), height, width


def _mosaic_layer(
    records: Sequence[Mapping[str, str]],
    *,
    crs: Any,
    transform: Affine,
    shape: tuple[int, int],
) -> np.ndarray:
    mosaic = np.full(shape, 255, dtype=np.uint8)
    covered = np.zeros(shape, dtype=bool)
    for record in records:
        path = Path(record["path"]).resolve()
        with rasterio.open(path) as source:
            if source.count != 1 or source.crs != crs:
                raise ValueError("layer CRS/count mismatch")
            if not np.isclose(source.transform.a, transform.a) or not np.isclose(
                source.transform.e, transform.e
            ):
                raise ValueError("layer resolution mismatch")
            x_offset = (source.transform.c - transform.c) / transform.a
            y_offset = (transform.f - source.transform.f) / (-transform.e)
            if not np.isclose(x_offset, round(x_offset), atol=1e-7) or not np.isclose(
                y_offset, round(y_offset), atol=1e-7
            ):
                raise ValueError("layer grid alignment mismatch")
            source_values = source.read(1)
            if np.any(source_values == 255):
                raise ValueError("reserved coverage sentinel present in source")
            projected = np.full(shape, 255, dtype=np.uint8)
            reproject(
                source_values,
                projected,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform,
                dst_crs=crs,
                dst_nodata=255,
                resampling=Resampling.nearest,
                init_dest_nodata=True,
            )
        valid = projected != 255
        overlap = valid & covered
        if np.any(overlap & (mosaic != projected)):
            raise ValueError("overlapping tiles disagree")
        mosaic[valid] = projected[valid]
        covered |= valid
    if not covered.all():
        raise ValueError("required tile coverage is incomplete")
    return mosaic


def _derive_masks(phase: str, arrays: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    treecover = arrays["treecover2000"]
    datamask = arrays["datamask"]
    lossyear = arrays["lossyear"]
    base = (datamask == 1) & (treecover >= TREECOVER_THRESHOLD)
    eligible = {
        year: base & ((lossyear == 0) | (lossyear > year - 2000))
        for year in (2020, 2021, 2022)
    }
    masks = {
        "eligible_2020": eligible[2020],
        "eligible_2021": eligible[2021],
        "eligible_2022": eligible[2022],
        "positive_2021": eligible[2020] & (lossyear == 21),
        "positive_2022": eligible[2021] & (lossyear == 22),
        "positive_2023": eligible[2022] & (lossyear == 23),
    }
    names = PRE_LIFT_MASKS if phase == "pre_lift" else POST_LIFT_MASKS
    return {name: np.asarray(masks[name], dtype=bool) for name in names}


def _run(request_path: Path, output_dir: Path) -> None:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    # Validate once to discover raw paths, then install the capability guard and
    # validate again so checksum reads also happen inside the guard.
    _, _, raw_paths = _validate_request(payload)
    _install_capability_guard(request_path, output_dir, raw_paths)
    phase, bbox, _ = _validate_request(payload)
    layers = payload["layers"]
    first_path = Path(layers["treecover2000"][0]["path"]).resolve()
    crs, transform, height, width = _grid_from_first(first_path, bbox)
    arrays = {
        layer: _mosaic_layer(
            layers[layer], crs=crs, transform=transform, shape=(height, width)
        )
        for layer in REQUIRED_LAYERS
    }
    masks = _derive_masks(phase, arrays)
    output_dir.mkdir(parents=False, exist_ok=False)
    for name, values in masks.items():
        with (output_dir / f"{name}.npy").open("wb") as stream:
            np.save(stream, values, allow_pickle=False)
    handoff = {
        "phase": phase,
        "gfc_release": str(payload["gfc_release"]),
        "treecover_threshold": TREECOVER_THRESHOLD,
        "shape": [height, width],
        "crs": crs.to_string(),
        "transform": list(transform)[:6],
        "masks": {
            name: {
                "file": f"{name}.npy",
                "dtype": "bool",
                "formula": FORMULAS[name],
            }
            for name in masks
        },
    }
    (output_dir / "handoff.json").write_text(
        json.dumps(handoff, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    _disable_crash_artifacts()
    if len(sys.argv) != 3:
        os._exit(70)
    try:
        _run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    except BaseException:
        # No child exception text is allowed to reach the observable transcript.
        os._exit(70)


if __name__ == "__main__":
    main()

