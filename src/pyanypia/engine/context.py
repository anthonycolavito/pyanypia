"""CalcContext: the working state of one benefit calculation (PiaData).

Mutable, internal to the engine; the facade converts it into an immutable
Results object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from pyanypia.dates import Age, MonthYear, QtrYear
from pyanypia.params import Params
from pyanypia.worker import Worker

YEAR36 = 1936
YEAR37 = 1937
YEAR50 = 1950
YEAR51 = 1951


@dataclass
class CompPeriod:
    """Computation period (comppd.h)."""

    base_year: int
    n_elapsed: int = 0
    n_drop: int = 0
    di_years: int = 0
    n: int = 0


@dataclass
class FreezeYears:
    """Years wholly within a period of disability (frzyrs.h)."""

    year1: int = 0
    year2: int = 0
    year3: int = 0
    year4: int = 0

    def clear(self) -> None:
        self.year1 = self.year2 = self.year3 = self.year4 = 0

    def is_freeze_year(self, year: int) -> bool:
        if self.year1 > 0 and self.year1 <= year <= self.year2:
            return True
        return self.year3 > 0 and self.year3 <= year <= self.year4

    def has_years1(self) -> bool:
        return self.year1 > 0 or self.year2 > 0


@dataclass
class CalcContext:
    """Working data for one calculation (PiaData analogue)."""

    worker: Worker
    params: Params
    # day before birth (kbirth)
    kbirth: date = field(init=False)
    ioasdi: int = 0

    # ages and dates
    age_ent: Age | None = None
    age_ben: Age | None = None
    full_ret_age: Age | None = None
    early_ret_age: Age | None = None
    full_ret_date: MonthYear | None = None
    full_ins_date: MonthYear | None = None
    elig_date: MonthYear | None = None
    elig_year: int = 0
    elig_year_non_freeze: int = 0

    # earnings attribution
    ibegin_all: int = 0
    iend_all: int = 0
    earn_year: int = 0
    earn_oasdi: dict[int, float] = field(default_factory=dict)
    earn_oasdi_limited: dict[int, float] = field(default_factory=dict)
    earn_hi: dict[int, float] = field(default_factory=dict)
    earn_hi_limited: dict[int, float] = field(default_factory=dict)
    earn_total50: float = 0.0  # regular pre-1951 total

    # totalization: an artificial earnings record built from the worker's
    # relative earnings position in their covered years
    ibegin_total: int = 0
    iend_total: int = 0
    earn_totalized: dict[int, float] = field(default_factory=dict)
    earn_totalized_limited: dict[int, float] = field(default_factory=dict)
    earn_total50_totalized: float = 0.0
    rel_earn_position: dict[int, float] = field(default_factory=dict)
    rel_earn_position_average: float = 0.0
    qc_total_rel: int = 0

    # quarters of coverage
    qcov: dict[int, int] = field(default_factory=dict)
    qc3750_simp: int = 0
    qc_total50: int = 0
    qc_total51: int = 0
    qc_total: int = 0
    qc_total51_non_freeze: int = 0
    qc_total_non_freeze: int = 0
    qc_current: int = 0
    qc_current_non_freeze: int = 0
    qc_req: int = 0
    qc_req_perm: int = 0
    qc_req_non_freeze: int = 0
    qc_req_perm_non_freeze: int = 0
    deemed_qc_req: int = 0

    # disability-insured working data (PiaData qcDis* fields)
    qc_dis_date1: QtrYear | None = None
    qc_dis_date2: QtrYear | None = None
    qc_dis_date3: QtrYear | None = None
    qc_dis_date4: QtrYear | None = None
    qc_dis_date5: QtrYear | None = None
    qc_dis_date6: QtrYear | None = None
    qc_dis_qtr: int = 0
    qc_dis_qtr2: int = 0
    qc_dis_req: int = 0
    qc_dis_years: int = 0
    qc_total_dis: int = 0
    qc_dis_date_nf1: QtrYear | None = None
    qc_dis_date_nf2: QtrYear | None = None
    qc_dis_qtr_nf: int = 0
    qc_dis_req_nf: int = 0
    qc_total_dis_nf: int = 0

    # insured status
    fins_code: str = " "  # InsCodeType char
    fins_code2: str = " "  # OACT summary code '1'..'7'
    fins_non_freeze_code: str = " "
    fins_non_freeze_code2: str = " "
    dis_ins_code: str = " "  # DisInsCodeType char
    dis_ins_non_freeze_code: str = " "

    # computation periods and freeze years
    comp_period_new: CompPeriod = field(
        default_factory=lambda: CompPeriod(YEAR50)
    )
    comp_period_new_non_freeze: CompPeriod = field(
        default_factory=lambda: CompPeriod(YEAR50)
    )
    comp_period_old: CompPeriod = field(
        default_factory=lambda: CompPeriod(YEAR36)
    )
    freeze_years: FreezeYears = field(default_factory=FreezeYears)
    partial_freeze_years: FreezeYears = field(default_factory=FreezeYears)

    # results
    amend90: bool = False
    months_ardri: int = 0
    arf: float = 0.0
    arf_app: int = 0  # 0 none, 1 support benefit, 2 spec-min benefit
    iappn: int = -1  # applicable method type (PiaMethod::pia_type)
    iapps: int = -1  # support method type
    high_pia: float = 0.0
    high_mfb: float = 0.0
    support_pia: float = 0.0
    unrounded_benefit: float = 0.0
    rounded_benefit: float = 0.0
    pifc: str = " "
    over_max: bool = False

    def __post_init__(self) -> None:
        self.kbirth = self.worker.dob - timedelta(days=1)
        self.ioasdi = int(self.worker.benefit_type)

    # --- helpers mirroring PiaData ---

    def qcov_get(self, year: int) -> int:
        return self.qcov.get(year, 0)

    def qcov_accumulate_years(self, y1: int, y2: int, start: int) -> int:
        for y in range(y1, y2 + 1):
            start += self.qcov.get(y, 0)
        return start

    def qcov_accumulate(self, q1: QtrYear, q2: QtrYear, start: int) -> int:
        """QcArray::accumulate over a quarter range: QCs within a year are
        deemed available in any quarter, capped by quarters in the range."""
        if q1 > q2:
            return start
        if q1.year < q2.year:
            start += min(self.qcov.get(q1.year, 0), 4 - q1.quarter)
            start = self.qcov_accumulate_years(q1.year + 1, q2.year - 1, start)
            start += min(self.qcov.get(q2.year, 0), q2.quarter + 1)
        else:
            start += min(
                q2.quarter - q1.quarter + 1, self.qcov.get(q1.year, 0)
            )
        return start

    def get_earn_total50(self, with_totalization: bool = False) -> float:
        """PiaData::getEarnTotal50 — the pre-1951 earnings total, from the
        real record or the totalized one."""
        if with_totalization:
            return self.earn_total50_totalized
        return self.earn_total50

    def method_earnings(self) -> dict[int, float]:
        """The earnings a PIA method computes from: the totalized record
        for a totalization case, otherwise the real one."""
        if self.worker.totalize:
            return self.earn_totalized_limited
        return self.earn_oasdi_limited

    def earn50(self, with_totalization: bool = False) -> int:
        """PiaData::getEarn50 — first year of post-1950 earnings."""
        if with_totalization and self.worker.totalize:
            return max(self.ibegin_total, YEAR51)
        return max(self.ibegin_all, YEAR51)
