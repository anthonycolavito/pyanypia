"""Policy parameters: the primitive inputs a reform can change, and the
series derived from them with AnyPIA's operation order and rounding."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np

from pyanypia import _data2026 as d
from pyanypia import _project as proj
from pyanypia._years import FIRST_YEAR, LAST_YEAR, N_YEARS, to_array

#: derived series that `Policy.with_series` can pin
SERIES = ("awi", "cola", "taxmax", "base77", "qc_amount", "yoc_specmin", "yoc_wep", "nra")


def _series(values: tuple[float, ...], first: int) -> dict[int, float]:
    return {first + i: float(v) for i, v in enumerate(values)}


def _statutory_nra(elig_year: int) -> int:
    """Normal retirement age in months, by year of attaining 62."""
    if elig_year < 2000:
        return 780
    if elig_year < 2005:
        return 780 + 2 * (elig_year - 1999)
    if elig_year < 2017:
        return 792
    if elig_year < 2022:
        return 792 + 2 * (elig_year - 2016)
    return 804


def _statutory_drc(elig_year: int) -> float:
    """Monthly delayed retirement credit rate (PiaParams::retCredit)."""
    if elig_year < 1979:
        return 1.0 / 1200.0
    if elig_year < 1987:
        return 1.0 / 400.0
    if elig_year < 2005:
        return float((elig_year - 1985) // 2) / 2400.0 + 1.0 / 400.0
    return 2.0 / 300.0


def _frozen(arr: np.ndarray) -> np.ndarray:
    arr.setflags(write=False)
    return arr


@dataclass(frozen=True, eq=False)
class Policy:
    """Everything a benefit computation reads that a reform could change.

    The fields are primitive inputs. The array attributes (`awi`, `cola`,
    `taxmax`, `qc_amount`, ...) are derived from them on first use and indexed
    by `year - 1937`. `replace` changes primitives, and the change flows into
    every derived series; `with_series` pins individual derived values.
    """

    #: average wage index by year, through the last historical year
    awi_hist: Mapping[int, float]
    #: projected AWI growth, percent, for every later year through 2105
    awi_growth: Mapping[int, float]
    #: benefit increases (COLAs), percent, by year of the December increase
    cola_hist: Mapping[int, float]
    cola_proj: Mapping[int, float]
    #: taxable maximum and old-law (1977-Act) base, historical years
    taxmax_hist: Mapping[int, float]
    base77_hist: Mapping[int, float]
    #: 1979 PIA bend points, indexed by the AWI from 1977
    pia_bend_base: tuple[float, ...] = (180.0, 1085.0)
    pia_pct: tuple[float, ...] = (0.90, 0.32, 0.15)
    mfb_bend_base: tuple[float, ...] = (230.0, 332.0, 433.0)
    mfb_pct: tuple[float, ...] = (1.50, 2.72, 1.34, 1.75)
    #: early-retirement reduction: per month for the first months, then after
    ar_rate_first: float = 5.0 / 900.0
    ar_rate_later: float = 5.0 / 1200.0
    ar_months_first: int = 36
    spouse_ar_rate_first: float = 25.0 / 3600.0
    #: monthly delayed retirement credit; None follows the statute by cohort
    drc_rate: float | None = None
    #: quarter-of-coverage amount in 1978, indexed by the AWI after
    qc_base: float = 250.0
    #: special minimum per year of coverage over 10, in January 1979
    spec_min_amount: float = 11.50
    wep_enabled: bool = False
    gpo_enabled: bool = False
    gpo_fraction: float = 2.0 / 3.0
    #: pinned derived values, {series: {year: value}}; see `with_series`
    overrides: Mapping[str, Mapping[int, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.pia_pct) != len(self.pia_bend_base) + 1:
            raise ValueError("pia_pct: needs exactly one more entry than pia_bend_base")
        if len(self.mfb_pct) != 4 or len(self.mfb_bend_base) != 3:
            raise ValueError("mfb_pct/mfb_bend_base: need 4 percentages and 3 bend points")
        for name in self.overrides:
            if name not in SERIES:
                raise ValueError(f"unknown series {name!r}; expected one of {SERIES}")

    @classmethod
    def current_law(cls, alt: int = 2) -> Policy:
        """Present law under 2026 Trustees Report alternative 1, 2 or 3."""
        if alt not in (1, 2, 3):
            raise ValueError(f"alt must be 1, 2 or 3, not {alt}")
        return cls(
            awi_hist=_series(d.FQ, d.FQ_FIRST),
            awi_growth=_series(getattr(d, f"FQINC_PROJ_ALT{alt}"),
                               getattr(d, f"FQINC_PROJ_ALT{alt}_FIRST")),
            cola_hist=_series(d.CPIINC, d.CPIINC_FIRST),
            cola_proj=_series(getattr(d, f"CPIINC_PROJ_ALT{alt}"),
                              getattr(d, f"CPIINC_PROJ_ALT{alt}_FIRST")),
            taxmax_hist=_series(d.BASE_OASDI, d.BASE_OASDI_FIRST),
            base77_hist=_series(d.BASE_77, d.BASE_77_FIRST),
        )

    def replace(self, **changes: Any) -> Policy:
        """A copy with primitive fields changed; derived series are rebuilt."""
        return dataclasses.replace(self, **changes)

    def with_series(self, name: str, values: Mapping[int, float]) -> Policy:
        """A copy with derived-series values pinned for specific years. These
        are final values: later years are not re-projected from them."""
        if name not in SERIES:
            raise ValueError(f"unknown series {name!r}; expected one of {SERIES}")
        merged = {k: dict(v) for k, v in self.overrides.items()}
        merged.setdefault(name, {}).update(values)
        return self.replace(overrides=merged)

    # ---- derived series ----

    def _finish(self, name: str, arr: np.ndarray) -> np.ndarray:
        for year, v in self.overrides.get(name, {}).items():
            if not FIRST_YEAR <= year <= LAST_YEAR:
                raise ValueError(
                    f"{name}: override year {year} outside {FIRST_YEAR}-{LAST_YEAR}")
            arr[year - FIRST_YEAR] = v
        return _frozen(arr)

    @staticmethod
    def _as_dict(arr: np.ndarray) -> dict[int, float]:
        return {FIRST_YEAR + i: float(v) for i, v in enumerate(arr) if not np.isnan(v)}

    @cached_property
    def awi(self) -> np.ndarray:
        fq = dict(self.awi_hist)
        proj.project_fq(fq, dict(self.awi_growth), max(fq) + 1, LAST_YEAR)
        return self._finish("awi", to_array(fq))

    @cached_property
    def cola(self) -> np.ndarray:
        return self._finish("cola", to_array({**self.cola_hist, **self.cola_proj}))

    def _projected_base(self, hist: Mapping[int, float], ind: int) -> np.ndarray:
        base = dict(hist)
        proj.project_base(base, self._as_dict(self.awi), self._as_dict(self.cola), ind,
                          max(base) + 1, LAST_YEAR)
        return to_array(base)

    @cached_property
    def taxmax(self) -> np.ndarray:
        return self._finish("taxmax", self._projected_base(self.taxmax_hist, 0))

    @cached_property
    def base77(self) -> np.ndarray:
        return self._finish("base77", self._projected_base(self.base77_hist, 2))

    @cached_property
    def qc_amount(self) -> np.ndarray:
        amounts = proj.project_qc_amounts(self._as_dict(self.awi), LAST_YEAR, self.qc_base)
        return self._finish("qc_amount", to_array(amounts))

    @cached_property
    def yoc_specmin(self) -> np.ndarray:
        """Earnings for a year of coverage toward the special minimum."""
        b = self.base77
        vals = {y: (0.25 if y < 1991 else 0.15) * float(b[y - FIRST_YEAR])
                for y in range(1951, LAST_YEAR + 1)}
        return self._finish("yoc_specmin", to_array(vals))

    @cached_property
    def yoc_wep(self) -> np.ndarray:
        """Earnings for a year of coverage toward the WEP's 30 years."""
        b = self.base77
        vals = {y: 0.25 * float(b[y - FIRST_YEAR]) for y in range(1951, LAST_YEAR + 1)}
        return self._finish("yoc_wep", to_array(vals))

    @cached_property
    def nra(self) -> np.ndarray:
        """Normal retirement age in months, by year of attaining 62."""
        arr = np.array([float(_statutory_nra(y)) for y in range(FIRST_YEAR, LAST_YEAR + 1)])
        return self._finish("nra", arr)

    @cached_property
    def drc_rate_by_elig(self) -> np.ndarray:
        if self.drc_rate is not None:
            return _frozen(np.full(N_YEARS, float(self.drc_rate)))
        return _frozen(np.array([_statutory_drc(y) for y in range(FIRST_YEAR, LAST_YEAR + 1)]))

    @cached_property
    def spec_min_tables(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(PIA (20, years), MFB (20, years), Aug-2001 PIA (20,), Aug-2001 MFB
        (20,)), by years of coverage over 10, minus one."""
        pia_t, mfb_t, pia01, mfb01 = proj.project_special_min(
            self._as_dict(self.cola), LAST_YEAR, self.spec_min_amount)
        return (
            _frozen(np.stack([to_array(t) for t in pia_t])),
            _frozen(np.stack([to_array(t) for t in mfb_t])),
            _frozen(np.array(pia01)),
            _frozen(np.array(mfb01)),
        )


#: present law, 2026 Trustees Report intermediate assumptions
CURRENT_LAW = Policy.current_law(2)
