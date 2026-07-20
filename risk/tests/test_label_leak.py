import numpy as np

from risk.features import contagion_grid_features, prior_loss_cell_summaries


def test_future_loss_cannot_enter_time_since_loss():
    # The nearest-loss cell contains both 2001 and label-window 2024 loss.  Only
    # code 1 may determine recency, so the answer is 19 years rather than -4.
    cell_loss = [np.array([1, 24], dtype=np.uint8), np.array([24], dtype=np.uint8)]
    l20, maximum = prior_loss_cell_summaries(cell_loss, np.array([2, 1]))
    assert maximum.tolist() == [1, 0]

    features = contagion_grid_features(
        l20.reshape(1, 2), np.array([[2, 1]]), maximum.reshape(1, 2),
        grid_rc=np.array([[0, 0], [0, 1]]), interior=np.array([True, True]),
    )
    uncensored = features.loc[features["b_dist_censored"] == 0, "b_time_since_loss"]
    assert (uncensored >= 0).all()
    assert (uncensored <= 19).all()
    assert set(uncensored) == {19}

