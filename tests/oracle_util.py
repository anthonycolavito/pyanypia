"""Helpers to load oracle goldens + case manifests for differential tests."""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORACLE = ROOT / "oracle"


def load_params(alt: int = 2) -> dict[str, Any]:
    with open(ORACLE / "goldens" / f"params_alt{alt}.json") as f:
        return json.load(f)


def load_sweep(name: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Returns [(case_spec, oracle_expected), ...] for a sweep, joined on
    input order (case_id is cross-checked)."""
    specs = [
        json.loads(line)
        for line in open(ORACLE / "cases" / name / "manifest.jsonl")
    ]
    expected = [
        json.loads(line)
        for line in open(ORACLE / "goldens" / f"{name}.jsonl")
    ]
    assert len(specs) == len(expected), f"sweep {name}: manifest/golden mismatch"
    out = []
    for spec, exp in zip(specs, expected, strict=True):
        assert exp.get("case_id") == spec["case_id"]
        out.append((spec, exp))
    return out


def load_reform_sweep(
    name: str = "reform_v1",
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """Returns [(case_spec, oracle_expected, variant), ...].

    The golden holds one block per reform variant over the same cases,
    so the manifest is joined to each block in turn.
    """
    specs = [
        json.loads(line)
        for line in open(ORACLE / "cases" / name / "manifest.jsonl")
    ]
    expected = [
        json.loads(line)
        for line in open(ORACLE / "goldens" / f"{name}.jsonl")
    ]
    assert len(expected) % len(specs) == 0, (
        f"sweep {name}: {len(expected)} rows is not a whole number of "
        f"blocks of {len(specs)} cases"
    )
    out = []
    for i, exp in enumerate(expected):
        spec = specs[i % len(specs)]
        variant = exp["variant"]
        assert exp["case_id"] == f"{variant}::{spec['case_id']}"
        out.append((spec, exp, variant))
    return out


def reform_params(variant: str, alt: int = 2):  # type: ignore[no-untyped-def]
    """The parameters a sweep variant's reform produces."""
    from pyanypia.params import present_law

    if variant == "present_law":
        return present_law(alt)
    if str(ORACLE) not in sys.path:
        sys.path.insert(0, str(ORACLE))
    import reform_specs

    from pyanypia.law import reformed_params

    return reformed_params(reform_specs.BY_NAME[variant].reform, alt=alt)


def worker_from_spec(spec: dict[str, Any]):  # type: ignore[no-untyped-def]
    """Builds a pyanypia Worker from a generator CaseSpec dict, mirroring
    what the oracle reads from the .pia file."""
    from datetime import date

    from pyanypia import BenefitType, DisabilityPeriod, MonthYear, Worker
    from pyanypia.worker import MilitaryService

    y, m, d = spec["dob"]
    ent = MonthYear(*spec["ent"]) if spec.get("ent") else None
    ben = MonthYear(*spec["bendate"]) if spec.get("bendate") else None
    periods = []
    if spec.get("onset"):
        oy, om, od = spec["onset"]
        prior = spec.get("prior_ent")
        if prior is None and spec["joasdi"] == 3:
            prior = spec["ent"]
        periods.append(DisabilityPeriod(
            onset=date(oy, om, od),
            first_entitlement=MonthYear(*prior) if prior else None,
            waiting_period_start=(
                MonthYear(*spec["waitper"]) if spec.get("waitper") else None
            ),
            cessation=(
                MonthYear(*spec["cessation"])
                if spec.get("cessation") else None
            ),
            cessation_pia=spec.get("cessation_pia", 0.0),
            cessation_mfb=spec.get("cessation_mfb", 0.0),
        ))
    if spec.get("onset2"):
        oy, om, od = spec["onset2"]
        periods.append(DisabilityPeriod(
            onset=date(oy, om, od),
            first_entitlement=(
                MonthYear(*spec["prior_ent2"])
                if spec.get("prior_ent2") else None
            ),
            waiting_period_start=(
                MonthYear(*spec["waitper2"]) if spec.get("waitper2") else None
            ),
            cessation=(
                MonthYear(*spec["cessation2"])
                if spec.get("cessation2") else None
            ),
            cessation_pia=spec.get("cessation2_pia", 0.0),
            cessation_mfb=spec.get("cessation2_mfb", 0.0),
        ))
    from pyanypia import FamilyMember

    family = []
    for fm in spec.get("family", []):
        fy, fmm, fd = fm["dob"]
        family.append(FamilyMember(
            bic=fm["bic"],
            dob=date(fy, fmm, fd),
            entitlement=MonthYear(*fm["ent"]),
            disability_onset=(
                date(*fm["onset"]) if fm.get("onset") else None
            ),
        ))
    death = None
    if spec.get("death"):
        dy, dm, dd = spec["death"]
        death = date(dy, dm, dd)
    return Worker(
        dob=date(y, m, d),
        sex=spec["sex"],
        benefit_type=BenefitType(spec["joasdi"]),
        earnings={int(k): v for k, v in spec["earnings"].items()},
        entitlement=ent,
        benefit_date=ben,
        death_date=death,
        disability_periods=tuple(periods),
        family=tuple(family),
        qc_total_to_date=spec.get("qctottd") or 0,
        qc_total_51_to_date=spec.get("qctot51td") or 0,
        childcare_years=frozenset(spec.get("childcare_years") or ()),
        totalize=bool(spec.get("totalize")),
        earnings_span=(
            tuple(spec["earnings_span"]) if spec.get("earnings_span") else None
        ),
        projection=_projection_from_spec(spec),
        military_service=tuple(
            MilitaryService(MonthYear(*s), MonthYear(*e))
            for s, e in (spec.get("military") or [])
        ),
        qcs_by_year={
            int(k): v for k, v in (spec.get("qcs_by_year") or {}).items()
        },
    )


def _projection_from_spec(spec):  # type: ignore[no-untyped-def]
    """The .pia earnings-projection lines (07/08/20), if the case has any."""
    from pyanypia.worker import EarningsProjection

    types = {int(k): v for k, v in (spec.get("earn_types") or {}).items()}
    if not (spec.get("proj_back") or spec.get("proj_fwrd") or types):
        return None
    entered = sorted(int(k) for k in spec["earnings"])
    return EarningsProjection(
        proj_back=spec.get("proj_back", 0),
        perc_back=spec.get("perc_back", 0.0),
        first_year=entered[0] if entered else 0,
        proj_fwrd=spec.get("proj_fwrd", 0),
        perc_fwrd=spec.get("perc_fwrd", 0.0),
        last_year=entered[-1] if entered else 0,
        earn_types=types,
    )


def assert_case_matches(r, expected):  # type: ignore[no-untyped-def]
    """Field-by-field cent-level comparison against a golden row."""
    def f2(x: float) -> str:
        return f"{x:.2f}"

    assert r.fully_insured_code == expected["fins"], "insured code"
    assert r.disability_insured == expected["dib_insured"], "dib insured"
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
    if r.age_at_benefit is None:
        assert expected["age_ben_years"] == 0
        assert expected["age_ben_months"] == 0
    else:
        assert r.age_at_benefit.years == expected["age_ben_years"]
        assert r.age_at_benefit.months == expected["age_ben_months"]
    assert r.pifc == expected["pifc"]
    assert r.method == expected.get("high_method", " ")
    exp_sec = expected.get("secondaries", [])
    assert len(r.family) == len(exp_sec), "family size"
    for got, exp in zip(r.family, exp_sec, strict=True):
        assert got.bic == exp["bic"].strip(), "family bic"
        assert f2(got.full_benefit) == f2(exp["full_benefit"]), (
            f"family {got.bic} full benefit"
        )
        assert f2(got.rounded_benefit) == f2(exp["rounded_benefit"]), (
            f"family {got.bic} rounded benefit"
        )
        assert got.pifc == exp["pifc"], "family pifc"


def assert_rejects_like_oracle(spec, expected):  # type: ignore[no-untyped-def]
    """When the oracle errored on a case, pyanypia must reject it too,
    with the same AnyPIA error code."""
    import re

    import pytest

    from pyanypia import compute
    from pyanypia.errors import PiaError

    m = re.search(r"PiaException: (\d+)", expected["error"])
    assert m, f"unparseable oracle error: {expected['error']}"
    code = int(m.group(1))
    with pytest.raises(PiaError) as exc_info:
        compute(worker_from_spec(spec))
    assert exc_info.value.code == code, (
        f"oracle code {code}, pyanypia code {exc_info.value.code}"
    )
