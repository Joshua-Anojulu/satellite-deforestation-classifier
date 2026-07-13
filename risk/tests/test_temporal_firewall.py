import numpy as np
from affine import Affine

import risk.frame as frame
import risk.hansen as hansen
from risk.frame import Candidate, screen_candidate


def test_frame_reader_never_exposes_lossyear_above_20(monkeypatch):
    raw_loss = np.array([[0, 1, 16], [20, 21, 24]], dtype=np.uint8)
    transform = Affine(0.00025, 0, 0, 0, -0.00025, 1)

    def fake_read(band, tile, bounds, opener):
        if band == "lossyear":
            values = raw_loss.copy()
        elif band == "treecover2000":
            values = np.full(raw_loss.shape, 100, dtype=np.uint8)
        else:
            values = np.ones(raw_loss.shape, dtype=np.uint8)
        return values, transform, "EPSG:4326"

    monkeypatch.setattr(hansen, "_read_tile_band", fake_read)
    values, _, _ = hansen._read_frame_tile("00N_000E", (0, 0, 1, 1), opener=object())
    assert "lossyear" not in values
    assert values["prior"].dtype == np.bool_
    assert values["recent"].dtype == np.bool_
    assert values["prior"].tolist() == [[False, True, True], [True, False, False]]
    assert values["recent"].tolist() == [[False, False, True], [True, False, False]]


def test_frame_activity_shares_use_valid_land_not_treecover_universe(monkeypatch):
    """L13.3 activity shares divide by VALID LAND, not by the treecover universe U.

    The at-risk floor (AMENDMENT-1) is a separate criterion and is neutralised here so
    this test isolates the denominator question. The floor has its own test below.
    """
    monkeypatch.setattr(frame, "FRAME_MIN_AT_RISK_CELLS", 0)
    transform = Affine(0.5, 0, 0, 0, -0.5, 1)
    window = hansen.FrameHansenWindow(
        datamask=np.ones((2, 2), dtype=np.uint8),
        # The one loss is deliberately on a <30 treecover pixel. L13.3 still
        # counts it in cumulative/recent loss divided by valid land.
        treecover2000=np.array([[0, 100], [100, 100]], dtype=np.uint8),
        prior_loss_2001_2020=np.array([[True, False], [False, False]]),
        recent_loss_2016_2020=np.array([[True, False], [False, False]]),
        transform=transform, crs="EPSG:4326",
    )
    candidate = Candidate("x", "amazon_moist", 0.5, 0.5, 0, 0, 1, 1)
    screened = screen_candidate(candidate, reader=lambda _: window)
    assert screened is not None
    assert screened.cumulative_loss_share == 0.25
    assert screened.recent_loss_share == 0.25


def _uniform_window(rows: int, cols: int, treecover: int, prior: bool = False):
    return hansen.FrameHansenWindow(
        datamask=np.ones((rows, cols), dtype=np.uint8),
        treecover2000=np.full((rows, cols), treecover, dtype=np.uint8),
        prior_loss_2001_2020=np.full((rows, cols), prior),
        recent_loss_2016_2020=np.zeros((rows, cols), dtype=bool),
        transform=Affine(0.00025, 0, 0, 0, -0.00025, 1), crs="EPSG:4326",
    )


def test_at_risk_floor_counts_cells_and_rejects_thin_support(monkeypatch):
    """AMENDMENT-1's floor counts L5 at-risk cells and gates on >= FRAME_MIN_AT_RISK_CELLS."""
    inside = np.ones((105, 105), dtype=bool)          # 5x5 = 25 cells of 21x21 native pixels
    forested = _uniform_window(105, 105, treecover=100)
    assert frame.count_at_risk_cells(forested, inside) == 25

    # Same box, but every pixel already cleared before 2021 -> no eligible forest -> no at-risk cells.
    cleared = _uniform_window(105, 105, treecover=100, prior=True)
    assert frame.count_at_risk_cells(cleared, inside) == 0

    # Below-threshold canopy is not eligible forest either.
    sparse = _uniform_window(105, 105, treecover=10)
    assert frame.count_at_risk_cells(sparse, inside) == 0

    # A box that clears every OTHER L13.3 criterion: forested, with a 10% prior-loss stripe
    # (>=2% cumulative) of which the last rows are recent (>=0.5%).
    active = _uniform_window(105, 105, treecover=100)
    active.prior_loss_2001_2020[:11, :] = True     # ~10.5% of valid land
    active.recent_loss_2016_2020[:2, :] = True     # ~1.9% of valid land
    candidate = Candidate("x", "amazon_moist", 0.5, 0.5, 0, 0, 1, 1)

    # The floor GATES: this box has fewer at-risk cells than the locked 300 minimum.
    monkeypatch.setattr(frame, "FRAME_MIN_AT_RISK_CELLS", 300)
    assert screen_candidate(candidate, reader=lambda _: active) is None

    # ...and ADMITS it once the floor is met, proving the floor -- not some other
    # criterion -- was the binding constraint.
    monkeypatch.setattr(frame, "FRAME_MIN_AT_RISK_CELLS", 5)
    admitted = screen_candidate(candidate, reader=lambda _: active)
    assert admitted is not None
    assert admitted.at_risk_cells >= 5


def test_at_risk_floor_never_reads_future_loss():
    """The floor must count AT-RISK cells, never POSITIVE cells (outcome-informed selection)."""
    inside = np.ones((105, 105), dtype=bool)
    window = _uniform_window(105, 105, treecover=100)
    # FrameHansenWindow exposes no future-loss array at all -- the firewall is structural.
    assert not hasattr(window, "lossyear")
    assert not any("2021" in field or "future" in field
                   for field in window.__dataclass_fields__)
    assert frame.count_at_risk_cells(window, inside) == 25
