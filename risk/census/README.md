# Label-blind census scripts

Read-only feasibility censuses behind `paper/pif_infeasibility_finding.md` and the AMENDMENT-4
review (`PLAN-REVIEW-LOG.md`). All are label-blind (<=2020 inputs only), Hansen-only, download no
imagery, and write nothing into the study tree.

Run with the project root on PYTHONPATH:

    $env:PYTHONPATH = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier"
    & $py risk\census\pif_census_halo.py <frame>\analysis_sites.json

| Script | Purpose |
|---|---|
| `pif_census.py` | PIF feasibility per site. **Superseded — no halo (biased).** Kept for the comparison. |
| `pif_census_halo.py` | **Canonical.** Same, with the >=1,920 m Hansen halo. Prints both, and the verdict flips. |
| `pif_diagnosis.py` | Readings A/B/D, prior-loss cluster structure, treecover sensitivity. |
| `queue_census.py` | L13.5 replacement-queue survival over a fixed rank-order prefix (halo, no stopping rule). |
| `control_census.py` | D2.2 control census: vegetation vs permanent water. Shows water at only 10/19 sites. |
| `control_census2.py` | Disjoint veg_near/veg_far control feasibility (19/19). `tree>=30` variant via the constant at the top. |
| `rondonia_distance_halo.py` | Distance distribution, halo vs no-halo. Produces the figures cited in §3/§5.1. |

**Distance figures must come from a halo path.** The no-halo variants are retained ONLY to
demonstrate the bias they cause; `pif_census.py` overstates every count and flips one site's verdict.

Caveats that belong with the numbers: queue survival uses a fixed 40-box prefix, not the complete
frame, and does not apply the L13.4 >=50 km separation check, so its rates are UPPER BOUNDS. The
`>=53 px` block-occupancy threshold in the control censuses is **not derived** — it was chosen ad hoc
and must be locked from a power calculation before any figure depending on it is published.
