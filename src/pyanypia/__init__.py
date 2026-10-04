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
from pyanypia.convenience import (
    Benefit,
    deceased_worker,
    disabled_worker,
    retired_worker,
    widow_guarantee_pia,
)
from pyanypia.dates import adjusted_birth, cola_year
from pyanypia.disability import childcare_aime, di_family_max
from pyanypia.earnings import (
    aime,
    capped_earnings,
    computation_years,
    disability_insured,
    elapsed_years,
    fully_insured,
    indexed_earnings,
    quarters_of_coverage,
    years_of_coverage,
)
from pyanypia.family import Auxiliary, FamilyBenefits, family_benefits
from pyanypia.formula import apply_colas, bend_points, family_max, family_max_bend_points, pia
from pyanypia.minimum import special_minimum_pia
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.wep import gpo_offset, wep_pia

__version__ = "0.3.1"

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
    "Benefit",
    "retired_worker",
    "special_minimum_pia",
    "childcare_aime",
    "di_family_max",
    "disabled_worker",
    "disability_insured",
    "Auxiliary",
    "FamilyBenefits",
    "deceased_worker",
    "family_benefits",
    "widow_guarantee_pia",
    "gpo_offset",
    "wep_pia",
]
