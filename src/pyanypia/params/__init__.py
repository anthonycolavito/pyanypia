"""Law parameters: historical data assembled with projections.

`Params.build(alt)` mirrors what anypiab does at startup for a case using
Trustees Report alternative `alt`: load historical data (AwbiDataNonFile /
PiaParams::setData), set historical AWI increases (setHistFqinc), apply
assumption paths (updateCpiinc / updateFqinc via PiaCalAny::calculate1),
project wage bases (updateBases) and dependent amounts.
"""

from __future__ import annotations

from datetime import date as _date
from functools import lru_cache

from pyanypia.dates import Age, MonthYear
from pyanypia.errors import PiaError
from pyanypia.params import _data2026 as d
from pyanypia.params import projection, retire_age
from pyanypia.params.assumptions import Assumptions
from pyanypia.rounding import apply_cola as _ba_apply_cola
from pyanypia.rounding import round_benefit, unapply_cola, unround_benefit

YEAR37 = 1937
YEAR51 = 1951
YEAR79 = 1979
YEAR1999 = 1999


def _series(values: tuple[float, ...], first: int) -> dict[int, float]:
    return {first + i: v for i, v in enumerate(values)}


# PercPia::PERC — the 90/32/15 benefit formula percentages
PERC_PIA = (0.90, 0.32, 0.15)


class Params:
    """Assembled law parameters for one assumption set (present law)."""

    def __init__(self, assumptions: Assumptions) -> None:
        self.istart = d.ISTART
        self.maxyear = d.MAXYEAR
        self.assumptions = assumptions

        # --- average wage index (fq) ---
        self.fq = _series(d.FQ, d.FQ_FIRST)  # through istart-2
        self.fqinc = projection.hist_fqinc(
            self.fq, YEAR37 + 1, self.istart - 2
        )
        self.fqinc.update(assumptions.awincproj)  # istart-1 .. maxyear
        projection.project_fq(
            self.fq, self.fqinc, self.istart - 1, self.maxyear
        )
        # The PIA bend points index off their own wage series, which a
        # reform can grow differently (PiaParamsLC::setFqBppia). The MFB
        # bend points always use the real one.
        self.fq_bppia = self.build_fq_bppia()

        # --- benefit increases (cpiinc) ---
        self.cpiinc = _series(d.CPIINC, d.CPIINC_FIRST)  # through istart-1
        self.cpiinc.update(assumptions.biproj)  # istart .. maxyear
        self.catchup = dict(assumptions.catchup)
        # A reform changes benefit increases here, before anything that
        # depends on them is projected (PiaParamsLC::setAltCpiinc).
        self.adjust_cpiinc()

        # --- wage bases ---
        self.base_oasdi = _series(d.BASE_OASDI, d.BASE_OASDI_FIRST)
        self.base_77 = _series(d.BASE_77, d.BASE_77_FIRST)
        self.base_hi = dict(self.base_oasdi)
        self.base_hi.update(_series(d.BASE_HI, d.BASE_HI_FIRST))
        self.project_bases()

        # --- amounts dependent on fq ---
        self.qc_amt = projection.project_qc_amounts(
            self.fq, projection.AUTO_YEAR, self.maxyear
        )

        # --- amounts dependent on base77 ---
        self.yoc_amt_windfall, self.yoc_amt_specmin = (
            projection.yoc_amounts_special_min(self.base_77, self.maxyear)
        )

        # --- special minimum tables (dependent on cpiinc) ---
        self._spec_min_split = self.spec_min_split_year()
        (
            self._specmin_pia,
            self._specmin_mfb,
            self._specmin_pia_2001,
            self._specmin_mfb_2001,
            self._specmin_pia_extra,
            self._specmin_mfb_extra,
        ) = projection.project_special_min(
            self.cpiinc, self.maxyear,
            amount_at=self.spec_min_amount,
            split_year=self._spec_min_split,
        )

    # ---- reform hooks (no-ops under present law) ----

    def build_fq_bppia(self) -> dict[int, float]:
        """The wage series the PIA bend points index off; the real one
        unless a reform grows it differently."""
        return self.fq

    def n_drop_override(self, ent_year: int, elig_year: int) -> int | None:
        """A reform's fixed number of dropout years, or None to keep the
        computed one."""
        return None

    def adjust_cpiinc(self) -> None:
        """Lets a reform change the benefit-increase series in place."""

    def perc_pia(self, elig_year: int) -> tuple[float, ...]:
        """PiaParams::percPiaCal — the benefit formula percentages for an
        eligibility year. Only a reform makes them vary by year."""
        return PERC_PIA

    def max_childcare_dropout_years(
        self, elig_year: int, benefit_year: int
    ) -> int:
        """PiaParams::getMaxChildcareDropoutYearsPL — three, counting the
        ordinary dropout years."""
        return 3

    def childcare_dropout_amount(
        self, elig_year: int, benefit_year: int
    ) -> float:
        """PiaParams::getChildcareDropoutAmountPL — a child-care dropout
        year must have no earnings at all."""
        return 0.0

    def childcare_always_applicable(
        self, elig_year: int, benefit_year: int
    ) -> bool:
        """ChildCareCalcLC::isApplicable — a reform can make the method
        apply whether or not present law would."""
        return False

    def comp_point_shift(self, elig_year: int, benefit_year: int) -> int:
        """Years to move the computation point past 62, which only a
        reform does (PiaCalLC::nelapsed2Cal)."""
        return 0

    def spec_min_amount(self, year: int) -> float:
        """PiaParams::specMinAmountCalPL — the special minimum's amount
        per year of coverage, $11.50 since 1979."""
        return 11.50

    def spec_min_split_year(self) -> int | None:
        """The first year of a reform's new special-minimum amount, from
        which the table is rebuilt rather than carried forward."""
        return None

    def project_bases(self) -> None:
        """WageBaseLC::project — projects the three wage-base series.

        Present law projects each of them straight through; a reform
        setting ad hoc bases overrides this.
        """
        projection.project_base(
            self.base_oasdi, self.fq, self.cpiinc, 0,
            self.istart + 1, self.maxyear,
        )
        projection.project_base(
            self.base_77, self.fq, self.cpiinc, 2,
            self.istart + 1, self.maxyear,
        )
        projection.project_base(
            self.base_hi, self.fq, self.cpiinc, 3,
            self.istart + 1, self.maxyear,
        )

    # ---- accessors mirroring PiaParams ----

    def get_fq(self, year: int) -> float:
        return self.fq[year]

    def get_cpiinc(self, year: int) -> float:
        if year < YEAR51 or year > self.maxyear:
            raise PiaError(62016, f"cpiinc year {year} out of range")
        return self.cpiinc[year]

    def bend_points_pia(self, elig_year: int) -> tuple[float, ...]:
        """The PIA formula bend points. Two under present law; a reform
        replacing the formula can name up to four."""
        return projection.bend_points_pia(elig_year, self.fq_bppia)

    def bend_points_mfb(self, elig_year: int) -> tuple[float, float, float]:
        return projection.bend_points_mfb(elig_year, self.fq)

    def month_beninc(self, year: int) -> int:
        return retire_age.month_beninc(year)

    # ---- COLA application (present law: catch-up is empty) ----

    def _catchup_factor(self, elig_year: int, year: int) -> float | None:
        return self.catchup.get((elig_year, year))

    def apply_cola(
        self, pia: float, year: int, elig_year: int | None = None
    ) -> float:
        rv = _ba_apply_cola(pia, self.get_cpiinc(year), year)
        if elig_year is not None:
            cu = self._catchup_factor(elig_year, year)
            if cu is not None:
                rv = round_benefit(rv * (cu / 100.0 + 1.0), year)
        return rv

    def apply_cola99(self, pia: float) -> float:
        return _ba_apply_cola(pia, self.get_cpiinc(YEAR1999) + 0.1, YEAR1999)

    def apply_cola_mfb(
        self, mfb: float, year: int, pia: float,
        elig_year: int | None = None,
    ) -> float:
        rv = _ba_apply_cola(mfb, self.get_cpiinc(year), year)
        if elig_year is not None:
            cu = self._catchup_factor(elig_year, year)
            if cu is not None:
                rv = round_benefit(rv * (cu / 100.0 + 1.0), year)
        mfbt = round_benefit(retire_age.FACTOR_150 * pia, year)
        return max(rv, mfbt)

    def apply_cola_mfb99(self, mfb: float, pia: float) -> float:
        rv = _ba_apply_cola(mfb, self.get_cpiinc(YEAR1999) + 0.1, YEAR1999)
        mfbt = round_benefit(retire_age.FACTOR_150 * pia, YEAR1999)
        return max(rv, mfbt)

    def unapply_cola(
        self, pia: float, year: int, elig_year: int | None = None
    ) -> float:
        rv = unapply_cola(pia, self.get_cpiinc(year), year)
        if elig_year is not None:
            cu = self._catchup_factor(elig_year, year)
            if cu is not None:
                rv = unround_benefit(rv / (cu / 100.0 + 1.0), year)
        return rv

    def unapply_cola99(self, pia: float) -> float:
        return unapply_cola(pia, self.get_cpiinc(YEAR1999) + 0.1, YEAR1999)

    @staticmethod
    def is_applicable_cola99(year: int, benefit_date: MonthYear) -> bool:
        """The special 1999 COLA (extra 0.1%) applies to the December 1999
        increase for benefits paid August 2001 or later."""
        return year == YEAR1999 and not benefit_date < retire_age.AMEND01

    def deconvert_pia(
        self, elig_year: int, number: int, pia77: float,
        ben_date: MonthYear,
    ) -> float:
        rv = pia77
        if number <= 0 or elig_year < YEAR79:
            return rv
        for year in range(elig_year + number - 1, elig_year - 1, -1):
            if self.is_applicable_cola99(year, ben_date):
                rv = self.unapply_cola99(rv)
            else:
                rv = self.unapply_cola(rv, year, elig_year)
        return rv

    # ---- law parameters a reform can override ----
    #
    # These delegate to present law. A reform supplies a Params subclass
    # that overrides them, which is how PiaParamsLC works: the engine
    # always asks its parameter set rather than a module-level function,
    # so a reform reaches every caller at once.

    def full_ret_age(self, elig_year: int) -> Age:
        return retire_age.full_ret_age(elig_year)

    def full_ret_age_di(
        self, elig_year: int, current_year: int
    ) -> Age:
        return retire_age.full_ret_age_di(elig_year, current_year)

    def early_age_oab(self, sex: int, kbirth: _date) -> Age:
        return retire_age.early_age_oab(sex, kbirth)

    def max_dib_age(self, year: int) -> Age:
        return retire_age.max_dib_age(year)

    def ret_credit(self, elig_year: int) -> float:
        return retire_age.ret_credit(elig_year)

    def factor_ar(self, months_ardri: int) -> float:
        return retire_age.factor_ar(months_ardri)

    def factor_dri(self, months_ardri: int, elig_year: int) -> float:
        return retire_age.factor_dri(months_ardri, elig_year)

    def factor_ar_aged_spouse(self, months_ardri: int) -> float:
        return retire_age.factor_ar_aged_spouse(months_ardri)

    def factor_aged_spouse(self) -> float:
        """The aged spouse benefit factor (50% under present law)."""
        return retire_age.FACTOR_50

    def factor_aged_widow(
        self, months_ardri: int, age: Age, ben_date: MonthYear
    ) -> float:
        return retire_age.factor_aged_widow(months_ardri, age, ben_date)

    def factor_dis_widow(self, ben_date: MonthYear) -> float:
        return retire_age.factor_dis_widow(ben_date)

    def marr_length_for_div_ben(self) -> int:
        """Years of marriage a divorced spouse needs (10 under present
        law)."""
        return 10

    def n_drop_adjustment(self, elig_year: int) -> int:
        """Dropout years removed by a reform; none under present law."""
        return 0

    def use_all_earnings(self, elig_year: int) -> bool:
        """Whether every year of earnings enters the AIME rather than the
        highest n; never under present law."""
        return False

    # ---- special minimum ----

    def get_spec_min_pia(self, at: MonthYear, yoc: int) -> float:
        return self._spec_min_get(self._specmin_pia, self._specmin_pia_2001,
                                  self._specmin_pia_extra, at, yoc)

    def get_spec_min_mfb(self, at: MonthYear, yoc: int) -> float:
        return self._spec_min_get(self._specmin_mfb, self._specmin_mfb_2001,
                                  self._specmin_mfb_extra, at, yoc)

    def _spec_min_get(
        self,
        tables: list[dict[int, float]],
        aug2001: list[float],
        changed: list[float],
        at: MonthYear,
        yoc: int,
    ) -> float:
        year = at.year
        if at.month < self.month_beninc(year):
            if year == 2001 and at.month >= 8:
                return aug2001[yoc - 1] if yoc > 0 else 0.0
            if year == self._spec_min_split:
                # before the benefit increase in the year a reform's new
                # amount starts, that amount applies unindexed
                return changed[yoc - 1] if yoc > 0 else 0.0
            year -= 1
        return tables[yoc - 1][year] if yoc > 0 else 0.0


@lru_cache(maxsize=8)
def present_law(alt: int = 2) -> Params:
    """Present-law parameters under a Trustees Report alternative."""
    return Params(Assumptions.tr_alternative(alt))


@lru_cache(maxsize=16)
def params_for(ialtbi: int, ialtaw: int) -> Params:
    """Present-law parameters with the benefit-increase and average-wage
    assumptions chosen separately, as a .pia assumption line does."""
    return Params(Assumptions.for_alternatives(ialtbi, ialtaw))
