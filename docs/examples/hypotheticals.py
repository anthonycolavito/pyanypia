"""Hypothetical workers, one at a time."""

from pyanypia import CURRENT_LAW, Auxiliary, family_benefits, retired_worker

# A worker born 15 June 1964 who earned the national average wage every
# year from 22 to 66, claiming at 62 and 1 month, at the normal retirement
# age (67), and at 70. Ages are in months; the PIA includes COLAs to the
# claim month, so it is higher for a later claim.
earnings = {year: float(CURRENT_LAW.awi[year - 1937]) for year in range(1986, 2031)}
for months in (62 * 12 + 1, 67 * 12, 70 * 12):
    b = retired_worker(earnings, 1964, 6, months)
    print(f"claim at {months // 12}y{months % 12}m: AIME {b.aime:,.0f}  "
          f"PIA ${b.pia:,.2f}  benefit ${b.benefit:,.0f}/month")

# The same worker at 67 with the middle bracket cut from 32% to 30%.
reform = CURRENT_LAW.replace(pia_pct=(0.90, 0.30, 0.15))
b = retired_worker(earnings, 1964, 6, 67 * 12, policy=reform)
print(f"reform PIA ${b.pia:,.2f}")

# A spouse born March 1966 who claims at 64, in the month the worker claims at 67.
b = retired_worker(earnings, 1964, 6, 67 * 12)
spouse = Auxiliary("spouse", 1966, 3, claim_age=64 * 12 + 3)
fam = family_benefits(b.pia, b.mfb, [spouse], benefit_year=2031, benefit_month=6)
print(f"spouse benefit ${fam.benefit[0]:,.0f}/month")
