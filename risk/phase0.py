"""Executable Phase 0 checks that gate all acquisition and modeling work."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from .config import BOA_QUANTIFICATION_VALUE, REFLECTANCE_BANDS, RESULTS_DIR
from .hansen import hansen_url
from .provenance import backend_provenance, base_provenance, write_json

DEFAULT_BACKEND = "https://openeo.dataspace.copernicus.eu"
DEFAULT_COMPOSITE = Path(r"C:\Users\josha\ml-data\deforestation\sites\rondonia_2016.tif")


def verify_hansen(tile: str = "00N_070W",
                  bounds: tuple[float, float, float, float] = (-63.10, -10.00, -63.08, -9.98)
                  ) -> dict[str, Any]:
    findings: dict[str, Any] = {}
    for band in ("lossyear", "treecover2000", "datamask"):
        url = hansen_url(band, tile)
        with rasterio.open(url) as dataset:
            window = from_bounds(*bounds, transform=dataset.transform).round_offsets().round_lengths()
            values = dataset.read(1, window=window)
            findings[band] = {
                "url": url.removeprefix("/vsicurl/"),
                "shape": list(values.shape), "dtype": str(values.dtype),
                "min": int(values.min()), "max": int(values.max()),
                "crs": str(dataset.crs),
            }
    if findings["treecover2000"]["min"] < 0 or findings["treecover2000"]["max"] > 100:
        raise AssertionError("treecover2000 is not in its documented 0--100 range.")
    return findings


def verify_openeo(url: str = DEFAULT_BACKEND) -> tuple[dict[str, Any], object]:
    import openeo

    connection = openeo.connect(url)
    metadata = connection.collection_metadata("SENTINEL2_L2A")
    bands = metadata.band_names
    processes = {process["id"] for process in connection.list_processes()}
    required_bands = ("SCL", "B11", "B12")
    required_processes = ("mask", "apply_kernel", "reduce_dimension", "median")
    result = {
        **backend_provenance(connection),
        "required_bands": {name: name in bands for name in required_bands},
        "required_processes": {name: name in processes for name in required_processes},
        "all_bands": bands,
    }
    if not all(result["required_bands"].values()):
        raise RuntimeError("SENTINEL2_L2A lacks a required SCL/SWIR band.")
    if not all(result["required_processes"].values()):
        raise RuntimeError("Backend lacks a process needed for manual SCL masking/dilation.")
    return result, connection


def inspect_reflectance_convention(path: str | Path) -> dict[str, Any]:
    """Classify the backend convention from an actual composite histogram.

    A substantial population below 1000 in scaled visible bands is incompatible
    with uncorrected baseline-04 DN for ordinary non-negative reflectance: those
    DN would still contain the +1000 storage offset.  Such values therefore show
    that CDSE already removed the offset while retaining the 1/10000 scale.
    """
    path = Path(path)
    with rasterio.open(path) as dataset:
        descriptions = tuple(name or f"band_{i}" for i, name in enumerate(dataset.descriptions, 1))
        histograms = {}
        pooled: list[np.ndarray] = []
        for index, name in enumerate(descriptions, 1):
            values = dataset.read(index).astype(np.float64)
            valid = np.isfinite(values)
            if dataset.nodata is not None:
                valid &= values != dataset.nodata
            sample = values[valid]
            pooled.append(sample)
            quantiles = np.percentile(sample, [0, 1, 10, 50, 90, 99, 100])
            histograms[name] = {
                key: float(value) for key, value in zip(
                    ("min", "p01", "p10", "p50", "p90", "p99", "max"), quantiles
                )
            }
        all_values = np.concatenate(pooled)
        if np.percentile(np.abs(all_values), 99) <= 2.0:
            convention = "already_reflectance"
            formula = "rho = value"
        else:
            visible = [pooled[i] for i, name in enumerate(descriptions)
                       if name in {"B02", "B03", "B04"}]
            visible_values = np.concatenate(visible or pooled)
            below_offset_fraction = float(np.mean((visible_values >= 0) & (visible_values < 1000)))
            if below_offset_fraction > 0.01:
                convention = "already_offset_integer_scaled"
                formula = f"rho = value / {int(BOA_QUANTIFICATION_VALUE)}"
            else:
                convention = "raw_baseline04_dn"
                formula = f"rho = (value - 1000) / {int(BOA_QUANTIFICATION_VALUE)}"
        return {
            "path": str(path), "dtype": list(dataset.dtypes), "nodata": dataset.nodata,
            "descriptions": list(descriptions), "histogram": histograms,
            "convention": convention, "conversion": formula,
        }


def run_phase0(composite: str | Path = DEFAULT_COMPOSITE,
               output: str | Path = RESULTS_DIR / "phase0.json") -> dict[str, Any]:
    hansen = verify_hansen()
    openeo_result, connection = verify_openeo()
    # Build the exact locked graph without executing a composite download.  A
    # graph-construction failure is therefore a Phase 0 failure, not a surprise
    # discovered after the frame has been frozen.
    from .download_timeseries import build_cubes, process_graphs
    cubes = build_cubes(
        connection,
        {"west": -63.10, "south": -10.00, "east": -63.09, "north": -9.99},
        ("2020-06-01", "2020-06-10"),
    )
    graph = process_graphs(cubes)
    validation = {name: list(connection.validate_process_graph(cube))
                  for name, cube in cubes.items()}
    if any(validation.values()):
        raise RuntimeError(f"Backend rejected a locked process graph: {validation}")
    reflectance = inspect_reflectance_convention(composite)
    payload = {
        **base_provenance(), "status": "passed", "hansen": hansen,
        "openeo": {**openeo_result, "locked_graph_smoke_test": graph,
                   "graph_validation_errors": validation},
        "reflectance": reflectance,
    }
    write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the risk study's Phase 0 assumption checks.")
    parser.add_argument("--composite", type=Path, default=DEFAULT_COMPOSITE)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "phase0.json")
    args = parser.parse_args()
    payload = run_phase0(args.composite, args.output)
    print(f"Phase 0 PASSED -> {args.output}")
    print(f"Reflectance convention: {payload['reflectance']['convention']}")


if __name__ == "__main__":
    main()
