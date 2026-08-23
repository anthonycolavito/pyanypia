"""Writer for the calculator's ``lawchg.dat`` reform file.

Format, per LawChangeRead::read:

    line 1   an id line, ignored
    line 2   one indicator per law-change type, in enum order; 0 is off
    then     for each active type in enum order, its own parameter lines,
             the first of which is always
             ``startYear endYear phaseType [extras...]``

Each type's extra lines follow its own ``read``; the ones this module
supports are documented on their spec classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# LawChange::lawChangeType, in enum order. The position in this list is
# the position in the indicator line.
TYPES = [
    "PRE1977LAW", "BPFRACWAGE", "BPCPI", "EARNINDCPI", "NEWFORMULA",
    "BPSPECRATE", "BPMINCONST", "AGE65COMP", "DECLINEPERC", "NOCPIELIG",
    "NOREINDWID", "WINDFALL", "NEWSPECMIN", "NOOLDSTART", "DIDROP5",
    "TRANSGUAR1", "MARRLENGTH", "TRANSGUAR3", "ALLEARN", "DROPOUTCHG",
    "RETTESTCHG", "SANFORD1", "NOPIATABLE", "NOTRANSGUAR", "TAXRATECHG",
    "SANFORD2", "NRACHANGE", "CHILDCARECREDIT", "RETROWAGEIND",
    "TRANSGUAR4", "WIFEFACTOR", "WIDFACTOR", "TAXBENCHG", "PSAACCT",
    "WAGEBASECHG", "STATELOCAL", "FEDERAL", "CHILDCAREDROPOUT",
    "COLACHANGE", "NODIBGUAR",
]
INDEX = {name: i for i, name in enumerate(TYPES)}


@dataclass
class Change:
    """One active law change.

    ``ind`` selects the variant (its meaning differs per type; 0 is off).
    ``phase_type`` is 0 for new eligibles only, 1 for everyone. ``extras``
    are appended to the first line, and ``lines`` are whole extra lines
    that follow it.
    """

    name: str
    ind: int
    start_year: int
    end_year: int
    phase_type: int = 0
    extras: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def render(self) -> list[str]:
        first = [str(self.start_year), str(self.end_year),
                 str(self.phase_type), *self.extras]
        return [" ".join(first), *self.lines]


def write_lawchg(changes: list[Change], title: str = "pyanypia") -> str:
    """Renders a ``lawchg.dat`` for the given changes."""
    by_name = {c.name: c for c in changes}
    unknown = set(by_name) - set(INDEX)
    if unknown:
        raise ValueError(f"unknown law-change types: {sorted(unknown)}")
    indicators = [
        str(by_name[name].ind if name in by_name else 0) for name in TYPES
    ]
    out = [f"$Id: {title} $", " ".join(indicators)]
    for name in TYPES:
        change = by_name.get(name)
        if change is not None and change.ind > 0:
            out.extend(change.render())
    return "\n".join(out) + "\n"


# ---- the changes this project supports, as constructors ----------------


def nra_change(ind: int, start_year: int, end_year: int,
               phase_type: int = 0) -> Change:
    """Full retirement age: 1 holds it at 65, 2 removes the 66-to-67
    plateau, 3 also indexes it upward after 2011."""
    return Change("NRACHANGE", ind, start_year, end_year, phase_type)


def cola_change(adjustment: float, start_year: int, end_year: int,
                phase_type: int = 1) -> Change:
    """Benefit increases reduced by `adjustment` percentage points."""
    return Change("COLACHANGE", 1, start_year, end_year, phase_type,
                  extras=[f"{adjustment}"])


def bend_point_fraction(proportion: float, start_year: int, end_year: int,
                        phase_type: int = 0) -> Change:
    """Bend points rise at `proportion` of the wage rate."""
    return Change("BPFRACWAGE", 1, start_year, end_year, phase_type,
                  extras=[f"{proportion}"])


def bend_point_minus_constant(constant: float, start_year: int,
                              end_year: int, phase_type: int = 0) -> Change:
    """Bend points rise at the wage rate less `constant` percentage
    points (LawChangeBPMINCONST, which reads it as the 4th field)."""
    return Change("BPMINCONST", 1, start_year, end_year, phase_type,
                  extras=[f"{constant}"])


def di_dropout_five(start_year: int, end_year: int,
                    phase_type: int = 0) -> Change:
    """A flat five dropout years in place of the one-for-five rule.
    LawChangeDIDROP5 has no read() of its own, so the base class reads
    just the start/end/phase line."""
    return Change("DIDROP5", 1, start_year, end_year, phase_type)


def declining_perc(factors: tuple[float, float, float], start_year: int,
                   end_year: int,
                   later: tuple[tuple[int, tuple[float, float, float]], ...]
                   = (), phase_type: int = 0) -> Change:
    """Benefit formula percentages falling year by year. The indicator is
    how many intervals there are; each one after the first gets its own
    line of `year f0 f1 f2`."""
    lines = [
        " ".join([str(year), *(f"{f}" for f in fs)]) for year, fs in later
    ]
    return Change("DECLINEPERC", 1 + len(later), start_year, end_year,
                  phase_type, extras=[f"{f}" for f in factors], lines=lines)


def childcare_dropout(fq_ratio: float, max_age: int, max_years: int,
                      start_year: int, end_year: int,
                      phase_type: int = 0) -> Change:
    """Widen the child-care dropout years. The maximum age of child is
    part of the file format but the batch path never reads it."""
    return Change("CHILDCAREDROPOUT", 1, start_year, end_year, phase_type,
                  extras=[f"{fq_ratio}", str(max_age), str(max_years)])


def age65_comp(years: int, step: int, start_year: int, end_year: int,
               phase_type: int = 0) -> Change:
    """Move the computation point from 62 towards 65. The indicator is
    how many years it moves; the step phases it in."""
    return Change("AGE65COMP", years, start_year, end_year, phase_type,
                  extras=[str(step)])


def new_special_min(amount: float, start_year: int, end_year: int,
                    phase_type: int = 0) -> Change:
    """A new special-minimum amount per year of coverage. Indicator 1 is
    the amount alone, which LawChangeNEWSPECMIN reads from its own line."""
    return Change("NEWSPECMIN", 1, start_year, end_year, phase_type,
                  lines=[f"{amount:.2f}"])


def wage_base_change(bases: dict[int, float], start_year: int,
                     end_year: int, phase_type: int = 1) -> Change:
    """Ad hoc OASDI wage bases for start_year..end_year."""
    row = " ".join(
        f"{bases[y]:.2f}" for y in range(start_year, end_year + 1)
    )
    return Change("WAGEBASECHG", 1, start_year, end_year, phase_type,
                  lines=[row])


def dropout_change(step: int, start_year: int, end_year: int,
                   phase_type: int = 0) -> Change:
    """One fewer dropout year for every `step` eligibility years."""
    return Change("DROPOUTCHG", 1, start_year, end_year, phase_type,
                  extras=[str(step)])


def wife_factor(start_year: int, end_year: int,
                phase_type: int = 0) -> Change:
    """Aged spouse benefit factor cut from 50% to 33%."""
    return Change("WIFEFACTOR", 1, start_year, end_year, phase_type)


def new_formula(bend_points: dict[int, list[float]],
                percentages: dict[int, list[float]], start_year: int,
                end_year: int, phase_type: int = 0) -> Change:
    """A replacement PIA formula.

    Per LawChangeNEWFORMULA::read: a line giving the number of bend
    points, then one line per eligibility year in the span carrying that
    year's percentages, one more than the bend points, followed by the
    bend points themselves. The year is not on the line -- the lines are
    matched to years by their order.
    """
    num_bp = len(bend_points[start_year])
    lines = [str(num_bp)]
    for year in range(start_year, end_year + 1):
        lines.append(" ".join([
            *(f"{p}" for p in percentages[year]),
            *(f"{b:.2f}" for b in bend_points[year]),
        ]))
    return Change("NEWFORMULA", 1, start_year, end_year, phase_type,
                  lines=lines)
