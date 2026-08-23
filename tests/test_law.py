"""The reform layer's public behaviour."""

from __future__ import annotations

from datetime import date

import pytest

import pyanypia as pia
from pyanypia.law import (
    BendPointFraction,
    BendPointMinusConstant,
    ColaChange,
    Law,
    NraChange,
    Reform,
)

WORKER = pia.Worker(
    dob=date(1960, 3, 15),
    sex=pia.Sex.FEMALE,
    benefit_type=pia.BenefitType.OLD_AGE,
    earnings={year: 52_000.0 for year in range(1985, 2026)},
    entitlement=pia.MonthYear(2027, 4),
)


@pytest.mark.parametrize(
    "field,change",
    [
        ("bend_point_fraction", BendPointFraction(1990, 2100, proportion=0.5)),
        ("bend_point_minus", BendPointMinusConstant(1990, 2100, constant=0.5)),
    ],
)
def test_bend_point_reforms_are_refused(field: str, change: object) -> None:
    """The calculator cannot compute these, so neither will we -- and a
    reform that is quietly ignored is worse than one that is refused."""
    with pytest.raises(ValueError, match="bend-point reforms are not"):
        Reform(**{field: change})


def test_compare_without_a_reform_is_a_baseline() -> None:
    c = pia.compare(WORKER)
    assert c.baseline is c.reformed
    assert c.pia_change == 0.0
    assert c.benefit_change == 0.0


def test_compare_applies_the_reform() -> None:
    """Holding the full retirement age at 65 leaves this worker's PIA
    alone and turns their claim into fifteen months of credit."""
    c = pia.compare(WORKER, Reform(nra=NraChange(1990, 2100, variant=1)))
    assert c.pia_change == 0.0
    assert c.benefit_change > 0.0
    assert "PIA" in c.detail()


def test_compare_rejects_a_non_reform() -> None:
    with pytest.raises(TypeError, match="must be a pyanypia.law.Reform"):
        pia.compare(WORKER, "hold the retirement age at 65")  # type: ignore[arg-type]


def test_a_cola_cut_lowers_the_pia() -> None:
    c = pia.compare(WORKER, Reform(cola=ColaChange(1990, 2100, 1, adjustment=-0.5)))
    assert c.pia_change < 0.0
    assert c.benefit_change_percent < 0.0


def test_law_applies_a_reform_to_its_parameters() -> None:
    baseline = Law.present_law(alt=2)
    reformed = baseline.apply(Reform(nra=NraChange(1990, 2100, variant=1)))
    assert baseline.params.full_ret_age(2022).years == 67
    assert reformed.params.full_ret_age(2022).years == 65


def test_an_empty_reform_is_falsy() -> None:
    assert not Reform()
    assert Reform(nra=NraChange(1990, 2100, variant=1))
