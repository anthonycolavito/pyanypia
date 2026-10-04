"""pyanypia: Social Security benefit-formula functions, penny-exact with SSA's AnyPIA."""

from __future__ import annotations

from pyanypia.claiming import (
    benefit_factor,
    delayed_credit_factor,
    earliest_claim_age,
    early_reduction_factor,
    eligibility_year,
    monthly_benefit,
    normal_retirement_age,
    spouse_reduction_factor,
)
from pyanypia.dates import adjusted_birth, cola_year
from pyanypia.earnings import (
    aime,
    capped_earnings,
    computation_years,
    elapsed_years,
    fully_insured,
    indexed_earnings,
    quarters_of_coverage,
    years_of_coverage,
)
from pyanypia.formula import apply_colas, bend_points, family_max, family_max_bend_points, pia
from pyanypia.policy import CURRENT_LAW, Policy

__version__ = "0.3.0"

__all__ = [
    "CURRENT_LAW",
    "Policy",
    "adjusted_birth",
    "benefit_factor",
    "cola_year",
    "delayed_credit_factor",
    "earliest_claim_age",
    "early_reduction_factor",
    "eligibility_year",
    "monthly_benefit",
    "normal_retirement_age",
    "spouse_reduction_factor",
    "aime",
    "capped_earnings",
    "computation_years",
    "elapsed_years",
    "fully_insured",
    "indexed_earnings",
    "quarters_of_coverage",
    "years_of_coverage",
    "apply_colas",
    "bend_points",
    "family_max",
    "family_max_bend_points",
    "pia",
]
