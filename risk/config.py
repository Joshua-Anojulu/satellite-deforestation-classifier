"""Frozen configuration for the within-frontier risk study.

Every numeric choice in this module comes from PLAN.md section L.  Keeping the
values here makes accidental tuning visible in review and keeps large artifacts
outside the OneDrive checkout.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(
    os.environ.get("RISK_DATA_ROOT", r"C:\Users\josha\ml-data\deforestation-risk")
)
RAW_DIR = DATA_ROOT / "composites"
HANSEN_DIR = DATA_ROOT / "hansen"
FRAME_DIR = DATA_ROOT / "frame"
EXTERNAL_DIR = DATA_ROOT / "external"
PROCESSED_DIR = DATA_ROOT / "processed"
RESULTS_DIR = DATA_ROOT / "results"

SEED = 42
FEATURE_YEARS = (2016, 2017, 2018, 2019, 2020)
REFERENCE_YEAR = 2020
LABEL_YEARS = (2021, 2022, 2023, 2024)

REFLECTANCE_BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")
VISIBLE_NIR_BANDS = ("B02", "B03", "B04", "B08")
SWIR_BANDS = ("B11", "B12")
SCL_MASKED_CLASSES = (0, 1, 2, 3, 8, 9, 10, 11)
SCL_KEPT_CLASSES = (4, 5, 6, 7)
SCL_DILATION_KERNEL = 5
MAX_CLOUD_COVER = 80

BOA_QUANTIFICATION_VALUE = 10_000.0
BOA_ADD_OFFSET_BASELINE_04 = -1_000.0
MAX_OUT_OF_RANGE_FRACTION = 0.01

CELL_SIZE_M = 640
PATCH_PIXELS = 64
STRIDE_PIXELS = 64
BUFFER_M = 4_000
NEIGHBORHOOD_RADIUS_M = 1_920
DISTANCE_CAP_M = 4_000

MIN_MEDIAN_CLEAR_OBS = 8
MIN_CELL_MEDIAN_CLEAR_OBS = 3
MIN_GOOD_CELL_FRACTION = 0.95
MAX_NODATA_FRACTION = 0.05
MIN_PIF_PIXELS = 5_000
PIF_CLEAR_OBS_MIN = 5
PIF_MAX_SAMPLE = 200_000
NORMALIZATION_GAIN_BOUNDS = (0.5, 2.0)
NORMALIZATION_OFFSET_BOUNDS = (-0.1, 0.1)

TREECOVER_THRESHOLD = 30
PIF_TREECOVER_THRESHOLD = 70
AT_RISK_LAND_FRACTION = 0.25
PRIMARY_LABEL_THRESHOLD = 0.25
LABEL_SENSITIVITIES = (0.10, 0.50)
MIN_SUPPORT_PIXELS = 20

LR_C_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)
GBM_GRID = (
    {"learning_rate": 0.05, "max_leaf_nodes": 7, "min_samples_leaf": 100,
     "l2_regularization": 10.0, "max_iter": 400},
    {"learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 50,
     "l2_regularization": 1.0, "max_iter": 300},
    {"learning_rate": 0.10, "max_leaf_nodes": 15, "min_samples_leaf": 50,
     "l2_regularization": 1.0, "max_iter": 200},
    {"learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 20,
     "l2_regularization": 1.0, "max_iter": 300},
    {"learning_rate": 0.10, "max_leaf_nodes": 31, "min_samples_leaf": 20,
     "l2_regularization": 0.1, "max_iter": 200},
)
MIN_VALID_INNER_FOLDS = 4

MORAN_MAX_LAG = 20
MORAN_MIN_PAIRS = 500
MORAN_THRESHOLD = 0.1
MIN_BLOCK_SIZE = 2
MAX_RELIABLE_BLOCK_SIZE = 12
SITE_BOOTSTRAP_REPLICATES = 1_000
HIERARCHICAL_BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_MAX_DRAW_MULTIPLIER = 10
MAX_ZERO_POSITIVE_FRACTION = 0.20
ALERT_BUDGETS = (0.01, 0.05, 0.10)

LATTICE_ORIGIN = (-180.0, 23.5)
LATTICE_STEP = (0.25, 0.22)
LATTICE_BOX_SIZE = (0.25, 0.22)
MAX_FRAME_LATITUDE = 23.5
FRAME_GROUP_ORDER = ("amazon_moist", "congo_moist", "dry_forest", "sea_peat")
FRAME_SITES_PER_GROUP = 3
FRAME_MIN_SEPARATION_KM = 50.0
FRAME_VALID_LAND_MIN = 0.95
# AMENDMENT-1 (2026-07-13, disclosed protocol deviation -- see PLAN.md).
# The original box-level rule was FRAME_ELIGIBLE_FOREST_MIN = 0.50. It excluded 5 of the 8
# legacy boxes -- all three Amazon sites, Riau and Gran Chaco -- purely for being ALREADY
# heavily cleared (23.5-38.1% eligible forest), while every one of them cleared the activity
# criteria comfortably. That bar selects for EARLY-stage frontiers, which is perverse for a
# study of active ones, and it would have biased the 12 unseen frame boxes identically.
#
# Replaced by a minimum at-risk-cell count. NOTE HONESTLY: this is NOT a redundancy fix --
# it CHANGES THE ESTIMAND from "forest-dominated frontiers" to "active-frontier landscapes
# with residual at-risk forest". 300 is a permissive OPERATIONAL SUPPORT FLOOR ONLY: it makes
# no bootstrap or AP-viability guarantee (L7's usable-block-placement rule decides that), and
# it was chosen after observing the legacy count range, so it is not prespecified.
FRAME_MIN_AT_RISK_CELLS = 300
FRAME_CUMULATIVE_LOSS_MIN = 0.02
FRAME_RECENT_LOSS_MIN = 0.005
FRAME_REQUIRED = 12
COMBINED_MINIMUM = 14

MOIST_BIOME_NAME = "Tropical & Subtropical Moist Broadleaf Forests"
DRY_BIOME_NAME = "Tropical & Subtropical Dry Broadleaf Forests"

# The eight outcome-informed boxes retained by the frozen plan.  Kalimantan is
# not in this cohort: it was excluded before the plan was locked.
LEGACY_SITES = {
    "rondonia": {"bbox": {"west": -63.10, "south": -10.00, "east": -62.85, "north": -9.78},
                  "group": "amazon_moist"},
    "sao_felix_xingu": {"bbox": {"west": -52.10, "south": -6.70, "east": -51.85, "north": -6.48},
                        "group": "amazon_moist"},
    "mato_grosso": {"bbox": {"west": -55.40, "south": -12.55, "east": -55.15, "north": -12.30},
                     "group": "amazon_moist"},
    "tshopo_drc": {"bbox": {"west": 24.90, "south": 0.30, "east": 25.15, "north": 0.55},
                   "group": "congo_moist"},
    "mai_ndombe_drc": {"bbox": {"west": 18.40, "south": -2.55, "east": 18.65, "north": -2.30},
                       "group": "congo_moist"},
    "riau_sumatra": {"bbox": {"west": 101.40, "south": 0.30, "east": 101.65, "north": 0.55},
                     "group": "sea_peat"},
    "santa_cruz_bolivia": {"bbox": {"west": -61.90, "south": -16.90, "east": -61.65, "north": -16.70},
                            "group": "dry_forest"},
    "gran_chaco_paraguay": {"bbox": {"west": -60.35, "south": -22.30, "east": -60.10, "north": -22.05},
                            "group": "dry_forest"},
}

EXPECTED_LEGACY_WINDOWS = {
    "rondonia": (6, 9), "sao_felix_xingu": (6, 9), "mato_grosso": (6, 9),
    "tshopo_drc": (6, 8), "mai_ndombe_drc": (6, 8), "riau_sumatra": (5, 9),
    "santa_cruz_bolivia": (5, 9), "gran_chaco_paraguay": (5, 9),
}


def assert_feature_years(years: object) -> tuple[int, ...]:
    """Reject any imagery year after 2020 before feature code can read it."""
    result = tuple(int(y) for y in years)
    if not result:
        raise ValueError("At least one feature year is required.")
    if max(result) > REFERENCE_YEAR:
        raise AssertionError(f"Feature years must be <= {REFERENCE_YEAR}: {result}")
    return result

