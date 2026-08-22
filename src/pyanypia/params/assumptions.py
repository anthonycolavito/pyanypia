"""Assumption sets: Trustees Report alternatives I/II/III and user paths.

The per-alternative projected paths (AWI percentage increases and benefit
increases) come from the generated data module; a user-specified
assumption set supplies its own paths (AssumptionType::OTHER_ASSUM).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyanypia.params import _data2026 as d

ALTERN_I = 1
ALTERN_IIB = 2  # intermediate
ALTERN_III = 3


@dataclass(frozen=True)
class Assumptions:
    """Projected benefit-increase and AWI-increase paths."""

    alt: int  # 1, 2, 3, or 0 for user-specified
    biproj: dict[int, float] = field(default_factory=dict)  # year -> percent
    awincproj: dict[int, float] = field(default_factory=dict)
    catchup: dict[tuple[int, int], float] = field(default_factory=dict)
    # catchup keyed by (elig_year, year); empty in the 2026 TR

    @classmethod
    def tr_alternative(cls, alt: int) -> Assumptions:
        if alt not in (1, 2, 3):
            raise ValueError(f"alternative must be 1, 2, or 3; got {alt}")
        bi = getattr(d, f"CPIINC_PROJ_ALT{alt}")
        bi_first = getattr(d, f"CPIINC_PROJ_ALT{alt}_FIRST")
        aw = getattr(d, f"FQINC_PROJ_ALT{alt}")
        aw_first = getattr(d, f"FQINC_PROJ_ALT{alt}_FIRST")
        return cls(
            alt=alt,
            biproj={bi_first + i: v for i, v in enumerate(bi)},
            awincproj={aw_first + i: v for i, v in enumerate(aw)},
        )
