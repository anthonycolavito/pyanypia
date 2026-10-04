"""100,000 synthetic workers in one vectorized call."""

import time

import numpy as np

from pyanypia import CURRENT_LAW, retired_worker

rng = np.random.default_rng(0)
n, first, last = 100_000, 1980, 2045
birth_year = rng.integers(1960, 1983, n)
level = rng.lognormal(mean=0.0, sigma=0.6, size=n)  # earnings relative to the AWI
years = np.arange(first, last + 1)
awi = CURRENT_LAW.awi[years - 1937]
working = (years >= birth_year[:, None] + 22) & (years < birth_year[:, None] + 62)
earnings = np.where(working, level[:, None] * awi, 0.0)
claim_age = rng.integers(62 * 12 + 1, 70 * 12 + 1, n)

start = time.perf_counter()
b = retired_worker(earnings, birth_year, 6, claim_age, first_year=first)
elapsed = time.perf_counter() - start
print(f"{n:,} workers in {elapsed:.1f}s; median benefit ${np.median(b.benefit):,.0f}/month")
