"""The unchanged v11 detector-audit allocator, parameterized by site populations.

Both 12-site v11 and Specification W use ``n_b = 180``.  W merely supplies nine
site strata per biome instead of three; the census/floor/cap/redistribution rules
and finite-population correction are identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .specification_w import AUDIT_BUDGET_PER_BIOME


@dataclass(frozen=True)
class AuditAllocation:
    allocations: Mapping[str, int]
    populations: Mapping[str, int]
    requested_budget: int
    effective_budget: int
    realised_total: int
    census_sites: tuple[str, ...]
    zero_population_sites: tuple[str, ...]
    floor_overage: int


def largest_remainder_with_caps(
    capacities: Mapping[str, int], total: int
) -> dict[str, int]:
    """Allocate ``total`` proportionally, cap, and iteratively redistribute."""

    remaining = {str(site): int(capacity) for site, capacity in capacities.items()}
    if any(capacity < 0 for capacity in remaining.values()) or total < 0:
        raise ValueError("capacities and total must be non-negative")
    if total > sum(remaining.values()):
        raise ValueError("allocation exceeds total remaining capacity")
    result = {site: 0 for site in remaining}
    left = int(total)
    active = {site for site, capacity in remaining.items() if capacity > 0}
    while left and active:
        capacity_total = sum(remaining[site] for site in active)
        if capacity_total <= 0:
            raise AssertionError("positive allocation remains without capacity")
        quotas = {
            site: left * remaining[site] / capacity_total for site in active
        }
        bases = {
            site: min(remaining[site], int(np.floor(quotas[site]))) for site in active
        }
        assigned = sum(bases.values())
        for site, amount in bases.items():
            result[site] += amount
            remaining[site] -= amount
        left -= assigned
        active = {site for site in active if remaining[site] > 0}
        if not left:
            break
        # Largest fractional remainders; exact ties go to ascending site id.
        order = sorted(active, key=lambda site: (-(quotas[site] - bases[site]), site))
        if not order:
            raise AssertionError("largest-remainder redistribution exhausted")
        progressed = False
        for site in order:
            if not left:
                break
            if remaining[site] <= 0:
                continue
            result[site] += 1
            remaining[site] -= 1
            left -= 1
            progressed = True
        active = {site for site in active if remaining[site] > 0}
        if not progressed and left:
            raise AssertionError("largest-remainder redistribution stalled")
    if sum(result.values()) != total or any(
        result[site] > int(capacities[site]) for site in result
    ):
        raise AssertionError("invalid capped allocation")
    return result


def allocate_detector_audit(
    populations: Mapping[str, int],
    budget: int = AUDIT_BUDGET_PER_BIOME,
) -> AuditAllocation:
    """Apply the frozen census -> floor -> largest-remainder allocation order."""

    if budget < 0:
        raise ValueError("budget must be non-negative")
    canonical = {str(site): int(value) for site, value in populations.items()}
    if any(value < 0 for value in canonical.values()):
        raise ValueError("site populations must be non-negative")
    allocations = {site: 0 for site in canonical}
    zero_sites = tuple(sorted(site for site, value in canonical.items() if value == 0))
    positive = {site: value for site, value in canonical.items() if value > 0}

    census = {site for site, value in positive.items() if value <= 5}
    for site in census:
        allocations[site] = positive[site]
    used = sum(allocations.values())
    effective_budget = max(int(budget), used)
    remaining_sites = {site: value for site, value in positive.items() if site not in census}
    remaining_budget = effective_budget - used

    if sum(remaining_sites.values()) <= remaining_budget:
        for site, value in remaining_sites.items():
            allocations[site] = value
            census.add(site)
    elif remaining_sites:
        floor_total = 2 * len(remaining_sites)
        if remaining_budget < floor_total:
            effective_budget += floor_total - remaining_budget
            remaining_budget = floor_total
        for site in remaining_sites:
            allocations[site] = 2
        extra = remaining_budget - floor_total
        capacities = {site: value - 2 for site, value in remaining_sites.items()}
        additions = largest_remainder_with_caps(capacities, extra)
        for site, amount in additions.items():
            allocations[site] += amount
            if allocations[site] == canonical[site]:
                census.add(site)

    realised = sum(allocations.values())
    if realised > effective_budget:
        raise AssertionError("audit allocation exceeded its effective budget")
    for site, population in positive.items():
        allocation = allocations[site]
        if allocation > population:
            raise AssertionError("site allocation exceeded its population")
        if allocation < population and allocation < 2:
            raise AssertionError("non-census stratum fell below the frozen floor")
    return AuditAllocation(
        allocations=dict(sorted(allocations.items())),
        populations=dict(sorted(canonical.items())),
        requested_budget=int(budget),
        effective_budget=effective_budget,
        realised_total=realised,
        census_sites=tuple(sorted(census)),
        zero_population_sites=zero_sites,
        floor_overage=max(0, effective_budget - int(budget)),
    )


def finite_population_correction(population: int, sample: int) -> float:
    """Return ``1 - n/N``; empty and census strata contribute zero."""

    population, sample = int(population), int(sample)
    if population < 0 or sample < 0 or sample > population:
        raise ValueError((population, sample))
    if population == 0:
        return 0.0
    return 1.0 - sample / population


def stratified_ratio_variance(
    populations: Mapping[str, int],
    allocations: Mapping[str, int],
    residual_variances: Mapping[str, float],
    denominator: float,
) -> float:
    """Frozen Taylor-linearized ratio variance with site-level FPC."""

    if not np.isfinite(denominator) or denominator == 0:
        raise ValueError("ratio denominator must be finite and nonzero")
    if set(populations) != set(allocations) or set(populations) != set(residual_variances):
        raise ValueError("variance inputs must contain identical site strata")
    total = 0.0
    for site in sorted(populations):
        population = int(populations[site])
        sample = int(allocations[site])
        variance = float(residual_variances[site])
        if population == 0 or sample == population:
            continue
        if sample < 2:
            raise ValueError("non-census sample variance requires n >= 2")
        if variance < 0 or not np.isfinite(variance):
            raise ValueError("residual variances must be finite and non-negative")
        total += (
            finite_population_correction(population, sample)
            * (population ** 2 / sample)
            * variance
        )
    return float(total / denominator ** 2)

