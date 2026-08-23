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
        return cls(
            alt=alt,
            biproj=cls._bi_path(alt),
            awincproj=cls._aw_path(alt),
        )

    @classmethod
    def for_alternatives(cls, ialtbi: int, ialtaw: int) -> Assumptions:
        """The benefit-increase and average-wage paths chosen
        independently, as the .pia assumption line allows.

        1-3 are the Trustees Report alternatives. 5 (flat) and 6 (the old
        Statement assumptions) project no increases at all, which is what
        BiprojNonFile/AwincNonFile assign for any non-TR alternative.
        """
        return cls(
            alt=ialtbi,
            biproj=cls._bi_path(ialtbi),
            awincproj=cls._aw_path(ialtaw),
        )

    @staticmethod
    def _bi_path(alt: int) -> dict[int, float]:
        if alt not in (1, 2, 3):
            return {y: 0.0 for y in range(d.ISTART, d.MAXYEAR + 1)}
        bi = getattr(d, f"CPIINC_PROJ_ALT{alt}")
        first = getattr(d, f"CPIINC_PROJ_ALT{alt}_FIRST")
        return {first + i: v for i, v in enumerate(bi)}

    @staticmethod
    def _aw_path(alt: int) -> dict[int, float]:
        if alt not in (1, 2, 3):
            return {y: 0.0 for y in range(d.ISTART - 1, d.MAXYEAR + 1)}
        aw = getattr(d, f"FQINC_PROJ_ALT{alt}")
        first = getattr(d, f"FQINC_PROJ_ALT{alt}_FIRST")
        return {first + i: v for i, v in enumerate(aw)}
