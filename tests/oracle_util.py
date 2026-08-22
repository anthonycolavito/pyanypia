"""Helpers to load oracle goldens + case manifests for differential tests."""

from __future__ import annotations

import json
import pathlib
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
    for spec, exp in zip(specs, expected):
        assert exp.get("case_id") == spec["case_id"]
        out.append((spec, exp))
    return out
