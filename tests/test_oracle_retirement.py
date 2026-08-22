"""MILESTONE test: every retire_v1 golden must match penny-exact,
end-to-end and on every per-method intermediate."""

from datetime import date

import pytest

from pyanypia import BenefitType, MonthYear, Worker, compute
from tests.oracle_util import load_sweep

SWEEP = load_sweep("retire_v1")


def worker_from_spec(spec: dict) -> Worker:
    y, m, d = spec["dob"]
    ey, em = spec["ent"]
    by, bm = spec["bendate"]
    return Worker(
        dob=date(y, m, d),
        sex=spec["sex"],
        benefit_type=BenefitType(spec["joasdi"]),
        earnings={int(k): v for k, v in spec["earnings"].items()},
        entitlement=MonthYear(ey, em),
        benefit_date=MonthYear(by, bm),
    )


def f2(x: float) -> str:
    return f"{x:.2f}"


@pytest.mark.oracle
@pytest.mark.parametrize(
    "spec,expected", SWEEP, ids=[s["case_id"] for s, _ in SWEEP]
)
def test_retirement_case(spec: dict, expected: dict) -> None:
    assert "error" not in expected, "oracle rejected this case"
    r = compute(worker_from_spec(spec))
    assert r.fully_insured_code == expected["fins"], "insured code"
    assert r.elig_year == expected["elig_year"], "eligibility year"
    exp_methods = {m["method"]: m for m in expected["methods"]}
    assert set(r.methods) == set(exp_methods), "method set"
    for name, em in exp_methods.items():
        gm = r.methods[name]
        assert gm.applicable == em["applicable"], f"{name} applicable"
        assert f2(gm.ame) == f2(em["ame"]), f"{name} ame"
        assert f2(gm.pia) == f2(em["pia"]), f"{name} pia"
        assert f2(gm.mfb) == f2(em["mfb"]), f"{name} mfb"
    assert f2(r.pia) == f2(expected["high_pia"]), "high pia"
    assert f2(r.mfb) == f2(expected["high_mfb"]), "high mfb"
    assert f2(r.support_pia) == f2(expected["support_pia"]), "support pia"
    assert f2(r.unrounded_benefit) == f2(expected["unrounded_benefit"])
    assert f2(r.monthly_benefit) == f2(expected["rounded_benefit"])
    assert r.months_reduction_or_credit == expected["months_ardri"]
    assert r.age_at_benefit is not None
    assert r.age_at_benefit.years == expected["age_ben_years"]
    assert r.age_at_benefit.months == expected["age_ben_months"]
    assert r.pifc == expected["pifc"]
    assert r.method == expected.get("high_method", " ")
