"""The reform variants the `reform_v1` sweep runs.

Each variant is defined once, in both dialects at the same time: the
`lawchg.dat` changes the calculator reads, and the `pyanypia.law.Reform`
that is supposed to mean the same thing. The differential test asserts
they agree, so pairing them here is what makes the test meaningful --
two separate lists would drift and still pass.

Spans are chosen to exercise the boundaries that matter. Of the six
supported change types only COLACHANGE consults `LawChange::isEffective`;
the rest key on the indicator alone or on conditions of their own, so
for those a narrow span tests the parameter series resuming present-law
growth after the change rather than the change switching off.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

ORACLE = pathlib.Path(__file__).resolve().parent
if str(ORACLE) not in sys.path:
    sys.path.insert(0, str(ORACLE))

import lawchg_writer as lcw  # noqa: E402

from pyanypia.law import (  # noqa: E402
    FOR_EVERYONE,
    BendPointFraction,
    BendPointMinusConstant,
    ColaChange,
    DiDropoutFive,
    NraChange,
    Reform,
    WageBaseChange,
)

_PARAMS = json.load(open(ORACLE / "goldens" / "params_alt2.json"))
_BASE = {
    int(y): v["base_oasdi"]
    for y, v in _PARAMS["years"].items()
    if v["base_oasdi"] is not None
}

# Ad hoc wage bases. The hike doubles the present-law base over a decade
# so that even max earners' AIMEs move; the freeze holds it flat, which
# moves them the other way. Both end before the projection resumes.
_WB_FIRST, _WB_LAST = 2015, 2030
_HIKE = {y: round(2.0 * _BASE[y], 2) for y in range(_WB_FIRST, _WB_LAST + 1)}
_FREEZE = {y: _BASE[_WB_FIRST] for y in range(_WB_FIRST, _WB_LAST + 1)}


@dataclass(frozen=True)
class ReformVariant:
    """One reform, in both dialects."""

    name: str
    changes: list[lcw.Change]
    reform: Reform
    note: str

    def lawchg(self) -> str:
        return lcw.write_lawchg(self.changes, title=f"reform_v1 {self.name}")


VARIANTS: list[ReformVariant] = [
    # ---- full retirement age (NRACHANGE) -----------------------------
    ReformVariant(
        "nra_hold_65",
        [lcw.nra_change(1, 1990, 2100)],
        Reform(nra=NraChange(1990, 2100, variant=1)),
        "full retirement age never leaves 65",
    ),
    ReformVariant(
        "nra_no_plateau",
        [lcw.nra_change(2, 1990, 2100)],
        Reform(nra=NraChange(1990, 2100, variant=2)),
        "the 66-to-67 plateau removed, stopping at 67",
    ),
    ReformVariant(
        "nra_indexed",
        [lcw.nra_change(3, 1990, 2100)],
        Reform(nra=NraChange(1990, 2100, variant=3)),
        "and rising a month every two years after 2011",
    ),
    # ---- benefit increases (COLACHANGE) ------------------------------
    ReformVariant(
        "cola_minus_half",
        [lcw.cola_change(-0.5, 1990, 2100, phase_type=FOR_EVERYONE)],
        Reform(cola=ColaChange(1990, 2100, FOR_EVERYONE, adjustment=-0.5)),
        "every benefit increase half a point smaller",
    ),
    ReformVariant(
        "cola_minus_one_window",
        [lcw.cola_change(-1.0, 2015, 2025, phase_type=FOR_EVERYONE)],
        Reform(cola=ColaChange(2015, 2025, FOR_EVERYONE, adjustment=-1.0)),
        "a point smaller, but only for 2015-2025",
    ),
    # ---- dropout years (DIDROP5) -------------------------------------
    ReformVariant(
        "didrop5",
        [lcw.di_dropout_five(1990, 2100)],
        Reform(di_dropout_five=DiDropoutFive(1990, 2100)),
        "five dropout years instead of one per five",
    ),
    ReformVariant(
        "didrop5_from_2010",
        [lcw.di_dropout_five(2010, 2100)],
        Reform(di_dropout_five=DiDropoutFive(2010, 2100)),
        "the same, entitlements from 2010 on",
    ),
    # ---- contribution and benefit base (WAGEBASECHG) -----------------
    ReformVariant(
        "base_doubled",
        [lcw.wage_base_change(_HIKE, _WB_FIRST, _WB_LAST,
                              phase_type=FOR_EVERYONE)],
        Reform(wage_base=WageBaseChange(_WB_FIRST, _WB_LAST, FOR_EVERYONE,
                                        bases=_HIKE)),
        "the taxable maximum doubled for 2015-2030",
    ),
    ReformVariant(
        "base_frozen",
        [lcw.wage_base_change(_FREEZE, _WB_FIRST, _WB_LAST,
                              phase_type=FOR_EVERYONE)],
        Reform(wage_base=WageBaseChange(_WB_FIRST, _WB_LAST, FOR_EVERYONE,
                                        bases=_FREEZE)),
        "and held flat at its 2015 value instead",
    ),
]


# Two supported change types cannot be validated against this oracle at
# all. PiaParamsLC builds the bend-point wage series in its constructor,
# which runs before AnypiabDoc calls setHistFqinc(), so setFqBppia() sees
# a fqinc series of all zeros and nothing ever recomputes it. Every
# eligibility year from the start of the change onward therefore gets the
# bend points of the year before it began, whatever proportion was asked
# for -- a proportion of 1.0, which should reproduce present law exactly,
# moves a 2005 eligibility from 1500.10 to 1137.80 -- and where the span
# ends early the projection past it divides 0 by 0 and returns NaN.
#
# The official anypiabdoc.cpp constructs PiaParamsAny in the same order,
# so this is the calculator's behaviour rather than our instrumentation.
# pyanypia implements what the C++ intends, off properly projected wages,
# and so cannot agree with it. These stay defined, and out of the sweep.
UNVALIDATABLE: list[ReformVariant] = [
    ReformVariant(
        "bp_half_wage",
        [lcw.bend_point_fraction(0.5, 1990, 2100)],
        Reform(bend_point_fraction=BendPointFraction(1990, 2100,
                                                     proportion=0.5)),
        "bend points growing at half the wage rate",
    ),
    ReformVariant(
        "bp_three_quarter_window",
        [lcw.bend_point_fraction(0.75, 2010, 2040)],
        Reform(bend_point_fraction=BendPointFraction(2010, 2040,
                                                     proportion=0.75)),
        "three quarters of it for 2010-2040, then wages again",
    ),
    ReformVariant(
        "bp_wage_minus_half",
        [lcw.bend_point_minus_constant(0.5, 1990, 2100)],
        Reform(bend_point_minus=BendPointMinusConstant(1990, 2100,
                                                       constant=0.5)),
        "bend points growing at wages less half a point",
    ),
    ReformVariant(
        "bp_wage_minus_one_window",
        [lcw.bend_point_minus_constant(1.0, 2010, 2040)],
        Reform(bend_point_minus=BendPointMinusConstant(2010, 2040,
                                                       constant=1.0)),
        "less a full point for 2010-2040, then wages again",
    ),
]

BY_NAME = {v.name: v for v in [*VARIANTS, *UNVALIDATABLE]}

# A reform's changes must all be types pyanypia claims to support, or the
# sweep is testing the oracle against a Reform that means something else.
_SUPPORTED = {
    "NRACHANGE", "COLACHANGE", "BPFRACWAGE", "BPMINCONST", "DIDROP5",
    "WAGEBASECHG",
}
for _v in [*VARIANTS, *UNVALIDATABLE]:
    _unsupported = {c.name for c in _v.changes} - _SUPPORTED
    if _unsupported:
        raise AssertionError(f"{_v.name}: unsupported {sorted(_unsupported)}")
    if not _v.reform:
        raise AssertionError(f"{_v.name}: empty Reform")
