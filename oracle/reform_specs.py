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
    Age65ComputationPoint,
    ChildCareDropout,
    ColaChange,
    DiDropoutFive,
    NraChange,
    Reform,
    SpecialMinimum,
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
    # ---- child-care dropout years (CHILDCAREDROPOUT) -----------------
    ReformVariant(
        "childcare_half_awi",
        [lcw.childcare_dropout(0.5, 6, 3, 2000, 2100)],
        Reform(childcare_dropout=ChildCareDropout(
            2000, 2100, fq_ratio=0.5, max_years=3)),
        "a child-care year is one earning under half the average wage",
    ),
    ReformVariant(
        "childcare_five_years",
        [lcw.childcare_dropout(0.25, 12, 5, 2000, 2100)],
        Reform(childcare_dropout=ChildCareDropout(
            2000, 2100, fq_ratio=0.25, max_years=5)),
        "a quarter of it, and five dropout years rather than three",
    ),
    # ---- computation point (AGE65COMP) -------------------------------
    ReformVariant(
        "comp_point_63",
        [lcw.age65_comp(1, 1, 2000, 2100)],
        Reform(comp_point=Age65ComputationPoint(2000, 2100, years=1, step=1)),
        "the computation point a year later than 62",
    ),
    ReformVariant(
        "comp_point_65_phased",
        [lcw.age65_comp(3, 2, 2005, 2100)],
        Reform(comp_point=Age65ComputationPoint(2005, 2100, years=3, step=2)),
        "and at 65, a year at a time every two years of eligibility",
    ),
    # ---- special minimum (NEWSPECMIN) --------------------------------
    ReformVariant(
        "specmin_25",
        [lcw.new_special_min(25.00, 2015, 2100)],
        Reform(special_min=SpecialMinimum(2015, 2100, amount=25.00)),
        "the special minimum at $25 a year of coverage from 2015",
    ),
    ReformVariant(
        "specmin_5",
        [lcw.new_special_min(5.00, 2020, 2100)],
        Reform(special_min=SpecialMinimum(2020, 2100, amount=5.00)),
        "and at $5 from 2020, which should make it stop winning",
    ),

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


# Two of the calculator's change types are deliberately absent, and
# pyanypia.law.Reform rejects them. PiaParamsLC builds the bend-point wage
# series in its constructor, which runs before AnypiabDoc calls
# setHistFqinc(), so setFqBppia() sees a fqinc of all zeros and nothing
# recomputes it. Every eligibility year from the change onward keeps the
# bend points of the year before it began, whatever proportion was asked
# for, and where the span ends early the projection past it divides 0 by 0
# and returns NaN. The official anypiabdoc.cpp constructs PiaParamsAny in
# the same order, so this is the calculator's behaviour, not our driver's.
#
# To see it, run the oracle over these cases with
#
#     lcw.bend_point_fraction(1.0, 1990, 2100)
#
# which asks for bend points at the full wage rate and so should reproduce
# present law exactly. A 2005 eligibility comes back 1137.80 against
# present law's 1500.10, and 0.5 gives the identical figure.
UNSUPPORTED = ("BPFRACWAGE", "BPMINCONST")

BY_NAME = {v.name: v for v in VARIANTS}

# A reform's changes must all be types pyanypia claims to support, or the
# sweep is testing the oracle against a Reform that means something else.
_SUPPORTED = {"NRACHANGE", "COLACHANGE", "DIDROP5", "WAGEBASECHG",
              "NEWSPECMIN", "AGE65COMP",
              "CHILDCAREDROPOUT"}
for _v in VARIANTS:
    _unsupported = {c.name for c in _v.changes} - _SUPPORTED
    if _unsupported:
        raise AssertionError(f"{_v.name}: unsupported {sorted(_unsupported)}")
    if not _v.reform:
        raise AssertionError(f"{_v.name}: empty Reform")
