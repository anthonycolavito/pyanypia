"""Pre-1977 PIA tables (oldpia.cpp).

`OldPia` is the shared parent of the old-start, PIA-table and transitional
guarantee methods. Each successive Act's table is expressed as an increment
on the one before it, so `pl1973` recurses all the way down to `pl1952`;
`cpi_base` then carries a table value forward with benefit increases.

`piasub`, `mfbsub` and `iamemax` are the C++ member variables the table
functions communicate through, kept as instance state here for the same
reason.
"""

from __future__ import annotations

import enum
import math

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods.base import MethodState
from pyanypia.params import retire_age
from pyanypia.rounding import apply_cola as raw_apply_cola
from pyanypia.rounding import round_benefit

BENINC74 = 7.0  # temporary 7% increase, March-May 1974
FACTOR_150 = retire_age.FACTOR_150
FACTOR_175 = retire_age.FACTOR_175


class TableType(enum.IntEnum):
    """PiaMethod::table_type."""

    NO_TABLE = -1
    PL_1952 = 0
    PL_1954 = 1
    PL_1958 = 2
    PL_1965 = 3
    PL_1967 = 4
    PL_1969 = 5
    PL_1971 = 6
    PL_1972 = 7
    PL_1973 = 8
    PL_1977 = 9


def trunc_div(a: int, b: int) -> int:
    """C++ integer division, which truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class OldPia:
    """One PIA-table computation's working state."""

    def __init__(self, ctx: CalcContext, m: MethodState) -> None:
        self.ctx = ctx
        self.m = m
        self.piasub = 0.0
        self.mfbsub = 0.0
        self.iamemax = 0

    def last_amw(self, year: int) -> int:
        """PiaParams::lastAmw — highest AMW in the PIA table for a year.
        The 1979 and 1980 bases are not exact multiples of $60."""
        base = int(self.ctx.params.base_oasdi[year])
        return (base // 60 + 1) * 5 if base % 60 > 0 else base // 12

    # ---- table selection ----

    def old_pia_cal(self) -> int:
        """OldPia::oldPiaCal — the table in force at the benefit date."""
        bd = self.ctx.worker.benefit_date
        assert bd is not None
        if bd < retire_age.AMEND52:
            return TableType.NO_TABLE
        int_ame = int(self.m.ame)
        if bd < retire_age.AMEND54:
            return self.pl1952(int_ame)
        if bd < retire_age.AMEND58:
            return self.pl1954(int_ame)
        if bd < retire_age.AMEND651:
            return self.pl1958(int_ame)
        if bd < retire_age.AMEND672:
            return self.pl1965(int_ame)
        if bd < retire_age.AMEND69:
            return self.pl1967(int_ame)
        if bd < retire_age.AMEND70:
            return self.pl1969(int_ame)
        if bd < retire_age.AMEND721:
            return self.pl1971(int_ame)
        if bd < retire_age.AMEND742:
            return self.pl1972(int_ame)
        return TableType.NO_TABLE

    def cpi_base(
        self,
        benefit_date: MonthYear,
        freeze: bool,
        amesub: float,
        save_info: bool,
    ) -> int:
        """OldPia::cpiBase — carries the 1973 Act table forward with wage
        base extensions and benefit increases. `freeze` marks the
        transitional guarantee or a 1977 old-start with 1979-or-later
        eligibility, which both freeze the PIA at December 1978."""
        ctx, m, p = self.ctx, self.m, self.ctx.params
        i24 = 0  # year the AME first appears in the table, if AME > $1100
        elig_year = ctx.elig_year
        i1 = benefit_date.year
        last_year = (
            i1 - 1 if benefit_date.month < p.month_beninc(i1) else i1
        )
        i1 = int(amesub + 0.1)
        if i1 > 1100:
            for i2 in range(1975, last_year + 1):
                if i1 <= self.last_amw(i2):
                    i24 = i2
                    break
            if i24 == 0:
                i24 = last_year
            self.pl1973(1100)  # last PIA in the June 1974 table
            if save_info:
                m.pia_elig[m.year_first - 1] = self.piasub
                m.mfb_elig[m.year_first - 1] = self.mfbsub
            if i24 > 1975:
                if save_info:
                    m.year_table = i24
                # extend the table up to the year before the AME appears
                for i2 in range(1975, i24):
                    self.piasub += 0.2 * float(
                        self.last_amw(i2) - self.last_amw(i2 - 1)
                    )
                    self.mfbsub = round_benefit(
                        FACTOR_175 * self.piasub, i2 - 1
                    )
                    self._apply_increase(i2, benefit_date, elig_year)
                    if i2 == 1978 and freeze:
                        m.pia_elig[m.year_first] = self.piasub
                    if save_info:
                        m.pia_elig[i2] = self.piasub
                        m.mfb_elig[i2] = self.mfbsub
            # extension in the year the AME first appears
            self.piasub += float(
                trunc_div(i1 - self.last_amw(i24 - 1) + 4, 5)
            )
            self.mfbsub = round_benefit(FACTOR_175 * self.piasub, i24)
            i21 = i24
        elif elig_year < 1982 or not freeze or i1 > 75:
            self.pl1973(i1)
            if save_info:
                m.pia_elig[m.year_first - 1] = self.piasub
                m.mfb_elig[m.year_first - 1] = self.mfbsub
            m.pia_elig[m.year_first] = self.piasub
            m.mfb_elig[m.year_first] = self.mfbsub
            i21 = 1975
        else:
            # downward extension of the table, as of December 1978; no
            # benefit increases apply to the extended minimum
            self.piasub = round_benefit(float(i1) * 121.8 / 76.0, 1978)
            m.pia_elig[m.year_first] = self.piasub
            m.mfb_elig[m.year_first] = round_benefit(
                FACTOR_150 * self.piasub, 1978
            )
            return TableType.PL_1973
        for i2 in range(i21, last_year + 1):
            self._apply_increase(i2, benefit_date, elig_year)
            if i2 == 1978 and freeze:
                m.pia_elig[m.year_first] = self.piasub
            if save_info:
                m.pia_elig[i2] = self.piasub
                m.mfb_elig[i2] = self.mfbsub
        return TableType.PL_1973

    def _apply_increase(
        self, year: int, benefit_date: MonthYear, elig_year: int
    ) -> None:
        p = self.ctx.params
        if p.is_applicable_cola99(year, benefit_date):
            self.piasub = p.apply_cola99(self.piasub)
            self.mfbsub = p.apply_cola_mfb99(self.mfbsub, self.piasub)
        else:
            self.piasub = p.apply_cola(self.piasub, year, elig_year)
            self.mfbsub = p.apply_cola_mfb(
                self.mfbsub, year, self.piasub, elig_year
            )

    def mfb_old_cal(self, below_min: bool) -> float:
        """OldPia::mfbOldCal — the AME that produces this PIA, searched
        upward from the lowest one in the table."""
        bd = self.ctx.worker.benefit_date
        assert bd is not None
        rv = 75
        while True:
            rv += 1
            if bd < retire_age.AMEND742:
                self.pl1972(rv)
            else:
                self.cpi_base(bd, False, float(rv), False)
            if not (self.m.pia_ent > self.piasub and rv < 1000):
                break
        if below_min and rv == 76:
            self.m.mfb_ent = round_benefit(
                FACTOR_150 * self.m.pia_ent, self.m.year_ben
            )
        else:
            self.m.mfb_ent = self.mfbsub
        return float(rv)

    # ---- the Acts, newest to oldest ----

    def pl1973(self, amesub: int) -> None:
        """1973 Act, effective June 1974."""
        p = self.ctx.params
        if amesub < 1001:
            self.pl1972(amesub)
            self.piasub = p.apply_cola(self.piasub, 1974)
            self.mfbsub = p.apply_cola_mfb(self.mfbsub, 1974, self.piasub)
        else:
            self.pl1973ext(amesub)

    def pl1973ext(self, amesub: int) -> None:
        """1973 Act, $5 extension of the table above $1000 AME."""
        self.piasub = float(trunc_div(amesub + 4, 5)) + 249.0
        self.mfbsub = round_benefit(FACTOR_175 * self.piasub, 1974)

    def pl1972(self, amesub: int) -> int:
        """1972 Act, effective September 1972."""
        p, w = self.ctx.params, self.ctx.worker
        assert w.benefit_date is not None
        if amesub < 751:
            self.pl1971(amesub)
            self.piasub = p.apply_cola(self.piasub, 1972)
            self.mfbsub = p.apply_cola_mfb(self.mfbsub, 1972, self.piasub)
        else:
            self.piasub = float(trunc_div(amesub + 4, 5)) + 204.5
            self.mfbsub = round_benefit(FACTOR_175 * self.piasub, 1972)
        # temporary 7% increase for March-May 1974
        if (
            not w.benefit_date < retire_age.AMEND741
            and w.benefit_date < retire_age.AMEND742
        ):
            self.piasub = raw_apply_cola(self.piasub, BENINC74, 1974)
            self.mfbsub = raw_apply_cola(self.mfbsub, BENINC74, 1974)
        return TableType.PL_1972

    def pl1971(self, amesub: int) -> int:
        """1971 Act."""
        p = self.ctx.params
        if amesub < 652:
            self.pl1969(amesub)
            self.piasub = p.apply_cola(self.piasub, 1971)
        else:
            # 20% extension starting at $657, ad hoc between $652 and $656
            if amesub > 656:
                self.piasub = float(trunc_div(amesub + 4, 5)) + 145.4
            if 652 < amesub < 657:
                self.piasub = 276.6
            if amesub == 652:
                self.piasub = 275.8
        if amesub < 628:
            if amesub < 437:
                self.mfbsub = 0.88 * float(self.iamemax)
            if amesub > 436:
                self.mfbsub = 383.68 + 0.44 * float(self.iamemax - 436)
            self.mfbsub = round_benefit(self.mfbsub, 1971)
            mfb71 = round_benefit(FACTOR_150 * self.piasub, 1971)
            if amesub < 240 or self.mfbsub < mfb71:
                self.mfbsub = mfb71
        else:
            self.mfbsub = round_benefit(FACTOR_175 * self.piasub, 1971)
        return TableType.PL_1971

    def pl1969(self, amesub: int) -> int:
        """1969 Act (no table extension; 15% over the 1967 Act)."""
        p = self.ctx.params
        self.pl1967(amesub)
        self.piasub = p.apply_cola(self.piasub, 1970)
        self.piasub = max(64.0, self.piasub)
        if float(amesub) < 239.5:
            self.mfbsub = round_benefit(FACTOR_150 * self.piasub, 1970)
        return TableType.PL_1969

    def pl1967(self, amesub: int) -> int:
        """1967 Act."""
        p = self.ctx.params
        self.iamemax = amesub
        if self.iamemax < 554:
            self.pl1965(amesub)
            self.piasub = p.apply_cola(self.piasub, 1968)
            self.piasub = max(55.0, self.piasub)
        else:
            # extend the table beyond $553 at 28.43%
            self.piasub = math.floor(
                189.598 + 0.2843 * (amesub - 550) + 0.5
            )
            while True:
                self.iamemax += 1
                pia67 = math.floor(
                    189.598 + 0.2843 * float(self.iamemax - 550) + 0.5
                )
                if not abs(pia67 - self.piasub) < 0.1:
                    break
            self.iamemax -= 1
        if amesub < 371:
            if amesub < 179:
                self.mfbsub = round_benefit(FACTOR_150 * self.piasub, 1968)
            return TableType.PL_1967
        if amesub > 436:
            self.mfbsub = min(
                434.4, 348.8 + 0.4 * float(self.iamemax - 436)
            )
        else:
            self.mfbsub = 0.8 * float(self.iamemax)
        return TableType.PL_1967

    def pl1965(self, amesub: int) -> int:
        """1965 Act."""
        p = self.ctx.params
        self.pl1958(amesub)
        if amesub < 95:
            self.piasub += 4.0
            self.piasub = max(44.0, self.piasub)
            self.mfbsub = FACTOR_150 * self.piasub
            return TableType.PL_1965
        if amesub < 404:
            self.piasub = p.apply_cola(self.piasub, 1965)
        else:
            # $9 matches the 7% increase at $403, rounded to a dollar
            self.piasub += 9.0
        if amesub < 315:
            if amesub < 142:
                self.mfbsub = round_benefit(FACTOR_150 * self.piasub, 1965)
            return TableType.PL_1965
        if amesub > 370:
            self.mfbsub = min(368.0, 296.0 + 0.4 * float(self.iamemax - 370))
        else:
            self.mfbsub = 0.8 * float(self.iamemax)
        return TableType.PL_1965

    def pl1958(self, amesub: int) -> int:
        """1958 Act."""
        w = self.ctx.worker
        assert w.benefit_date is not None
        if amesub <= 84:
            self.piasub = 3.49 + 0.55 * float(amesub)
        else:
            # 0.5885 is 1.07 times the 0.55 of the 1954 Act
            round58 = 110.0 if amesub > 110 else float(amesub)
            self.piasub = 0.5885 * round58
            round58 = max(float(amesub - 110), 0.0)
            self.piasub += 0.214 * round58
        self.piasub = max(33.0, math.floor(self.piasub + 0.5))
        if amesub == 553:
            self.piasub = 159.0  # made ad hoc in the 1967 Act
        if not w.benefit_date < retire_age.AMEND61 and self.piasub < 40.0:
            self.piasub = 40.0
        self.iamemax = amesub
        if self.iamemax > 127:
            while True:
                self.iamemax += 1
                pia58 = math.floor(
                    41.195 + 0.214 * float(self.iamemax) + 0.5
                )
                if not abs(pia58 - self.piasub) < 0.1:
                    break
            if self.iamemax != 553:
                self.iamemax -= 1
            self.mfbsub = min(254.0, 0.8 * float(self.iamemax))
        else:
            self.mfbsub = max(
                FACTOR_150 * self.piasub, self.piasub + 20.0
            )
        return TableType.PL_1958

    def pl1954(self, amesub: int) -> int:
        """1954 Act: 55% of the first $110 of AMW plus 20% of the excess."""
        i1 = 110 if amesub > 110 else amesub
        self.piasub = 0.55 * float(i1)
        i1 = amesub - 110 if amesub > 110 else 0
        self.piasub += 0.2 * float(i1)
        piat = round_benefit(self.piasub, 1954)
        self.piasub = max(30.0, piat)
        self.mfbsub = max(
            FACTOR_150 * self.piasub, max(0.8 * float(amesub), 50.0)
        )
        self.mfbsub = min(200.0, self.mfbsub)
        return TableType.PL_1954

    def pl1952(self, amesub: int) -> int:
        """1952 Act: 55% of the first $100 of AMW plus 15% of the excess."""
        i1 = min(amesub, 100)
        self.piasub = 0.55 * float(i1)
        i1 = max(amesub - 100, 0)
        self.piasub += 0.15 * float(i1)
        piat = round_benefit(self.piasub, 1952)
        self.piasub = max(25.0, piat)
        self.mfbsub = min(168.75, max(0.8 * float(amesub), 45.0))
        return TableType.PL_1952
