import pytest

from risk.evaluation import ConfidenceInterval, concordance_verdict


@pytest.mark.parametrize(
    ("normalized", "unnormalized", "expected"),
    [
        (ConfidenceInterval(0.01, 0.10), ConfidenceInterval(0.02, 0.20), "HISTORY ADDS VALUE"),
        (ConfidenceInterval(-0.20, -0.01), ConfidenceInterval(-0.10, -0.02), "HISTORY HARMS"),
        (ConfidenceInterval(-0.01, 0.10), ConfidenceInterval(0.0, 0.20), "NULL"),
        (ConfidenceInterval(0.01, 0.10), ConfidenceInterval(-0.01, 0.20), "INCONCLUSIVE"),
    ],
)
def test_l4_all_four_decision_rows(normalized, unnormalized, expected):
    assert concordance_verdict(normalized, unnormalized) == expected


def test_unreliable_or_undefined_forces_inconclusive():
    good = ConfidenceInterval(0.01, 0.10)
    assert concordance_verdict(good, ConfidenceInterval(None, None, "UNRELIABLE")) == "INCONCLUSIVE"
    assert concordance_verdict(ConfidenceInterval(None, None, "undefined"), good) == "INCONCLUSIVE"

