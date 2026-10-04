# pyanypia Formula Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `pyanypia` from a full port of SSA's AnyPIA calculator into a small, NumPy-vectorized library of Social Security benefit-formula functions with overridable policy parameters. The full engine moves to its own repo and serves as the test oracle.

**Architecture:** Pure functions over NumPy arrays: one row per person, earnings as an `(n, Y)` matrix. Each function takes a frozen `Policy` holding primitive policy inputs. Derived series (projected AWI, taxable maximum, bend points, special-minimum table) are built once per `Policy`, using the engine's exact operation order and rounding. Correctness is proven differentially against the archived engine (`anypia_engine`), which is itself penny-exact against SSA's C++.

**Tech Stack:** Python ≥3.11, NumPy ≥1.26, optional pandas; pytest, ruff, mypy (strict); hatchling. Test-only dependency: `anypia-engine` from git.

**Spec:** `docs/superpowers/specs/2026-10-04-formula-library-design.md`

## Global Constraints

- Runtime dependency: `numpy>=1.26` only. pandas stays optional (`pyanypia[pandas]`).
- Python 3.11, 3.12, 3.13 (the CI matrix); ruff line length 100; `mypy --strict` on `src/pyanypia`.
- Penny-exact: every money result must equal the engine's float exactly (`==`), not approximately.
- Data range: years 1937–2105 (the 2026 Trustees Report data). Anything outside raises `ValueError`.
- Scope of exactness: wage-indexed computations with eligibility year ≥ 1979.
- Errors: invalid input raises `ValueError` naming the field. Vectorized validation reports the count of bad rows and the first bad index. No silent clipping, except the statutory taxable-maximum cap on earnings.
- WEP/GPO are off by default (`Policy.wep_enabled=False`, `Policy.gpo_enabled=False`).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Confirm with the user** immediately before: creating the GitHub repo, pushing any tag, creating a release, and pushing/merging to `pyanypia` `main`.
- Never `git add -A` while subagents are working; stage explicit paths.

## Refinements to the spec (decided while planning)

These keep the spec's intent but pin down signatures the spec left loose:

1. Birth-date logic lives in `eligibility_year` / `computation_years`, so the AIME call is `aime(earnings, elig_year, comp_years, *, first_year, last_year=None, policy)`. Callers who want the one-shot path use the convenience functions.
2. `family_max(pia_elig, elig_year, *, policy)` covers retirement and survivor cases. The disability cap is the separate `di_family_max(pia_elig, aime, elig_year, *, policy)`. Both work at eligibility (before COLAs); `apply_colas` carries them forward.
3. `monthly_benefit(pia, factor, benefit_year, benefit_month=12)` takes a factor from `benefit_factor(...)`, so the two pieces are separately usable.
4. The engine package is renamed to `anypia_engine` in the archived repo, so both can be installed together.
5. GPO is not in AnyPIA, so `gpo_offset` is tested against hand arithmetic only. The README says so.
6. Quarters of coverage use one annual rule for every year: `min(4, floor(earnings / qc_amount[year]))`, with the $50 amount before 1978. Before 1978 this is an approximation, because SSA actually counted calendar-quarter wages. The differential tests feed the engine summary QCs computed by the same rule, so both sides agree.

## File Structure

```
src/pyanypia/
  __init__.py      flat public namespace, __version__ = "0.3.0"
  _data2026.py     2026 TR data (moved from params/_data2026.py, unchanged)
  _years.py        FIRST_YEAR/LAST_YEAR, dict->array, validated year lookup
  _arrays.py       coercion, broadcasting, validation, scalar-out
  _project.py      scalar projection formulas (ported from params/projection.py)
  rounding.py      vectorized SSA rounding
  policy.py        Policy, CURRENT_LAW
  dates.py         adjusted_birth, month_index, cola_year
  claiming.py      eligibility_year, NRA, earliest age, AR/DRC factors, monthly_benefit
  earnings.py      capped/indexed earnings, elapsed/computation years, aime, QCs, YOC
  formula.py       bend points, pia, family_max, apply_colas
  minimum.py       special_minimum_pia
  disability.py    di_family_max, childcare_aime
  family.py        Auxiliary, family_benefits
  wep.py           wep_pia, gpo_offset
  convenience.py   Benefit, retired_worker, disabled_worker, deceased_worker
tests/
  conftest.py      engine availability, rng fixture
  engine.py        adapter: our inputs -> anypia_engine Worker -> Results
  cases.py         seeded random case generators
  data/params_alt{1,2,3}.json   C++ oracle parameter goldens (copied)
  test_<module>.py one per module, plus test_diff_<benefit>.py sweeps
docs/examples/hypotheticals.py, docs/examples/microsim.py
```

---

### Task 1: Archive the engine as `anypia-engine`

**Files:** a new local clone at `/Users/anthony/anypia-engine`. Nothing in `pyanypia` changes.

**Interfaces:**
- Produces: the importable package `anypia_engine`, with the same API as pyanypia 0.2.0 (`anypia_engine.Worker`, `compute`, `MonthYear`, `BenefitType`, `Sex`, `DisabilityPeriod`, `FamilyMember`, `anypia_engine.params.present_law`), installable from `git+https://github.com/anthonycolavito/anypia-engine@v0.2.0`.

- [ ] **Step 1: Clone `main` (not the `formula-library` branch) to a sibling directory**

```bash
git clone --branch main /Users/anthony/pyanypia /Users/anthony/anypia-engine
cd /Users/anthony/anypia-engine && git log --oneline -1   # expect 231ec9b
```

- [ ] **Step 2: Rename the package**

```bash
cd /Users/anthony/anypia-engine
git mv src/pyanypia src/anypia_engine
# URLs first (hyphenated repo name), then the import name everywhere else
grep -rl --exclude-dir=.git --exclude-dir=.venv 'anthonycolavito/pyanypia' . \
  | xargs sed -i '' 's#anthonycolavito/pyanypia#anthonycolavito/anypia-engine#g'
grep -rl --exclude-dir=.git --exclude-dir=.venv --include='*.py' --include='*.toml' \
  --include='*.md' --include='*.yml' --include='Makefile' 'pyanypia' . \
  | xargs sed -i '' 's/pyanypia/anypia_engine/g'
sed -i '' 's/^name = "anypia_engine"/name = "anypia-engine"/' pyproject.toml
grep -rn 'pyanypia' --exclude-dir=.git --exclude-dir=.venv . | grep -v '^./oracle/goldens' | head
```
Expected: the last grep prints nothing. Golden data files must not be rewritten: if any `oracle/goldens` file was touched, restore it with `git checkout -- oracle/goldens`.

- [ ] **Step 3: Add the pointer to the README**

Insert directly below the H1 in `README.md`:

```markdown
> **Archived engine.** This is the full AnyPIA port that was pyanypia 0.2.0,
> kept as a reference implementation and as the test oracle for
> [pyanypia](https://github.com/anthonycolavito/pyanypia), which is now a
> vectorized library of benefit-formula functions. Frozen; fixes only.
```

- [ ] **Step 4: Run the full suite in a fresh venv**

```bash
cd /Users/anthony/anypia-engine && uv venv -q .venv && uv pip install -q -e ".[dev,pandas]" \
  && .venv/bin/pytest -q -m "not oracle_smoke" && .venv/bin/ruff check src tests oracle && .venv/bin/mypy
```
Expected: all pass. This is the same suite as pyanypia 0.2.0, with only names changed.

- [ ] **Step 5: Commit**

```bash
git add -u && git add src/anypia_engine README.md
git commit -m "chore: rename to anypia-engine, archived reference engine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: STOP and confirm with the user, then publish**

Ask: "Ready to create public repo anthonycolavito/anypia-engine, push main, tag v0.2.0 and create the release?" Only after a yes:

```bash
cd /Users/anthony/anypia-engine
git remote remove origin
gh repo create anthonycolavito/anypia-engine --public --source . --push \
  --description "Archived pure-Python port of SSA's AnyPIA (2026 TR); test oracle for pyanypia"
git tag -a v0.2.0 -m "anypia-engine 0.2.0 (formerly pyanypia 0.2.0)"
git push origin v0.2.0
gh release create v0.2.0 --title "v0.2.0" --notes "The full AnyPIA port formerly published as pyanypia 0.2.0, renamed to anypia_engine."
```

- [ ] **Step 7: Verify install from git**

```bash
cd "$(mktemp -d)" && uv venv -q && uv pip install -q "anypia-engine @ git+https://github.com/anthonycolavito/anypia-engine@v0.2.0" \
  && .venv/bin/python -c "import anypia_engine as e; print(e.__version__)"
```
Expected: `0.2.0`.

---

### Task 2: Clear the decks — skeleton, vectorized rounding, array helpers

**Files:**
- Delete: `src/pyanypia/{engine,io,params}/`, `src/pyanypia/{worker,results,law,batch,errors,dates}.py`, `oracle/`, `tests/*`, `docs/examples/tour.py`, `dist/`
- Move: `src/pyanypia/params/_data2026.py` → `src/pyanypia/_data2026.py`
- Create: `src/pyanypia/_years.py`, `src/pyanypia/_arrays.py`, `tests/conftest.py`, `tests/test_rounding.py`, `tests/test_arrays.py`
- Rewrite: `src/pyanypia/rounding.py`, `src/pyanypia/__init__.py`, `pyproject.toml`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces:
  - `_years.FIRST_YEAR=1937`, `LAST_YEAR=2105`, `N_YEARS=169`
  - `_years.to_array(values: Mapping[int, float]) -> np.ndarray`, with NaN where absent
  - `_years.at(series, years, name) -> np.ndarray`
  - `_arrays.as_int(name, x) -> np.ndarray`
  - `_arrays.as_float(name, x) -> np.ndarray`
  - `_arrays.check(name, bad, what) -> None`
  - `_arrays.as_earnings(earnings, first_year) -> tuple[np.ndarray(n,Y), int, bool]`, where the last element is `single`
  - `_arrays.out(x) -> float | np.ndarray`
  - `rounding.round_benefit(amount, year)`, `round_wage(v)`, `apply_cola(amount, percent, year)`, `floor_dollar(amount)` (all array in, array out)

- [ ] **Step 1: Delete the engine and move the data file**

```bash
cd /Users/anthony/pyanypia && git switch formula-library
git mv src/pyanypia/params/_data2026.py src/pyanypia/_data2026.py
git rm -r -q src/pyanypia/engine src/pyanypia/io src/pyanypia/params \
  src/pyanypia/worker.py src/pyanypia/results.py src/pyanypia/law.py \
  src/pyanypia/batch.py src/pyanypia/errors.py src/pyanypia/dates.py \
  oracle tests docs/examples/tour.py
rm -rf dist
mkdir -p tests/data && git show main:oracle/goldens/params_alt1.json > tests/data/params_alt1.json
git show main:oracle/goldens/params_alt2.json > tests/data/params_alt2.json
git show main:oracle/goldens/params_alt3.json > tests/data/params_alt3.json
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pyanypia"
version = "0.3.0"
description = "Vectorized Social Security benefit-formula functions, penny-exact with SSA's AnyPIA (2026 TR)"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Anthony Colavito", email = "colavitoanthony@gmail.com" }]
requires-python = ">=3.11"
dependencies = ["numpy>=1.26"]
keywords = ["social-security", "ssa", "anypia", "pia", "aime", "microsimulation"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Science/Research",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3 :: Only",
    "Topic :: Scientific/Engineering",
    "Typing :: Typed",
]

[project.urls]
Homepage = "https://github.com/anthonycolavito/pyanypia"
Changelog = "https://github.com/anthonycolavito/pyanypia/blob/main/CHANGELOG.md"

[project.optional-dependencies]
pandas = ["pandas>=2.0"]
dev = [
    "pytest>=8", "ruff==0.16.*", "mypy==2.3.*",
    "anypia-engine @ git+https://github.com/anthonycolavito/anypia-engine@v0.2.0",
]

[tool.hatch.metadata]
allow-direct-references = true

[tool.hatch.build.targets.wheel]
packages = ["src/pyanypia"]

[tool.hatch.build.targets.sdist]
include = ["/src", "/tests", "/docs/examples", "/README.md", "/CHANGELOG.md", "/LICENSE", "/pyproject.toml"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: large differential sweeps"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/pyanypia"]

[[tool.mypy.overrides]]
module = "pandas.*"
ignore_missing_imports = true
```

- [ ] **Step 3: Write `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push: {branches: [main]}
  pull_request:
permissions: {contents: read}
concurrency: {group: "ci-${{ github.ref }}", cancel-in-progress: true}
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ["3.11", "3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with: {python-version: "${{ matrix.python }}"}
      - run: python -m pip install -e ".[dev,pandas]"
      - run: ruff check src tests docs/examples
      - run: mypy
      - run: pytest -q
```

- [ ] **Step 4: Recreate the venv with the engine**

```bash
cd /Users/anthony/pyanypia && rm -rf .venv && uv venv -q .venv && uv pip install -q -e ".[dev,pandas]"
.venv/bin/python -c "import anypia_engine, numpy; print('ok')"
```
Expected: `ok`. If Task 1 has not been published yet, use `uv pip install -e /Users/anthony/anypia-engine` instead.

- [ ] **Step 5: Write the failing tests**

`tests/conftest.py`:
```python
import numpy as np
import pytest


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20261004)
```

`tests/test_rounding.py`:
```python
import numpy as np
from anypia_engine import rounding as eng

from pyanypia import rounding


def test_round_benefit_matches_engine_across_eras(rng):
    amounts = rng.uniform(0, 5000, 4000)
    amounts[:200] = np.round(amounts[:200], 1) + 0.0005  # near the dime boundary
    for year in (1970, 1975, 1981, 1982, 2000, 2030):
        got = rounding.round_benefit(amounts, year)
        want = [eng.round_benefit(float(a), year) for a in amounts]
        assert got.tolist() == want


def test_round_benefit_per_element_years():
    got = rounding.round_benefit(np.array([100.04, 100.04]), np.array([1981, 1982]))
    assert got.tolist() == [eng.round_benefit(100.04, 1981), eng.round_benefit(100.04, 1982)]


def test_apply_cola_matches_engine(rng):
    amounts = rng.uniform(0, 5000, 2000)
    for pct, year in ((2.5, 2026), (11.2, 1980), (0.0, 2010)):
        got = rounding.apply_cola(amounts, pct, year)
        assert got.tolist() == [eng.apply_cola(float(a), pct, year) for a in amounts]


def test_round_wage_and_floor_dollar():
    assert rounding.round_wage(np.array([1.005, 2.344])).tolist() == [
        np.floor(1.005 * 100 + 0.5) / 100, 2.34]
    assert rounding.floor_dollar(np.array([1234.9, 7.0])).tolist() == [1234.0, 7.0]
```

`tests/test_arrays.py`:
```python
import numpy as np
import pytest

from pyanypia import _arrays, _years


def test_as_earnings_from_dict_fills_gaps():
    m, first, single = _arrays.as_earnings({2000: 10.0, 2002: 30.0}, None)
    assert first == 2000 and single
    assert m.tolist() == [[10.0, 0.0, 30.0]]


def test_as_earnings_matrix_requires_first_year():
    with pytest.raises(ValueError, match="first_year"):
        _arrays.as_earnings(np.zeros((2, 3)), None)


def test_negative_earnings_report_rows():
    e = np.zeros((5, 3))
    e[3, 1] = -1.0
    e[4, 0] = -2.0
    with pytest.raises(ValueError, match=r"earnings: negative in 2 row\(s\); first at row 3"):
        _arrays.as_earnings(e, 2000)


def test_year_lookup_out_of_range():
    series = _years.to_array({y: float(y) for y in range(1937, 2106)})
    assert _years.at(series, np.array([1937, 2105]), "awi").tolist() == [1937.0, 2105.0]
    with pytest.raises(ValueError, match="awi: year outside 1937-2105"):
        _years.at(series, 2106, "awi")


def test_year_lookup_missing_value():
    series = _years.to_array({2000: 1.0})
    with pytest.raises(ValueError, match="cola: no value for year 1999"):
        _years.at(series, 1999, "cola")


def test_as_int_rejects_fractional():
    assert _arrays.as_int("claim_age", 744.0).dtype.kind == "i"
    with pytest.raises(ValueError, match="claim_age: must be whole numbers"):
        _arrays.as_int("claim_age", 744.5)


def test_out_scalarizes():
    assert _arrays.out(np.array(3.0)) == 3.0 and isinstance(_arrays.out(np.array(3.0)), float)
    assert isinstance(_arrays.out(np.array([3.0])), np.ndarray)
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_rounding.py tests/test_arrays.py -q`
Expected: FAIL. `pyanypia._arrays`/`_years` do not exist, and `round_benefit` is scalar-only.

- [ ] **Step 7: Implement**

`src/pyanypia/_years.py`:
```python
"""The year axis every policy series is stored on."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import check

FIRST_YEAR = 1937
LAST_YEAR = 2105
N_YEARS = LAST_YEAR - FIRST_YEAR + 1


def to_array(values: Mapping[int, float]) -> np.ndarray:
    """A year-indexed float array, NaN where `values` has no entry."""
    arr = np.full(N_YEARS, np.nan)
    for year, v in values.items():
        if not FIRST_YEAR <= year <= LAST_YEAR:
            raise ValueError(f"year {year} outside {FIRST_YEAR}-{LAST_YEAR}")
        arr[year - FIRST_YEAR] = v
    return arr


def at(series: np.ndarray, years: ArrayLike, name: str) -> np.ndarray:
    """`series[years]` with range and missing-value checks."""
    y = np.asarray(years)
    check(name, (y < FIRST_YEAR) | (y > LAST_YEAR), f"year outside {FIRST_YEAR}-{LAST_YEAR}")
    vals = series[y - FIRST_YEAR]
    missing = np.isnan(vals)
    if missing.any():
        first = int(np.asarray(y)[missing].ravel()[0]) if y.ndim else int(y)
        raise ValueError(f"{name}: no value for year {first}")
    return vals
```

`src/pyanypia/_arrays.py`:
```python
"""Input coercion and validation shared by every public function."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import ArrayLike


def check(name: str, bad: ArrayLike, what: str) -> None:
    """Raises if any element of `bad` is true, naming the count and first row."""
    b = np.asarray(bad)
    if not b.any():
        return
    if b.ndim == 0:
        raise ValueError(f"{name}: {what}")
    rows = b.reshape(b.shape[0], -1).any(axis=1) if b.ndim > 1 else b
    idx = np.flatnonzero(rows)
    raise ValueError(f"{name}: {what} in {len(idx)} row(s); first at row {idx[0]}")


def as_float(name: str, x: ArrayLike) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    check(name, ~np.isfinite(a), "must be finite")
    return a


def as_int(name: str, x: ArrayLike) -> np.ndarray:
    a = np.asarray(x)
    if a.dtype.kind in "iu":
        return a.astype(np.int64)
    if a.dtype.kind == "b":
        raise ValueError(f"{name}: must be whole numbers, not booleans")
    f = np.asarray(a, dtype=float)
    check(name, ~np.isfinite(f) | (f != np.floor(f)), "must be whole numbers")
    return f.astype(np.int64)


def as_earnings(
    earnings: Mapping[int, float] | ArrayLike, first_year: int | None
) -> tuple[np.ndarray, int, bool]:
    """Returns (matrix (n, Y), first_year, single).

    A `{year: amount}` dict or a 1-D array is one worker (`single=True`);
    a 2-D array is one row per worker and needs `first_year`.
    """
    if isinstance(earnings, Mapping):
        if not earnings:
            raise ValueError("earnings: empty")
        lo, hi = min(earnings), max(earnings)
        row = np.zeros(hi - lo + 1)
        for year, v in earnings.items():
            row[year - lo] = v
        m, first, single = row[None, :], lo, True
    else:
        a = np.asarray(earnings, dtype=float)
        if first_year is None:
            raise ValueError("first_year: required when earnings is an array")
        if a.ndim == 1:
            m, single = a[None, :], True
        elif a.ndim == 2:
            m, single = a, False
        else:
            raise ValueError(f"earnings: must be 1-D or 2-D, got {a.ndim}-D")
        first = int(first_year)
    check("earnings", ~np.isfinite(m), "not finite")
    check("earnings", m < 0, "negative")
    from pyanypia._years import FIRST_YEAR, LAST_YEAR

    if first < FIRST_YEAR or first + m.shape[1] - 1 > LAST_YEAR:
        raise ValueError(f"earnings: years must lie within {FIRST_YEAR}-{LAST_YEAR}")
    return m, first, single


def out(x: Any) -> Any:
    """0-d arrays come back as Python scalars; everything else unchanged."""
    a = np.asarray(x)
    return a.item() if a.ndim == 0 else a
```

(`_years` imports `check` from `_arrays`, and `_arrays` imports `_years` lazily inside `as_earnings`, which avoids a cycle.)

`src/pyanypia/rounding.py`:
```python
"""SSA rounding rules, vectorized. Transliterated from BenefitAmount.cpp.

Constants and operation order are copied from the C++ so results match the
official calculator bit-for-bit on IEEE doubles. Do not "clean up" the
arithmetic.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

AMEND73_YEAR = 1973
AMEND82_YEAR = 1982


def round_benefit(amount: ArrayLike, year: ArrayLike) -> np.ndarray:
    """Rounds a PIA or MFB to a multiple of $0.10: down from 1982, up before
    (with a half-cent margin through 1972). `year` is the benefit-increase
    year, or the year before a wage-indexed formula's eligibility year."""
    a = np.asarray(amount, dtype=float)
    y = np.asarray(year)
    down = np.floor(10.0 * a + 0.0005) / 10.0
    q = np.where(y >= AMEND73_YEAR, 0.009, 0.499)
    x100 = np.fmod(a * 100.0, 10.0)
    up = np.where(x100 < q, a - x100 / 100.0, a + (0.10 - x100 / 100.0))
    return np.asarray(np.where(y >= AMEND82_YEAR, down, up))


def round_wage(value: ArrayLike) -> np.ndarray:
    """Earnings and average wages round to the cent."""
    return np.asarray(np.floor(np.asarray(value, dtype=float) * 100.0 + 0.5) / 100.0)


def apply_cola(amount: ArrayLike, percent: ArrayLike, year: ArrayLike) -> np.ndarray:
    a = np.asarray(amount, dtype=float) * (1.0 + np.asarray(percent, dtype=float) / 100.0)
    return round_benefit(a, year)


def floor_dollar(amount: ArrayLike) -> np.ndarray:
    """Benefits from June 1982 are paid in whole dollars, rounded down."""
    return np.asarray(np.floor(np.asarray(amount, dtype=float)))
```

`src/pyanypia/__init__.py` (it grows in later tasks):
```python
"""pyanypia: Social Security benefit-formula functions, penny-exact with SSA's AnyPIA."""

from __future__ import annotations

__version__ = "0.3.0"

__all__: list[str] = []
```

- [ ] **Step 8: Run the tests to verify they pass, then lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests && .venv/bin/mypy`
Expected: PASS, with no lint or type errors.

- [ ] **Step 9: Commit**

```bash
git add -u && git add pyproject.toml .github/workflows/ci.yml src/pyanypia tests
git commit -m "refactor!: drop the full engine; vectorized rounding and array helpers

The engine now lives in anthonycolavito/anypia-engine.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `Policy` and its derived series

**Files:**
- Create: `src/pyanypia/_project.py`, `src/pyanypia/policy.py`, `tests/test_policy.py`
- Modify: `src/pyanypia/__init__.py`

**Interfaces:**
- Consumes: `_years.to_array`, `_years.at`, `rounding.round_benefit`, `rounding.apply_cola`
- Produces:
  - `Policy` (a frozen dataclass; fields below) with `Policy.current_law(alt=2)`, `.replace(**changes)`, `.with_series(name, {year: value})`
  - Cached `np.ndarray` attributes indexed by `year - 1937`: `.awi`, `.cola`, `.taxmax`, `.base77`, `.qc_amount`, `.yoc_specmin`, `.yoc_wep`, `.nra` (months, by the year of attaining 62), `.drc_rate_by_elig`
  - `.spec_min_tables -> tuple[pia (20, N_YEARS), mfb (20, N_YEARS), pia_aug2001 (20,), mfb_aug2001 (20,)]`
  - `CURRENT_LAW: Policy`
  - `SERIES: tuple[str, ...]`, the series names `with_series` accepts

- [ ] **Step 1: Write the failing tests** — `tests/test_policy.py`

```python
import json
import pathlib

import numpy as np
import pytest
from anypia_engine.dates import MonthYear
from anypia_engine.params import present_law

from pyanypia import CURRENT_LAW, Policy
from pyanypia._years import FIRST_YEAR, LAST_YEAR

DATA = pathlib.Path(__file__).parent / "data"
YEARS = range(FIRST_YEAR, LAST_YEAR + 1)


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_series_match_engine(alt):
    pol, eng = Policy.current_law(alt), present_law(alt)
    for name, ours, theirs, first in (
        ("awi", pol.awi, eng.fq, 1937),
        ("taxmax", pol.taxmax, eng.base_oasdi, 1937),
        ("base77", pol.base77, eng.base_77, 1937),
        ("qc_amount", pol.qc_amount, eng.qc_amt, 1937),
        ("yoc_specmin", pol.yoc_specmin, eng.yoc_amt_specmin, 1951),
        ("yoc_wep", pol.yoc_wep, eng.yoc_amt_windfall, 1951),
        ("cola", pol.cola, eng.cpiinc, 1951),
    ):
        for y in range(first, LAST_YEAR + 1):
            assert ours[y - FIRST_YEAR] == theirs[y], (name, y)


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_against_cpp_parameter_goldens(alt):
    g = json.loads((DATA / f"params_alt{alt}.json").read_text())
    pol = Policy.current_law(alt)
    for ys, row in g["years"].items():
        y = int(ys) - FIRST_YEAR
        assert pol.awi[y] == row["fq"], ys
        assert pol.taxmax[y] == row["base_oasdi"], ys
        assert pol.qc_amount[y] == row["qc_amt"], ys


def test_spec_min_table_matches_engine():
    pol, eng = CURRENT_LAW, present_law(2)
    pia, mfb, pia01, mfb01 = pol.spec_min_tables
    for yoc in range(1, 21):
        for y in range(1979, LAST_YEAR + 1):
            if y == 2001:
                continue
            assert pia[yoc - 1, y - FIRST_YEAR] == eng.get_spec_min_pia(MonthYear(y, 12), yoc)
            assert mfb[yoc - 1, y - FIRST_YEAR] == eng.get_spec_min_mfb(MonthYear(y, 12), yoc)
        assert pia01[yoc - 1] == eng.get_spec_min_pia(MonthYear(2001, 9), yoc)
        assert mfb01[yoc - 1] == eng.get_spec_min_mfb(MonthYear(2001, 9), yoc)


def test_nra_and_drc_by_eligibility_year():
    assert CURRENT_LAW.nra[1999 - FIRST_YEAR] == 780
    assert CURRENT_LAW.nra[2002 - FIRST_YEAR] == 786
    assert CURRENT_LAW.nra[2022 - FIRST_YEAR] == 804
    assert CURRENT_LAW.drc_rate_by_elig[2030 - FIRST_YEAR] == 2.0 / 300.0


def test_awi_growth_flows_into_taxmax():
    higher = CURRENT_LAW.replace(
        awi_growth={y: g + 1.0 for y, g in CURRENT_LAW.awi_growth.items()})
    i = 2040 - FIRST_YEAR
    assert higher.awi[i] > CURRENT_LAW.awi[i]
    assert higher.taxmax[i] > CURRENT_LAW.taxmax[i]
    assert higher.awi[2024 - FIRST_YEAR] == CURRENT_LAW.awi[2024 - FIRST_YEAR]


def test_with_series_overrides_one_year_only():
    p = CURRENT_LAW.with_series("taxmax", {2030: 250000.0})
    assert p.taxmax[2030 - FIRST_YEAR] == 250000.0
    assert p.taxmax[2031 - FIRST_YEAR] == CURRENT_LAW.taxmax[2031 - FIRST_YEAR]


def test_validation():
    with pytest.raises(ValueError, match="pia_pct"):
        CURRENT_LAW.replace(pia_pct=(0.9, 0.32))
    with pytest.raises(ValueError, match="unknown series"):
        CURRENT_LAW.with_series("bogus", {2030: 1.0})
    with pytest.raises(ValueError, match="alt"):
        Policy.current_law(4)


def test_current_law_defaults():
    assert CURRENT_LAW.wep_enabled is False and CURRENT_LAW.gpo_enabled is False
    assert CURRENT_LAW.pia_pct == (0.90, 0.32, 0.15)
    assert np.isnan(CURRENT_LAW.yoc_specmin[1950 - FIRST_YEAR])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_policy.py -q`
Expected: FAIL with `ImportError: cannot import name 'CURRENT_LAW'`.

- [ ] **Step 3: Write `src/pyanypia/_project.py`**

This is a scalar port of the engine's `params/projection.py`, with the operation order unchanged. `project_qc_amounts` gains a `base` parameter, and `project_special_min` takes a fixed amount.

```python
"""Projection formulas for derived policy series (scalar, run once per Policy).

Transliterated from the engine's params/projection.py (avgwg.cpp, wbgenrl.cpp,
qcamt.cpp, piaparms.cpp). Operation order and rounding are copied exactly;
do not simplify the arithmetic.
"""

from __future__ import annotations

import math

YEAR79 = 1979
AUTO_YEAR = 1978
MAXEARN = 99999999.0
SPEC_MIN_MAX_YEARS = 20


def round_wage(value: float) -> float:
    return math.floor(value * 100.0 + 0.5) / 100.0


def round_benefit(amount: float, year: int) -> float:
    if year >= 1982:
        return math.floor(10.0 * amount + 0.0005) / 10.0
    q = 0.009 if year >= 1973 else 0.499
    x100 = math.fmod(amount * 100.0, 10.0)
    if x100 < q:
        return amount - x100 / 100.0
    return amount + (0.10 - x100 / 100.0)


def apply_cola(amount: float, percent: float, year: int) -> float:
    amount *= 1.0 + percent / 100.0
    return round_benefit(amount, year)


def project_fq(fq: dict[int, float], fqinc: dict[int, float], first: int, last: int) -> None:
    for y in range(first, last + 1):
        fq[y] = round_wage(fq[y - 1] * (fqinc[y] / 100.0 + 1.0))


def project_base(
    base: dict[int, float], fq: dict[int, float], cpi: dict[int, float],
    wage_base_ind: int, first: int, last: int,
) -> None:
    """WageBaseGeneral::project. wage_base_ind: 0 = OASDI, 2 = old-law (1977)."""
    defcomp = 0.0149249
    y = first
    while y <= last:
        iflag = 0
        while cpi.get(y + iflag - 1, 0.0) < 0.1:
            base[y + iflag] = base[y - 1]
            iflag += 1
            if y + iflag > last:
                return
        i3 = y + iflag
        baseun = base[y - 1]
        if i3 < 1995:
            for i2 in range(0, iflag + 1):
                yr = y + i2
                if wage_base_ind != 1 and 1989 < yr < 1993:
                    if yr == 1990:
                        factor = fq[yr - 2] / fq[yr - 3] + 0.02
                    elif yr == 1991:
                        factor = (fq[yr - 2] + 0.02 * fq[yr - 3]) / (fq[yr - 3] + 0.02 * fq[yr - 4])
                    else:
                        factor = (fq[yr - 2] * (1.0 + defcomp)) / (fq[yr - 3] + 0.02 * fq[yr - 4])
                else:
                    factor = fq[yr - 2] / fq[yr - 3]
                baseun = (baseun + 0.001) * factor
        else:
            factor = fq[i3 - 2] / fq[1992]
            if wage_base_ind == 2:
                baseun = 45000.0 * factor
            else:
                baseun = 60600.0 * factor if wage_base_ind < 2 else MAXEARN
        if wage_base_ind != 2 and YEAR79 <= i3 < 1982:
            base[i3] = {1979: 22900.0, 1980: 25900.0}.get(i3, 29700.0)
        else:
            base[i3] = 300.0 * math.floor(baseun / 300.0 + 0.5)
        if base[i3] < base[i3 - 1]:
            base[i3] = base[i3 - 1]
        y = i3 + 1


def project_qc_amounts(fq: dict[int, float], last: int, base: float = 250.0) -> dict[int, float]:
    """$50 through 1977, then indexed from `base` (1978)."""
    out: dict[int, float] = {y: 50.0 for y in range(1937, AUTO_YEAR)}
    out[AUTO_YEAR] = base
    for y in range(AUTO_YEAR, last + 1):
        factor = fq[y - 2] / fq[AUTO_YEAR - 2]
        k = int((factor * base + 4.99) / 10.0)
        out[y] = float(k) * 10.0
        if out[y] < out[y - 1]:
            out[y] = out[y - 1]
    return out


def project_special_min(
    cpiinc: dict[int, float], last_year: int, amount: float
) -> tuple[list[dict[int, float]], list[dict[int, float]], list[float], list[float]]:
    """PiaParamsLC::projectSpecMin over one range from 1979: (pia tables, mfb
    tables, Aug-2001 pias, Aug-2001 mfbs), indexed by years-of-coverage-minus-11."""
    pia_tables: list[dict[int, float]] = [{} for _ in range(SPEC_MIN_MAX_YEARS)]
    mfb_tables: list[dict[int, float]] = [{} for _ in range(SPEC_MIN_MAX_YEARS)]
    pia_2001: list[float] = []
    mfb_2001: list[float] = []

    def cola(amt: float, year: int) -> float:
        return apply_cola(amt, cpiinc[year], year)

    def cola_mfb(mfb: float, year: int, pia: float) -> float:
        return max(apply_cola(mfb, cpiinc[year], year), round_benefit(1.5 * pia, year))

    for num_years in range(SPEC_MIN_MAX_YEARS):
        pia = (num_years + 1) * amount
        mfb = round_benefit(1.5 * pia, YEAR79)
        da_pia, da_mfb = pia_tables[num_years], mfb_tables[num_years]
        da_pia[1978], da_mfb[1978] = pia, mfb
        for year in range(YEAR79, min(2000, last_year) + 1):
            pia = cola(pia, year)
            da_pia[year] = pia
            mfb = cola_mfb(mfb, year, pia)
            da_mfb[year] = mfb
        pia1999 = apply_cola(da_pia[1998], cpiinc[1999] + 0.1, 1999)
        mfb1999 = max(apply_cola(da_mfb[1998], cpiinc[1999] + 0.1, 1999),
                      round_benefit(1.5 * pia1999, 1999))
        pia1999 = cola(pia1999, 2000)
        pia_2001.append(pia1999)
        mfb1999 = cola_mfb(mfb1999, 2000, pia)
        mfb_2001.append(mfb1999)
        pia = cola(pia1999, 2001)
        da_pia[2001] = pia
        mfb = cola_mfb(mfb1999, 2001, pia)
        da_mfb[2001] = mfb
        for year in range(2002, last_year + 1):
            pia = cola(pia, year)
            da_pia[year] = pia
            mfb = cola_mfb(mfb, year, pia)
            da_mfb[year] = mfb
    return pia_tables, mfb_tables, pia_2001, mfb_2001
```

Note: `cola_mfb(mfb1999, 2000, pia)` deliberately passes the pre-1999-recalculation `pia`, exactly as the engine does. Do not "fix" it.

- [ ] **Step 4: Write `src/pyanypia/policy.py`**

```python
"""Policy parameters: the primitive inputs a reform can change, and the
series derived from them with AnyPIA's operation order and rounding."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np

from pyanypia import _data2026 as d
from pyanypia import _project as proj
from pyanypia._years import FIRST_YEAR, LAST_YEAR, N_YEARS, to_array

SERIES = ("awi", "cola", "taxmax", "base77", "qc_amount", "yoc_specmin", "yoc_wep", "nra")


def _series(values: tuple[float, ...], first: int) -> dict[int, float]:
    return {first + i: float(v) for i, v in enumerate(values)}


def _statutory_nra(elig_year: int) -> int:
    """Normal retirement age in months by year of attaining 62."""
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


@dataclass(frozen=True, eq=False)
class Policy:
    """Everything a benefit computation reads that a reform could change.

    Primitive fields are inputs; the cached array attributes (`awi`, `taxmax`,
    `qc_amount`, ...) are derived from them on first use, indexed by
    `year - 1937`. Use `replace` to change primitives (changes flow into every
    derived series) and `with_series` to pin individual derived values.
    """

    awi_hist: Mapping[int, float]
    awi_growth: Mapping[int, float]
    cola_hist: Mapping[int, float]
    cola_proj: Mapping[int, float]
    taxmax_hist: Mapping[int, float]
    base77_hist: Mapping[int, float]
    pia_bend_base: tuple[float, ...] = (180.0, 1085.0)
    pia_pct: tuple[float, ...] = (0.90, 0.32, 0.15)
    mfb_bend_base: tuple[float, float, float] = (230.0, 332.0, 433.0)
    mfb_pct: tuple[float, float, float, float] = (1.50, 2.72, 1.34, 1.75)
    ar_rate_first: float = 5.0 / 900.0
    ar_rate_later: float = 5.0 / 1200.0
    ar_months_first: int = 36
    spouse_ar_rate_first: float = 25.0 / 3600.0
    drc_rate: float | None = None
    qc_base: float = 250.0
    spec_min_amount: float = 11.50
    wep_enabled: bool = False
    gpo_enabled: bool = False
    gpo_fraction: float = 2.0 / 3.0
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

    def replace(self, **changes: object) -> Policy:
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]

    def with_series(self, name: str, values: Mapping[int, float]) -> Policy:
        """Pins derived-series values for specific years (final values; later
        years are not re-projected from them)."""
        if name not in SERIES:
            raise ValueError(f"unknown series {name!r}; expected one of {SERIES}")
        merged = {k: dict(v) for k, v in self.overrides.items()}
        merged.setdefault(name, {}).update(values)
        return self.replace(overrides=merged)

    # ---- derived series ----

    def _finish(self, name: str, arr: np.ndarray) -> np.ndarray:
        for year, v in self.overrides.get(name, {}).items():
            if not FIRST_YEAR <= year <= LAST_YEAR:
                raise ValueError(f"{name}: override year {year} outside {FIRST_YEAR}-{LAST_YEAR}")
            arr[year - FIRST_YEAR] = v
        arr.setflags(write=False)
        return arr

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
        b = self.base77
        vals = {y: (0.25 if y < 1991 else 0.15) * float(b[y - FIRST_YEAR])
                for y in range(1951, LAST_YEAR + 1)}
        return self._finish("yoc_specmin", to_array(vals))

    @cached_property
    def yoc_wep(self) -> np.ndarray:
        b = self.base77
        vals = {y: 0.25 * float(b[y - FIRST_YEAR]) for y in range(1951, LAST_YEAR + 1)}
        return self._finish("yoc_wep", to_array(vals))

    @cached_property
    def nra(self) -> np.ndarray:
        """NRA in months, by year of attaining 62."""
        arr = np.array([float(_statutory_nra(y)) for y in range(FIRST_YEAR, LAST_YEAR + 1)])
        return self._finish("nra", arr)

    @cached_property
    def drc_rate_by_elig(self) -> np.ndarray:
        if self.drc_rate is not None:
            arr = np.full(N_YEARS, float(self.drc_rate))
        else:
            arr = np.array([_statutory_drc(y) for y in range(FIRST_YEAR, LAST_YEAR + 1)])
        arr.setflags(write=False)
        return arr

    @cached_property
    def spec_min_tables(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        pia_t, mfb_t, pia01, mfb01 = proj.project_special_min(
            self._as_dict(self.cola), LAST_YEAR, self.spec_min_amount)
        pia = np.stack([to_array(t) for t in pia_t])
        mfb = np.stack([to_array(t) for t in mfb_t])
        out = (pia, mfb, np.array(pia01), np.array(mfb01))
        for a in out:
            a.setflags(write=False)
        return out


CURRENT_LAW = Policy.current_law(2)
```

Add the exports to `__init__.py`: `from pyanypia.policy import CURRENT_LAW, Policy` and extend `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_policy.py -q`
Expected: PASS. If one year diverges, compare the engine's dict for the year before (projection chains forward) and check `project_base`'s `first` argument (`max(hist)+1` = 2027).

- [ ] **Step 6: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/_project.py src/pyanypia/policy.py src/pyanypia/__init__.py tests/test_policy.py
git commit -m "feat: Policy with derived series, matching the engine for all three TR alternatives

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Dates and claiming-age functions

**Files:**
- Create: `src/pyanypia/dates.py`, `src/pyanypia/claiming.py`, `tests/test_claiming.py`
- Modify: `src/pyanypia/__init__.py`

**Interfaces:**
- Consumes: `Policy.nra`, `Policy.drc_rate_by_elig`, `Policy.ar_*`, `_years.at`, `_arrays.*`, `rounding.round_benefit`, `rounding.floor_dollar`
- Produces:
  - `dates.adjusted_birth(birth_year, birth_month, birth_day=15) -> (year, month)` arrays. This is the day before birth, which is how SSA counts ages.
  - `dates.month_index(year, month)` → `12*year + month - 1`
  - `dates.from_month_index(i) -> (year, month)`
  - `dates.cola_year(year, month)` gives the year of the last benefit increase in effect
  - `claiming.eligibility_year(birth_year, birth_month, *, birth_day=15, onset_year=None, death_year=None)`
  - `claiming.normal_retirement_age(birth_year, birth_month, *, birth_day=15, policy)` returns months
  - `claiming.earliest_claim_age(birth_day)` returns months: 744 or 745
  - `claiming.early_reduction_factor(months, *, policy)`
  - `claiming.spouse_reduction_factor(months, *, policy)`
  - `claiming.delayed_credit_factor(months, elig_year, *, policy)`
  - `claiming.benefit_factor(birth_year, birth_month, claim_age, *, birth_day=15, benefit_age=None, policy) -> factor`
  - `claiming.adjustment_months(...)`, with the same arguments, returns `(ar_months, drc_months)`
  - `claiming.monthly_benefit(pia, factor, benefit_year, benefit_month=12) -> dollars`

Ages are whole months from the **adjusted** birth month to the entitlement month. Someone born 15 March 1964 is age 744 (62y0m) in March 2026.

- [ ] **Step 1: Write the failing tests** — `tests/test_claiming.py`

```python
from datetime import date, timedelta

import numpy as np
import pytest
from anypia_engine.dates import Age, MonthYear
from anypia_engine.params import retire_age as ra

from pyanypia import CURRENT_LAW, claiming, dates


def test_adjusted_birth_first_of_month():
    y, m = dates.adjusted_birth(np.array([1960, 1960, 1960]), np.array([1, 3, 3]),
                                np.array([1, 1, 2]))
    assert y.tolist() == [1959, 1960, 1960] and m.tolist() == [12, 2, 3]


def test_cola_year():
    assert dates.cola_year(np.array([2026, 2026, 1980, 1980]),
                           np.array([11, 12, 5, 6])).tolist() == [2025, 2026, 1979, 1980]


def test_eligibility_year():
    assert claiming.eligibility_year(1960, 1, birth_day=1) == 2021
    assert claiming.eligibility_year(1960, 1) == 2022
    assert claiming.eligibility_year(1960, 6, onset_year=2005) == 2005
    assert claiming.eligibility_year(1960, 6, death_year=2030) == 2022


def test_nra_matches_engine():
    for by in range(1930, 2001):
        got = claiming.normal_retirement_age(by, 6)
        assert got == ra.full_ret_age(by + 62).to_months(), by


def test_earliest_claim_age():
    assert claiming.earliest_claim_age(np.array([1, 2, 3, 15])).tolist() == [744, 744, 745, 745]


def test_factors_match_engine():
    months = np.arange(0, 61)
    assert claiming.early_reduction_factor(months).tolist() == [ra.factor_ar(int(m)) for m in months]
    assert claiming.spouse_reduction_factor(months).tolist() == [
        ra.factor_ar_aged_spouse(int(m)) for m in months]
    for elig in (1980, 1990, 2003, 2030):
        assert claiming.delayed_credit_factor(months, elig).tolist() == [
            ra.factor_dri(int(m), elig) for m in months]


def _engine_drc_months(dob: date, claim_age: int, benefit_age: int) -> int:
    kb = dob - timedelta(days=1)
    kb_my = MonthYear(kb.year, kb.month)
    nra = ra.full_ret_age(kb.year + 62)
    fra = kb_my.add_months(nra.to_months())
    return ra.months_dri(fra, kb.year + 62, kb, kb_my.add_months(claim_age),
                         kb_my.add_months(benefit_age), fra)


@pytest.mark.parametrize("dob", [date(1955, 3, 15), date(1960, 1, 1), date(1964, 12, 2)])
def test_drc_months_match_engine(dob):
    for claim in range(780, 861, 7):
        for extra in (0, 5, 14):
            ar, drc = claiming.adjustment_months(dob.year, dob.month, claim, birth_day=dob.day,
                                                 benefit_age=claim + extra)
            nra = claiming.normal_retirement_age(dob.year, dob.month, birth_day=dob.day)
            if claim >= nra:
                assert ar == 0
                assert drc == _engine_drc_months(dob, claim, claim + extra), (claim, extra)


def test_benefit_factor_early_and_late():
    f = claiming.benefit_factor(np.array([1960, 1960]), np.array([6, 6]), np.array([745, 840]))
    assert f[0] == ra.factor_ar(804 - 745)
    assert f[1] == ra.factor_dri(840 - 804, 2022) or f[1] < ra.factor_dri(840 - 804, 2022)


def test_claim_before_earliest_age_raises():
    with pytest.raises(ValueError, match="claim_age: before the earliest"):
        claiming.benefit_factor(1960, 6, 744)


def test_monthly_benefit_rounds_then_floors():
    assert claiming.monthly_benefit(1234.5, 0.7, 2030, 6) == 864.0  # 864.15 -> 864.1 -> 864
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_claiming.py -q`
Expected: FAIL, because `pyanypia.dates` and `pyanypia.claiming` do not exist yet.

- [ ] **Step 3: Implement `src/pyanypia/dates.py`**

```python
"""Month arithmetic. SSA counts ages from the day before birth."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_int, check


def adjusted_birth(
    birth_year: ArrayLike, birth_month: ArrayLike, birth_day: ArrayLike = 15
) -> tuple[np.ndarray, np.ndarray]:
    """(year, month) of the day before birth. Only a birth on the 1st moves it."""
    by, bm, bd = np.broadcast_arrays(as_int("birth_year", birth_year),
                                     as_int("birth_month", birth_month),
                                     as_int("birth_day", birth_day))
    check("birth_month", (bm < 1) | (bm > 12), "must be 1-12")
    check("birth_day", (bd < 1) | (bd > 31), "must be 1-31")
    first = bd == 1
    m = np.where(first, bm - 1, bm)
    y = np.where(first & (m == 0), by - 1, by)
    return y, np.where(m == 0, 12, m)


def month_index(year: ArrayLike, month: ArrayLike) -> np.ndarray:
    return np.asarray(12 * np.asarray(year) + np.asarray(month) - 1)


def from_month_index(i: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(i)
    return a // 12, a % 12 + 1


def cola_year(year: ArrayLike, month: ArrayLike) -> np.ndarray:
    """Year of the latest benefit increase in effect in (year, month).
    Increases are effective December from 1983 and June in 1974-1982."""
    y, m = np.asarray(year), np.asarray(month)
    beninc = np.where(y >= 1983, 12, 6)
    return np.asarray(np.where(m < beninc, y - 1, y))
```

- [ ] **Step 4: Implement `src/pyanypia/claiming.py`**

```python
"""Retirement ages and the reduction or credit for claiming early or late
(PiaParams retirement-age functions and PiaCal::ardriCal)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, check, out
from pyanypia._years import at
from pyanypia.dates import adjusted_birth, cola_year, month_index
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit


def eligibility_year(
    birth_year: ArrayLike, birth_month: ArrayLike, *, birth_day: ArrayLike = 15,
    onset_year: ArrayLike | None = None, death_year: ArrayLike | None = None,
) -> int | np.ndarray:
    """Year of attaining 62, or of disability onset or death if earlier."""
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    e = ky + 62
    if death_year is not None:
        e = np.minimum(e, as_int("death_year", death_year))
    if onset_year is not None:
        e = np.minimum(e, as_int("onset_year", onset_year))
    return out(e)  # type: ignore[no-any-return]


def normal_retirement_age(
    birth_year: ArrayLike, birth_month: ArrayLike, *, birth_day: ArrayLike = 15,
    policy: Policy = CURRENT_LAW,
) -> int | np.ndarray:
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    return out(at(policy.nra, ky + 62, "nra").astype(np.int64))  # type: ignore[no-any-return]


def earliest_claim_age(birth_day: ArrayLike = 15) -> int | np.ndarray:
    """62 for those born on the 1st or 2nd (they attain each age a month
    earlier); otherwise 62 and 1 month, the first month 62 is held all month."""
    bd = as_int("birth_day", birth_day)
    return out(np.where(bd <= 2, 744, 745))  # type: ignore[no-any-return]


def early_reduction_factor(months: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    m = as_int("months", months).astype(float)
    n1 = float(policy.ar_months_first)
    first = 1.0 - m * policy.ar_rate_first
    later = 1.0 - n1 * policy.ar_rate_first - (m - n1) * policy.ar_rate_later
    return np.asarray(np.where(m <= n1, first, later))


def spouse_reduction_factor(months: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    m = as_int("months", months).astype(float)
    n1 = float(policy.ar_months_first)
    first = 1.0 - m * policy.spouse_ar_rate_first
    later = 1.0 - n1 * policy.spouse_ar_rate_first - (m - n1) * policy.ar_rate_later
    return np.asarray(np.where(m < 0, 0.0, np.where(m <= n1, first, later)))


def delayed_credit_factor(
    months: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> np.ndarray:
    m = as_int("months", months).astype(float)
    return np.asarray(1.0 + m * at(policy.drc_rate_by_elig, as_int("elig_year", elig_year),
                                   "drc_rate"))


def adjustment_months(
    birth_year: ArrayLike, birth_month: ArrayLike, claim_age: ArrayLike, *,
    birth_day: ArrayLike = 15, benefit_age: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> tuple[np.ndarray, np.ndarray]:
    """(months of early reduction, months of delayed credit) for a retired worker.

    Delayed credits earned in the year of entitlement are credited the
    following January (PiaParams::monthsDriCal), so a benefit paid in the
    entitlement year counts only the credits through the prior December.
    """
    ky, km = adjusted_birth(birth_year, birth_month, birth_day)
    claim = as_int("claim_age", claim_age)
    ben_age = claim if benefit_age is None else as_int("benefit_age", benefit_age)
    ky, km, claim, ben_age, bd = np.broadcast_arrays(ky, km, claim, ben_age,
                                                     as_int("birth_day", birth_day))
    check("claim_age", claim < np.asarray(earliest_claim_age(bd)),
          "before the earliest retirement age")
    check("benefit_age", ben_age < claim, "before claim_age")
    nra = at(policy.nra, ky + 62, "nra").astype(np.int64)
    kb = month_index(ky, km)
    ent, ben = kb + claim, kb + ben_age
    fra = kb + nra
    age70 = kb + 70 * 12
    jan_ent = 12 * (ent // 12)
    i2 = np.where(age70 <= ent, age70,
                  np.where((age70 <= ben) | (ben // 12 > ent // 12), ent,
                           np.maximum(fra, jan_ent)))
    late = claim >= nra
    ar = np.where(late, 0, nra - claim)
    drc = np.where(late, np.maximum(i2 - fra, 0), 0)
    return ar, drc


def benefit_factor(
    birth_year: ArrayLike, birth_month: ArrayLike, claim_age: ArrayLike, *,
    birth_day: ArrayLike = 15, benefit_age: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> float | np.ndarray:
    """The multiplier on the PIA for a retired worker claiming at `claim_age`."""
    ar, drc = adjustment_months(birth_year, birth_month, claim_age, birth_day=birth_day,
                                benefit_age=benefit_age, policy=policy)
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    ky = np.broadcast_to(ky, ar.shape)
    f = np.where(ar > 0, early_reduction_factor(ar, policy=policy),
                 delayed_credit_factor(drc, ky + 62, policy=policy))
    return out(f)  # type: ignore[no-any-return]


def monthly_benefit(
    pia: ArrayLike, factor: ArrayLike, benefit_year: ArrayLike, benefit_month: ArrayLike = 12
) -> float | np.ndarray:
    """factor x PIA, rounded down to the dime, then paid in whole dollars."""
    cy = cola_year(as_int("benefit_year", benefit_year), as_int("benefit_month", benefit_month))
    unrounded = round_benefit(as_float("factor", factor) * as_float("pia", pia), cy)
    return out(floor_dollar(unrounded))  # type: ignore[no-any-return]
```

Notes for the implementer:
- `early_reduction_factor` must compute `1.0 - m*r1` and `1.0 - n1*r1 - (m-n1)*r2` in exactly this left-to-right order, matching `retire_age.factor_ar`.
- `test_benefit_factor_early_and_late`'s second assertion allows for the entitlement-year DRC rule. The precise DRC check is `test_drc_months_match_engine`.

Export the claiming names, `adjusted_birth` and `cola_year` from `__init__.py`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_claiming.py -q`
Expected: PASS.

- [ ] **Step 6: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/dates.py src/pyanypia/claiming.py src/pyanypia/__init__.py tests/test_claiming.py
git commit -m "feat: claiming ages, reduction and delayed-credit factors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Earnings — capping, indexing, computation years, AIME, coverage

**Files:**
- Create: `src/pyanypia/earnings.py`, `tests/test_earnings.py`
- Modify: `src/pyanypia/__init__.py`

**Interfaces:**
- Consumes: `_arrays.as_earnings/as_int/out/check`, `_years.at/FIRST_YEAR`, `Policy.awi/taxmax/qc_amount/yoc_specmin/yoc_wep`, `dates.adjusted_birth`
- Produces:
  - `capped_earnings(earnings, *, first_year=None, policy) -> (n, Y)`
  - `indexed_earnings(earnings, elig_year, *, first_year=None, policy) -> (n, Y)`. Capped, indexed to `elig_year-2`, and zero before 1951.
  - `elapsed_years(birth_year, birth_month, elig_year, *, birth_day=15, death_year=None) -> n_elapsed`
  - `computation_years(birth_year, birth_month, elig_year, *, birth_day=15, disabled=False, death_year=None) -> n`
  - `aime(earnings, elig_year, comp_years, *, first_year=None, last_year=None, policy)`
  - `select_top(x, n) -> bool mask` (internal, reused by disability)
  - `sum_by_year(x, mask) -> totals` (internal; sequential year-order sum)
  - `quarters_of_coverage(earnings, *, first_year=None, policy) -> (n, Y) int`
  - `fully_insured(earnings, birth_year, birth_month, elig_year, *, first_year=None, birth_day=15, through_year, policy) -> bool`
  - `years_of_coverage(earnings, *, first_year=None, last_year, kind="special_minimum"|"wep", policy) -> int`

- [ ] **Step 1: Write the failing tests** — `tests/test_earnings.py`

```python
import math

import numpy as np
import pytest
from anypia_engine.params import present_law

from pyanypia import CURRENT_LAW, earnings as E
from pyanypia._years import FIRST_YEAR

ENG = present_law(2)


def _engine_aime(earn: dict[int, float], elig: int, n: int, last: int) -> float:
    """Direct transliteration of WageIndGeneral::indexEarnings + orderEarnings
    + totalEarnCal, independent of the vectorized code."""
    idx = elig - 2
    first = max(min(earn), 1951)
    ind = {}
    for y in range(first, last + 1):
        e = min(earn.get(y, 0.0), ENG.base_oasdi[y])
        if y < idx:
            ind[y] = math.floor(ENG.fq[idx] * e / ENG.fq[y] * 100.0 + 0.5) / 100.0
        else:
            ind[y] = e
    order = sorted((v, y) for y, v in ind.items())
    chosen = {y for _, y in order[max(len(order) - n, 0):]}
    total = 0.0
    for y in range(first, last + 1):
        if y in chosen:
            total += ind[y]
    return math.floor(total / (n * 12.0))


def test_aime_matches_reference(rng):
    for _ in range(300):
        by = int(rng.integers(1940, 2000))
        start = by + 22 + int(rng.integers(0, 8))
        last = by + 62 + int(rng.integers(-5, 6))
        earn = {y: float(math.floor(rng.uniform(0, 2.2) * ENG.fq[min(y, 2105)] * 100 + 0.5) / 100)
                for y in range(start, last + 1)}
        for y in rng.choice(list(earn), size=len(earn) // 4, replace=False):
            earn[int(y)] = 0.0
        elig = by + 62
        n = 35
        got = E.aime(earn, elig, n, last_year=last)
        assert got == _engine_aime(earn, elig, n, last), (by, start, last)


def test_aime_vectorized_equals_rows(rng):
    m = rng.uniform(0, 150000, size=(50, 45))
    elig = rng.integers(2020, 2040, size=50)
    n = np.full(50, 35)
    whole = E.aime(m, elig, n, first_year=1980, last_year=2024)
    rows = [E.aime(m[i], int(elig[i]), 35, first_year=1980, last_year=2024) for i in range(50)]
    assert whole.tolist() == rows


def test_tied_earnings_choose_later_years():
    # equal indexed values tie; the result must not depend on which tie is taken
    earn = {y: 1000.0 for y in range(1990, 2030)}
    assert E.aime(earn, 2030, 35, last_year=2029) == _engine_aime(earn, 2030, 35, 2029)


def test_computation_years():
    assert E.computation_years(1960, 6, 2022) == 35
    assert E.computation_years(1990, 6, 2020, disabled=True) == 6   # elapsed 8, drop 1
    assert E.computation_years(1997, 6, 2020, disabled=True) == 2   # floor of 2
    assert E.computation_years(1980, 6, 2010, death_year=2010) == 3  # elapsed 8 - 5


def test_quarters_and_insured():
    qc = E.quarters_of_coverage({2020: 1e6, 2021: 0.0, 2022: 1810.0 * 2})
    assert qc.tolist() == [[4, 0, 2]] or qc.tolist()[0][0] == 4
    earn = {y: 50000.0 for y in range(1990, 2000)}       # 40 QCs
    assert E.fully_insured(earn, 1960, 6, 2022, through_year=2021)
    earn39 = dict(earn)
    earn39[1999] = float(CURRENT_LAW.qc_amount[1999 - FIRST_YEAR] * 3)  # 39 QCs
    assert not E.fully_insured(earn39, 1960, 6, 2022, through_year=2021)


def test_years_of_coverage():
    yoc_amt = CURRENT_LAW.yoc_specmin
    earn = {2000: float(yoc_amt[2000 - FIRST_YEAR]), 2001: float(yoc_amt[2001 - FIRST_YEAR]) - 1}
    assert E.years_of_coverage(earn, last_year=2001) == 1


def test_validation_messages():
    with pytest.raises(ValueError, match="comp_years: must be at least 1"):
        E.aime({2000: 1.0}, 2030, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_earnings.py -q`
Expected: FAIL, because `pyanypia.earnings` does not exist yet.

- [ ] **Step 3: Implement `src/pyanypia/earnings.py`**

```python
"""Earnings-side computations: capping, wage indexing, computation years,
AIME, quarters and years of coverage (WageIndGeneral, PiaMethod, PiaCal)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_earnings, as_int, check, out
from pyanypia._years import FIRST_YEAR, at
from pyanypia.dates import adjusted_birth
from pyanypia.policy import CURRENT_LAW, Policy

Earnings = Mapping[int, float] | ArrayLike


def _years(first: int, width: int) -> np.ndarray:
    return np.arange(first, first + width)


def _squeeze(x: np.ndarray, single: bool) -> np.ndarray:
    return x[0] if single else x


def capped_earnings(
    earnings: Earnings, *, first_year: int | None = None, policy: Policy = CURRENT_LAW
) -> np.ndarray:
    m, first, single = as_earnings(earnings, first_year)
    cap = at(policy.taxmax, _years(first, m.shape[1]), "taxmax")
    return _squeeze(np.minimum(m, cap[None, :]), single)


def _indexed(m: np.ndarray, first: int, elig: np.ndarray, policy: Policy) -> np.ndarray:
    """Capped earnings indexed to elig-2, nominal from elig-2 on, zero before 1951."""
    years = _years(first, m.shape[1])
    capped = np.minimum(m, at(policy.taxmax, years, "taxmax")[None, :])
    awi_idx = at(policy.awi, elig - 2, "awi")[:, None]
    awi_y = at(policy.awi, np.maximum(years, FIRST_YEAR), "awi")[None, :]
    mult = awi_idx * capped
    indexed = np.floor(mult / awi_y * 100.0 + 0.5) / 100.0
    x = np.where(years[None, :] < (elig - 2)[:, None], indexed, capped)
    return np.where(years[None, :] >= 1951, x, 0.0)


def indexed_earnings(
    earnings: Earnings, elig_year: ArrayLike, *, first_year: int | None = None,
    policy: Policy = CURRENT_LAW,
) -> np.ndarray:
    m, first, single = as_earnings(earnings, first_year)
    elig = np.broadcast_to(as_int("elig_year", elig_year), (m.shape[0],))
    return _squeeze(_indexed(m, first, elig, policy), single)


def select_top(x: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Mask of each row's `n` highest values. Ties go to later years, as
    sorting (value, year) pairs does in PiaMethod::orderEarnings."""
    order = np.argsort(x, axis=1, kind="stable")
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.broadcast_to(np.arange(x.shape[1]), x.shape), axis=1)
    return np.asarray(rank >= (x.shape[1] - n)[:, None])


def sum_by_year(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Row sums of the masked values, added in year order like the C++ loop
    (np.sum's pairwise summation can differ in the last bit)."""
    total = np.zeros(x.shape[0])
    for j in range(x.shape[1]):
        total = total + np.where(mask[:, j], x[:, j], 0.0)
    return total


def _window(m: np.ndarray, first: int, last_year: np.ndarray | None) -> np.ndarray:
    if last_year is None:
        return m
    years = _years(first, m.shape[1])
    return np.where(years[None, :] <= last_year[:, None], m, 0.0)


def aime(
    earnings: Earnings, elig_year: ArrayLike, comp_years: ArrayLike, *,
    first_year: int | None = None, last_year: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> float | np.ndarray:
    """Average indexed monthly earnings over the `comp_years` highest years.

    Earnings are capped at the taxable maximum and indexed to the average
    wage two years before `elig_year`. Years after `last_year` (default: all)
    are ignored, which is how a benefit computed for a given month ignores
    later earnings.
    """
    m, first, single = as_earnings(earnings, first_year)
    n_rows = m.shape[0]
    elig = np.broadcast_to(as_int("elig_year", elig_year), (n_rows,))
    n = np.broadcast_to(as_int("comp_years", comp_years), (n_rows,))
    check("comp_years", n < 1, "must be at least 1")
    last = None if last_year is None else np.broadcast_to(as_int("last_year", last_year), (n_rows,))
    x = _indexed(_window(m, first, last), first, elig, policy)
    total = sum_by_year(x, select_top(x, n))
    result = np.floor(total / (n.astype(float) * 12.0))
    return out(result[0] if single else result)  # type: ignore[no-any-return]


def elapsed_years(
    birth_year: ArrayLike, birth_month: ArrayLike, elig_year: ArrayLike, *,
    birth_day: ArrayLike = 15, death_year: ArrayLike | None = None,
) -> np.ndarray:
    """Years after the year of attaining 21 (or after 1950) and before
    eligibility; at least 2 (PiaCal::nElapsedCal)."""
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    e2 = as_int("elig_year", elig_year) - 1
    if death_year is not None:
        e2 = np.minimum(e2, as_int("death_year", death_year) - 1)
    e1 = np.maximum(ky + 21, 1950)
    return np.asarray(np.maximum(e2 - e1, 2))


def computation_years(
    birth_year: ArrayLike, birth_month: ArrayLike, elig_year: ArrayLike, *,
    birth_day: ArrayLike = 15, disabled: ArrayLike = False, death_year: ArrayLike | None = None,
) -> int | np.ndarray:
    """Elapsed years less dropout years: 5, or for a disabled worker one per
    five elapsed years up to 5; never fewer than 2 (PiaCal::nCal)."""
    elapsed = elapsed_years(birth_year, birth_month, elig_year, birth_day=birth_day,
                            death_year=death_year)
    drop = np.where(np.asarray(disabled, dtype=bool), np.minimum(elapsed // 5, 5), 5)
    return out(np.maximum(elapsed - drop, 2))  # type: ignore[no-any-return]


def quarters_of_coverage(
    earnings: Earnings, *, first_year: int | None = None, policy: Policy = CURRENT_LAW
) -> np.ndarray:
    """Annual quarters of coverage, min(4, earnings // QC amount), on uncapped
    earnings. Before 1978 SSA counted calendar-quarter wages; this annual rule
    with the $50 amount is an approximation there."""
    m, first, single = as_earnings(earnings, first_year)
    amt = at(policy.qc_amount, _years(first, m.shape[1]), "qc_amount")
    return _squeeze(np.minimum(4, np.floor(m / amt[None, :])).astype(np.int64), single)


def _qc_total(m: np.ndarray, first: int, through: np.ndarray, policy: Policy) -> np.ndarray:
    years = _years(first, m.shape[1])
    pre51 = np.minimum(np.where(years[None, :] < 1951, m, 0.0).sum(axis=1), 42000.0)
    lump = np.minimum((pre51 / 400.0).astype(np.int64), 56)
    amt = at(policy.qc_amount, np.maximum(years, 1951), "qc_amount")
    qc = np.minimum(4, np.floor(m / amt[None, :])).astype(np.int64)
    keep = (years[None, :] >= 1951) & (years[None, :] <= through[:, None])
    return np.asarray(lump + np.where(keep, qc, 0).sum(axis=1))


def fully_insured(
    earnings: Earnings, birth_year: ArrayLike, birth_month: ArrayLike, elig_year: ArrayLike, *,
    through_year: ArrayLike, first_year: int | None = None, birth_day: ArrayLike = 15,
    policy: Policy = CURRENT_LAW,
) -> bool | np.ndarray:
    """At least one QC per elapsed year (min 6, max 40) by `through_year`."""
    m, first, single = as_earnings(earnings, first_year)
    n_rows = m.shape[0]
    through = np.broadcast_to(as_int("through_year", through_year), (n_rows,))
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    e2 = np.minimum(through, as_int("elig_year", elig_year) - 1)
    e1 = np.maximum(ky + 21, 1950)
    req = np.minimum(40, np.maximum(6, e2 - e1))
    ok = _qc_total(m, first, through, policy) >= req
    return out(ok[0] if single else ok)  # type: ignore[no-any-return]


def years_of_coverage(
    earnings: Earnings, *, last_year: ArrayLike, first_year: int | None = None,
    kind: Literal["special_minimum", "wep"] = "special_minimum", policy: Policy = CURRENT_LAW,
) -> int | np.ndarray:
    """Years of coverage for the special minimum or the WEP, on uncapped
    earnings (PiaMethod::specMinYearsCal); pre-1951 earnings count one year
    per $900, up to 14."""
    m, first, single = as_earnings(earnings, first_year)
    n_rows = m.shape[0]
    last = np.broadcast_to(as_int("last_year", last_year), (n_rows,))
    years = _years(first, m.shape[1])
    series = policy.yoc_specmin if kind == "special_minimum" else policy.yoc_wep
    pre51 = np.minimum(np.where(years[None, :] < 1951, m, 0.0).sum(axis=1), 42000.0)
    pre_years = np.minimum(14, np.floor(pre51 / 900.0)).astype(np.int64)
    amt = at(series, np.maximum(years, 1951), "years_of_coverage")
    hit = (m > amt[None, :] - 0.009) & (years[None, :] >= 1951) & (years[None, :] <= last[:, None])
    total = pre_years + hit.sum(axis=1)
    return out(total[0] if single else total)  # type: ignore[no-any-return]
```

Implementation notes:
- `_indexed` uses `mult / awi_y * 100.0` because the engine computes `temp = (awi_idx*e) / awi[y]` and then `floor(temp*100 + 0.5)/100`. That is the same order.
- Taking `np.maximum(years, FIRST_YEAR)` guards the lookup only, since earnings years are already validated ≥1937.

The pre-1951 QC lump (`min(int(total/400), 56)`) is the engine's `qc3750_simp`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_earnings.py -q`
Expected: PASS. Tighten `test_quarters_and_insured`'s first assertion to the exact list once you have checked `qc_amount[2022]`, so it no longer has an `or` escape.

- [ ] **Step 5: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/earnings.py src/pyanypia/__init__.py tests/test_earnings.py
git commit -m "feat: wage indexing, computation years, AIME, quarters and years of coverage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The benefit formula — bend points, PIA, family maximum, COLAs

**Files:**
- Create: `src/pyanypia/formula.py`, `tests/test_formula.py`
- Modify: `src/pyanypia/__init__.py`

**Interfaces:**
- Consumes: `Policy.awi/cola/pia_*/mfb_*`, `rounding.round_benefit/apply_cola`, `dates.cola_year`
- Produces:
  - `bend_points(elig_year, *, policy) -> (..., k)` floats
  - `family_max_bend_points(elig_year, *, policy) -> (..., 3)`
  - `pia(aime, elig_year, *, policy, pct=None)`. `pct` overrides the percentages, which the WEP uses.
  - `family_max(pia_elig, elig_year, *, policy)`
  - `apply_colas(amount, elig_year, benefit_year, benefit_month=12, *, policy)`

- [ ] **Step 1: Write the failing tests** — `tests/test_formula.py`

```python
import json
import pathlib

import numpy as np
from anypia_engine.dates import MonthYear
from anypia_engine.engine.methods import base as mbase
from anypia_engine.engine.methods import wage_indexed as wi
from anypia_engine.params import present_law

from pyanypia import CURRENT_LAW, formula

ENG = present_law(2)
G = json.loads((pathlib.Path(__file__).parent / "data" / "params_alt2.json").read_text())


def test_bend_points_match_cpp_goldens():
    for ys, row in G["years"].items():
        y = int(ys)
        if y < 1979:
            continue
        assert formula.bend_points(y).tolist() == row["bp_pia"], y
        assert formula.family_max_bend_points(y).tolist() == row["bp_mfb"], y


def test_pia_matches_engine(rng):
    aimes = np.floor(rng.uniform(0, 15000, 3000))
    eligs = rng.integers(1979, 2090, 3000)
    got = formula.pia(aimes, eligs)
    for a, e, g in zip(aimes, eligs, got, strict=True):
        portions = wi.set_portion_aime(float(a), ENG.bend_points_pia(int(e)))
        assert g == wi.aimepia_cal(portions, ENG.perc_pia(int(e)), int(e) - 1)


def test_family_max_matches_engine(rng):
    pias = np.round(rng.uniform(0, 5000, 2000), 1)
    eligs = rng.integers(1979, 2090, 2000)
    got = formula.family_max(pias, eligs)
    for p, e, g in zip(pias, eligs, got, strict=True):
        portions = mbase.set_portion_pia_elig(float(p), ENG.bend_points_mfb(int(e)))
        assert g == mbase.mfb_cal(portions, mbase.PERC_MFB, int(e) - 1)


def _engine_colas(amount: float, elig: int, ben: MonthYear) -> float:
    pia77 = {elig - 1: amount}
    year3 = ben.year - 1 if ben.month < ENG.month_beninc(ben.year) else ben.year
    for y in range(elig, year3 + 1):
        if ENG.is_applicable_cola99(y, ben):
            pia77[y] = ENG.apply_cola99(pia77[y - 1])
        else:
            pia77[y] = ENG.apply_cola(pia77[y - 1], y, elig)
    return pia77.get(year3, amount) if elig <= year3 else amount


def test_apply_colas_matches_engine(rng):
    for _ in range(1500):
        elig = int(rng.integers(1979, 2060))
        by = int(rng.integers(elig, min(elig + 30, 2105) + 1))
        bm = int(rng.integers(1, 13))
        amt = float(np.round(rng.uniform(100, 4000), 1))
        got = formula.apply_colas(amt, elig, by, bm)
        assert got == _engine_colas(amt, elig, MonthYear(by, bm)), (elig, by, bm)


def test_more_brackets_via_policy():
    p = CURRENT_LAW.replace(pia_bend_base=(180.0, 1085.0, 2000.0), pia_pct=(0.9, 0.32, 0.15, 0.05))
    assert formula.bend_points(2030, policy=p).shape == (3,)
    assert formula.pia(20000.0, 2030, policy=p) < formula.pia(20000.0, 2030)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_formula.py -q`
Expected: FAIL, because `pyanypia.formula` does not exist yet.

- [ ] **Step 3: Implement `src/pyanypia/formula.py`**

```python
"""The PIA and family-maximum formulas, and benefit increases (COLAs)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, check, out
from pyanypia._years import at
from pyanypia.dates import cola_year
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import apply_cola, round_benefit

AWI_BASE_YEAR = 1977  # the 1979 bend points are defined against the 1977 AWI


def _index_bend(base: tuple[float, ...], elig: np.ndarray, policy: Policy) -> np.ndarray:
    temp = at(policy.awi, elig - 2, "awi") / policy.awi[AWI_BASE_YEAR - 1937]
    return np.stack([np.floor(b * temp + 0.5) for b in base], axis=-1)


def bend_points(elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    return _index_bend(policy.pia_bend_base, as_int("elig_year", elig_year), policy)


def family_max_bend_points(elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    return _index_bend(policy.mfb_bend_base, as_int("elig_year", elig_year), policy)


def _bracket_sum(x: np.ndarray, bp: np.ndarray, pct: tuple[float, ...]) -> np.ndarray:
    """sum(pct[i] * portion[i]) accumulated left to right, as the C++ does."""
    k = bp.shape[-1]
    parts = [np.minimum(x, bp[..., 0])]
    for i in range(k - 1):
        parts.append(np.maximum(0.0, np.minimum(x - bp[..., i], bp[..., i + 1] - bp[..., i])))
    parts.append(np.maximum(x - bp[..., k - 1], 0.0))
    total = np.zeros(np.shape(parts[0]))
    for p, part in zip(pct, parts, strict=True):
        total = total + p * part
    return total


def pia(
    aime: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW,
    pct: tuple[float, ...] | ArrayLike | None = None,
) -> float | np.ndarray:
    """Primary insurance amount at eligibility (before COLAs)."""
    a = as_float("aime", aime)
    check("aime", a < 0, "negative")
    e = as_int("elig_year", elig_year)
    a, e = np.broadcast_arrays(a, e)
    bp = bend_points(e, policy=policy)
    percents = policy.pia_pct if pct is None else pct
    if isinstance(percents, tuple):
        total = _bracket_sum(a, bp, percents)
    else:  # per-row percentages, shape (..., k+1)
        arr = np.asarray(percents, dtype=float)
        total = _bracket_sum(a, bp, tuple(arr[..., i] for i in range(arr.shape[-1])))
    return out(round_benefit(total, e - 1))  # type: ignore[no-any-return]


def family_max(
    pia_elig: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> float | np.ndarray:
    """Maximum family benefit at eligibility, for retirement and survivor
    cases (disability: see `di_family_max`)."""
    p, e = np.broadcast_arrays(as_float("pia_elig", pia_elig), as_int("elig_year", elig_year))
    bp = family_max_bend_points(e, policy=policy)
    return out(round_benefit(_bracket_sum(p, bp, policy.mfb_pct), e - 1))  # type: ignore[no-any-return]


def apply_colas(
    amount: ArrayLike, elig_year: ArrayLike, benefit_year: ArrayLike,
    benefit_month: ArrayLike = 12, *, policy: Policy = CURRENT_LAW,
) -> float | np.ndarray:
    """Carries a PIA or MFB from eligibility to a benefit month, applying each
    December increase from the eligibility year on (PiaMethod::applyColas).
    The December 1999 increase is 0.1 point higher for benefits from August 2001."""
    a, e, by, bm = np.broadcast_arrays(as_float("amount", amount), as_int("elig_year", elig_year),
                                       as_int("benefit_year", benefit_year),
                                       as_int("benefit_month", benefit_month))
    cy = cola_year(by, bm)
    after_aug2001 = (by > 2001) | ((by == 2001) & (bm >= 8))
    result = a.astype(float).copy()
    if result.size == 0:
        return out(result)
    for y in range(int(e.min()), int(cy.max()) + 1):
        active = (e <= y) & (y <= cy)
        if not active.any():
            continue
        pct = at(policy.cola, y, "cola") + np.where((y == 1999) & after_aug2001, 0.1, 0.0)
        result = np.where(active, apply_cola(result, pct, y), result)
    return out(result)  # type: ignore[no-any-return]
```

Export `bend_points`, `family_max_bend_points`, `pia`, `family_max` and `apply_colas`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_formula.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/formula.py src/pyanypia/__init__.py tests/test_formula.py
git commit -m "feat: bend points, PIA and family-maximum formulas, COLAs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `retired_worker` and the first differential sweep

**Files:**
- Create: `src/pyanypia/convenience.py`, `tests/engine.py`, `tests/cases.py`, `tests/test_diff_retired.py`
- Modify: `src/pyanypia/__init__.py`

**Interfaces:**
- Consumes: everything from Tasks 3–6.
- Produces:
  - `Benefit`, a frozen dataclass with array fields: `elig_year`, `aime`, `pia_elig`, `pia`, `mfb`, `nra`, `factor`, `benefit`, `method`, `insured`. `method` is a str array of `"wage_indexed"` or `"special_minimum"`.
  - `Benefit.to_frame()`
  - `retired_worker(earnings, birth_year, birth_month, claim_age, *, first_year=None, birth_day=15, benefit_age=None, policy) -> Benefit`
  - Test-side `tests/engine.py`: `run_retired(case) -> anypia_engine Results`, `qc_lumps(earn)`
  - Test-side `tests/cases.py`: the `Case` dataclass and `retired_cases(rng, n)`

`retired_worker` works out the benefit for the benefit month (`benefit_age`, defaulting to `claim_age`). It ignores earnings in or after the benefit year, as AnyPIA does when no later recomputation is modelled. The special minimum is wired in by Task 8 and the WEP by Task 11. Leave clearly named seams (`_special_minimum`, `_apply_wep`) that return "not applicable" for now.

- [ ] **Step 1: Write the test-side helpers**

`tests/cases.py`:
```python
"""Seeded random workers for differential sweeps."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from pyanypia import CURRENT_LAW
from pyanypia._years import FIRST_YEAR

AWI, TAXMAX = CURRENT_LAW.awi, CURRENT_LAW.taxmax


@dataclass
class Case:
    birth: tuple[int, int, int]
    earnings: dict[int, float]
    claim_age: int = 0          # months from adjusted birth to entitlement
    benefit_age: int = 0        # months from adjusted birth to benefit month
    extra: dict[str, object] = field(default_factory=dict)


def _cents(x: float) -> float:
    return math.floor(x * 100.0 + 0.5) / 100.0


def career(rng: np.random.Generator, birth_year: int, last_year: int) -> dict[int, float]:
    kind = rng.choice(["steady", "max", "low", "gappy", "short"])
    start = max(birth_year + 22 + int(rng.integers(0, 6)), 1951)
    years = list(range(start, last_year + 1))
    if kind == "short":
        years = years[: int(rng.integers(10, 16))]
    rel = {"steady": rng.uniform(0.3, 2.5), "max": 3.0, "low": rng.uniform(0.08, 0.35),
           "gappy": rng.uniform(0.3, 2.0), "short": rng.uniform(0.5, 1.5)}[kind]
    out = {}
    for y in range(start, last_year + 1):
        wage = rel * AWI[y - FIRST_YEAR] * rng.uniform(0.85, 1.15)
        if kind == "max":
            wage = 1.2 * TAXMAX[y - FIRST_YEAR]
        zero = (kind == "gappy" and rng.random() < 0.3) or y not in years
        out[y] = 0.0 if zero else _cents(wage)
    return out


def retired_cases(rng: np.random.Generator, n: int) -> list[Case]:
    cases = []
    for _ in range(n):
        by, bm = int(rng.integers(1940, 2001)), int(rng.integers(1, 13))
        bd = int(rng.choice([1, 2, 15, 28]))
        earliest = 744 if bd <= 2 else 745
        claim = int(rng.integers(earliest, 845))
        benefit = claim + int(rng.choice([0, 0, 7, 12, 30]))
        ky = by - 1 if (bd == 1 and bm == 1) else by
        km = (bm - 1 or 12) if bd == 1 else bm
        ent_year = (12 * ky + km - 1 + benefit) // 12
        cases.append(Case((by, bm, bd), career(rng, by, ent_year - 1), claim, benefit))
    return cases
```

`tests/engine.py`:
```python
"""Runs our cases through the archived engine (anypia_engine)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import anypia_engine as eng
from anypia_engine.params import present_law

from tests.cases import Case

QC50 = 50.0


def qc_lumps(earn: dict[int, float]) -> int:
    """Pre-1978 QCs under the library's annual rule, for the engine's summary field."""
    return sum(min(4, math.floor(v / QC50)) for y, v in earn.items() if 1951 <= y <= 1977)


def month_from(birth: tuple[int, int, int], months: int) -> eng.MonthYear:
    kb = date(*birth) - timedelta(days=1)
    return eng.MonthYear(kb.year, kb.month).add_months(months)


def run_retired(case: Case, alt: int = 2, **worker_kw: object) -> eng.Results:
    lump = qc_lumps(case.earnings)
    w = eng.Worker(
        dob=date(*case.birth), sex=eng.Sex.MALE, benefit_type=eng.BenefitType.OLD_AGE,
        earnings=case.earnings, entitlement=month_from(case.birth, case.claim_age),
        benefit_date=month_from(case.birth, case.benefit_age),
        qc_total_to_date=lump, qc_total_51_to_date=lump, **worker_kw,  # type: ignore[arg-type]
    )
    return eng.compute(w, params=present_law(alt))
```

- [ ] **Step 2: Write the failing differential test** — `tests/test_diff_retired.py`

```python
import numpy as np
import pytest

from pyanypia import Policy, retired_worker
from tests.cases import retired_cases
from tests.engine import run_retired

SUPPORTED = {"WAGE_IND", "SPEC_MIN"}


def _as_matrix(cases):
    first = min(min(c.earnings) for c in cases)
    last = max(max(c.earnings) for c in cases)
    m = np.zeros((len(cases), last - first + 1))
    for i, c in enumerate(cases):
        for y, v in c.earnings.items():
            m[i, y - first] = v
    cols = lambda k: np.array([c.birth[k] for c in cases])  # noqa: E731
    return m, first, cols(0), cols(1), cols(2)


def _sweep(n: int, alt: int, seed: int) -> None:
    cases = retired_cases(np.random.default_rng(seed), n)
    m, first, by, bm, bd = _as_matrix(cases)
    claim = np.array([c.claim_age for c in cases])
    ben = np.array([c.benefit_age for c in cases])
    ours = retired_worker(m, by, bm, claim, first_year=first, birth_day=bd, benefit_age=ben,
                          policy=Policy.current_law(alt))
    excluded, bad = 0, []
    for i, c in enumerate(cases):
        r = run_retired(c, alt)
        if r.method not in SUPPORTED or not r.insured:
            excluded += 1
            continue
        got = (ours.aime[i], ours.pia[i], ours.mfb[i], ours.factor[i], ours.benefit[i])
        want = (r.aime, r.pia, r.mfb, r.reduction_factor, r.monthly_benefit)
        if got != want:
            bad.append((i, c.birth, c.claim_age, c.benefit_age, got, want))
    assert not bad, f"{len(bad)} mismatches; first: {bad[:3]}"
    assert excluded <= 0.05 * n, f"{excluded} of {n} cases excluded"


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_retired_vs_engine(alt):
    _sweep(400, alt, seed=100 + alt)


@pytest.mark.slow
def test_retired_vs_engine_large():
    _sweep(6000, 2, seed=7)


def test_vectorized_equals_scalar():
    cases = retired_cases(np.random.default_rng(3), 60)
    m, first, by, bm, bd = _as_matrix(cases)
    claim = np.array([c.claim_age for c in cases])
    whole = retired_worker(m, by, bm, claim, first_year=first, birth_day=bd)
    for i in range(60):
        one = retired_worker(m[i], int(by[i]), int(bm[i]), int(claim[i]), first_year=first,
                             birth_day=int(bd[i]))
        assert (one.aime, one.pia, one.benefit) == (whole.aime[i], whole.pia[i], whole.benefit[i])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_diff_retired.py -q`
Expected: FAIL with `ImportError: cannot import name 'retired_worker'`.

- [ ] **Step 4: Implement `src/pyanypia/convenience.py`**

```python
"""One-call benefit computations that chain the formula functions."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia import claiming, earnings, formula
from pyanypia._arrays import as_earnings, as_int
from pyanypia.dates import adjusted_birth, from_month_index, month_index
from pyanypia.policy import CURRENT_LAW, Policy


@dataclass(frozen=True)
class Benefit:
    """Per-worker results; every field is an array (a scalar for one worker)."""

    elig_year: Any
    aime: Any
    pia_elig: Any       # PIA at eligibility, before COLAs
    pia: Any            # PIA at the benefit month
    mfb: Any            # maximum family benefit at the benefit month
    nra: Any            # normal retirement age, months
    factor: Any         # reduction / delayed-credit factor (1.0 when none)
    benefit: Any        # monthly benefit payable, whole dollars
    method: Any         # "wage_indexed" or "special_minimum"
    insured: Any        # fully insured as of the year before the benefit month

    def to_frame(self) -> Any:
        import pandas as pd

        return pd.DataFrame({f.name: np.atleast_1d(getattr(self, f.name)) for f in fields(self)})


def _scalarize(single: bool, **cols: np.ndarray) -> dict[str, Any]:
    if not single:
        return cols
    return {k: (v[0].item() if hasattr(v[0], "item") else v[0]) for k, v in cols.items()}


def _special_minimum(
    m: np.ndarray, first: int, last_year: np.ndarray, ben_y: np.ndarray, ben_m: np.ndarray,
    policy: Policy,
) -> tuple[np.ndarray, np.ndarray]:
    """(special-minimum PIA, MFB) at the benefit month; zeros until Task 8."""
    z = np.zeros(m.shape[0])
    return z, z


def _apply_wep(pia_elig: np.ndarray, **_: Any) -> np.ndarray:
    """Windfall elimination; identity until Task 11."""
    return pia_elig


def _select(
    wage_pia: np.ndarray, wage_mfb: np.ndarray, sm_pia: np.ndarray, sm_mfb: np.ndarray,
    factor: np.ndarray, delayed: np.ndarray, cy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """PiaCal::setHighPia/setSupportPia/piaCal2: the higher PIA wins (ties to
    the wage-indexed method); delayed credits never apply to a special
    minimum PIA, so a late claimer gets the larger of the credited
    wage-indexed benefit and the uncredited special minimum."""
    from pyanypia.rounding import round_benefit

    sm_wins = sm_pia > wage_pia
    pia = np.where(sm_wins, sm_pia, wage_pia)
    mfb = np.where(sm_wins, sm_mfb, wage_mfb)
    support = sm_wins & delayed
    unrounded = np.where(support,
                         np.maximum(round_benefit(factor * wage_pia, cy), sm_pia),
                         round_benefit(factor * pia, cy))
    method = np.where(sm_wins, "special_minimum", "wage_indexed")
    return pia, mfb, unrounded, method


def retired_worker(
    earnings_: Any, birth_year: ArrayLike, birth_month: ArrayLike, claim_age: ArrayLike, *,
    first_year: int | None = None, birth_day: ArrayLike = 15,
    benefit_age: ArrayLike | None = None, noncovered_pension: ArrayLike = 0.0,
    policy: Policy = CURRENT_LAW,
) -> Benefit:
    """A retired worker's benefit for the month at `benefit_age` (default: the
    entitlement month, `claim_age`). Ages are months from the month before
    birth (or the birth month, for a birth after the 1st)."""
    from pyanypia.dates import cola_year
    from pyanypia.rounding import floor_dollar

    m, first, single = as_earnings(earnings_, first_year)
    n = m.shape[0]
    shape = (n,)
    by, bm, bd = (np.broadcast_to(as_int(k, v), shape) for k, v in
                  (("birth_year", birth_year), ("birth_month", birth_month),
                   ("birth_day", birth_day)))
    claim = np.broadcast_to(as_int("claim_age", claim_age), shape)
    ben_age = claim if benefit_age is None else np.broadcast_to(
        as_int("benefit_age", benefit_age), shape)
    ky, km = adjusted_birth(by, bm, bd)
    ben_y, ben_m = from_month_index(month_index(ky, km) + ben_age)
    last_year = ben_y - 1
    elig = ky + 62

    comp = np.asarray(earnings.computation_years(by, bm, elig, birth_day=bd))
    aime = np.asarray(earnings.aime(m, elig, comp, first_year=first, last_year=last_year,
                                    policy=policy))
    pia_elig = np.asarray(formula.pia(aime, elig, policy=policy))
    pia_elig = _apply_wep(pia_elig, aime=aime, elig=elig, m=m, first=first,
                          last_year=last_year, ben_y=ben_y, pension=noncovered_pension,
                          policy=policy)
    mfb_elig = np.asarray(formula.family_max(pia_elig, elig, policy=policy))
    wage_pia = np.asarray(formula.apply_colas(pia_elig, elig, ben_y, ben_m, policy=policy))
    wage_mfb = np.asarray(formula.apply_colas(mfb_elig, elig, ben_y, ben_m, policy=policy))
    sm_pia, sm_mfb = _special_minimum(m, first, last_year, ben_y, ben_m, policy)

    factor = np.asarray(claiming.benefit_factor(by, bm, claim, birth_day=bd,
                                                benefit_age=ben_age, policy=policy))
    nra = np.asarray(claiming.normal_retirement_age(by, bm, birth_day=bd, policy=policy))
    cy = cola_year(ben_y, ben_m)
    pia, mfb, unrounded, method = _select(wage_pia, wage_mfb, sm_pia, sm_mfb, factor,
                                          claim > nra, cy)
    insured = np.asarray(earnings.fully_insured(m, by, bm, elig, through_year=last_year,
                                                first_year=first, birth_day=bd, policy=policy))
    return Benefit(**_scalarize(
        single, elig_year=elig, aime=aime, pia_elig=pia_elig, pia=pia, mfb=mfb, nra=nra,
        factor=factor, benefit=floor_dollar(unrounded), method=method,
        insured=np.atleast_1d(insured)))
```

The `delayed` flag is `claim > nra` (strictly greater), matching `full_ret_age < age_ent` in `set_support_pia`. Export `Benefit` and `retired_worker` from `__init__`.

Naming: the public first parameter should read `earnings`. The sketch calls it `earnings_` only because the module `earnings` is imported under that name. In the real file, import the module as `from pyanypia import earnings as _earn`, name the parameter `earnings`, and do the same in `disabled_worker` and `deceased_worker`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_diff_retired.py -q && .venv/bin/pytest -m slow tests/test_diff_retired.py -q`
Expected: PASS. Low earners whose engine winner is `SPEC_MIN` will mismatch until Task 8. If that pushes failures above zero, temporarily filter on `r.method == "WAGE_IND"` with a `# Task 8 widens this` comment, then restore `SUPPORTED` in Task 8. Debug any mismatch by comparing `aime` first, then `pia_elig`, then COLAs, then factor.

- [ ] **Step 6: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/convenience.py src/pyanypia/__init__.py tests/cases.py tests/engine.py tests/test_diff_retired.py
git commit -m "feat: retired_worker, penny-exact against the engine under all TR alternatives

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Special minimum PIA

**Files:**
- Create: `src/pyanypia/minimum.py`, `tests/test_minimum.py`
- Modify: `src/pyanypia/convenience.py` (`_special_minimum`), `src/pyanypia/__init__.py`, `tests/test_diff_retired.py`

**Interfaces:**
- Consumes: `Policy.spec_min_tables`, `earnings.years_of_coverage`
- Produces: `special_minimum_pia(years_of_coverage, benefit_year, benefit_month=12, *, policy) -> (pia, mfb)` at the benefit month. They are zero for ≤10 years, and use at most 30 years.

- [ ] **Step 1: Write the failing tests** — `tests/test_minimum.py`

```python
import numpy as np
import pytest
from anypia_engine.dates import MonthYear
from anypia_engine.params import present_law

from pyanypia import retired_worker, special_minimum_pia
from tests.cases import Case
from tests.engine import run_retired

ENG = present_law(2)


@pytest.mark.parametrize("ym", [(1985, 6), (1999, 12), (2001, 7), (2001, 8), (2001, 12),
                                (2026, 11), (2026, 12), (2070, 3)])
def test_table_lookup_matches_engine(ym):
    yoc = np.arange(0, 36)
    pia, mfb = special_minimum_pia(yoc, *ym)
    for y, p, f in zip(yoc, pia, mfb, strict=True):
        excess = min(max(int(y) - 10, 0), 20)
        assert p == ENG.get_spec_min_pia(MonthYear(*ym), excess)
        assert f == ENG.get_spec_min_mfb(MonthYear(*ym), excess)


def test_low_earner_gets_special_minimum():
    earn = {y: 0.0 for y in range(1975, 2007)}
    for y in range(1975, 2005):
        earn[y] = 9000.0 if y < 1991 else 0.16 * float(ENG.base_77[y])
    case = Case((1944, 5, 15), earn, claim_age=62 * 12 + 1, benefit_age=62 * 12 + 1)
    r = run_retired(case)
    ours = retired_worker(earn, 1944, 5, case.claim_age)
    assert r.method == "SPEC_MIN" and ours.method == "special_minimum"
    assert (ours.pia, ours.mfb, ours.benefit) == (r.pia, r.mfb, r.monthly_benefit)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_minimum.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `src/pyanypia/minimum.py`**

```python
"""The special minimum PIA (SpecMin.cpp): a table by years of coverage over
10, carried forward by COLAs from $11.50 a year in January 1979."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_int, out
from pyanypia._years import FIRST_YEAR
from pyanypia.policy import CURRENT_LAW, Policy


def special_minimum_pia(
    years_of_coverage: ArrayLike, benefit_year: ArrayLike, benefit_month: ArrayLike = 12, *,
    policy: Policy = CURRENT_LAW,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """(PIA, family maximum) under the special minimum for a benefit month."""
    yoc, by, bm = np.broadcast_arrays(as_int("years_of_coverage", years_of_coverage),
                                      as_int("benefit_year", benefit_year),
                                      as_int("benefit_month", benefit_month))
    pia_t, mfb_t, pia01, mfb01 = policy.spec_min_tables
    excess = np.clip(yoc - 10, 0, 20)
    beninc = np.where(by >= 1983, 12, 6)
    before_inc = bm < beninc
    aug2001 = before_inc & (by == 2001) & (bm >= 8)
    year = np.where(before_inc, by - 1, by)
    row = np.maximum(excess - 1, 0)
    col = np.clip(year - FIRST_YEAR, 0, pia_t.shape[1] - 1)
    pia = np.where(aug2001, pia01[row], pia_t[row, col])
    mfb = np.where(aug2001, mfb01[row], mfb_t[row, col])
    has = excess > 0
    return out(np.where(has, pia, 0.0)), out(np.where(has, mfb, 0.0))
```

Replace the stub in `convenience.py`:
```python
def _special_minimum(m, first, last_year, ben_y, ben_m, policy):
    from pyanypia.minimum import special_minimum_pia

    yoc = np.asarray(earnings.years_of_coverage(m, first_year=first, last_year=last_year,
                                                policy=policy))
    pia, mfb = special_minimum_pia(yoc, ben_y, ben_m, policy=policy)
    return np.asarray(pia), np.asarray(mfb)
```
(Annotate the parameter and return types as before.) Because `special_minimum_pia` is only meaningful from 1979, benefit months before 1979 are outside scope and already rejected by `eligibility ≥ 1979`. Restore `SUPPORTED = {"WAGE_IND", "SPEC_MIN"}` in `test_diff_retired.py` if Task 7 narrowed it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_minimum.py tests/test_diff_retired.py -q && .venv/bin/pytest -m slow -q`
Expected: PASS. The `low` career kind in `cases.py` produces special-minimum winners. Confirm at least one appears by adding `assert any(...)` in a scratch run. Don't commit that check.

- [ ] **Step 5: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/minimum.py src/pyanypia/convenience.py src/pyanypia/__init__.py tests/test_minimum.py tests/test_diff_retired.py
git commit -m "feat: special minimum PIA, selected against the wage-indexed PIA

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Disability — DI family maximum, child-care dropout, `disabled_worker`

**Files:**
- Create: `src/pyanypia/disability.py`, `tests/test_diff_disabled.py`
- Modify: `src/pyanypia/convenience.py`, `src/pyanypia/__init__.py`, `tests/cases.py`, `tests/engine.py`

**Interfaces:**
- Consumes: `earnings._indexed`, `select_top`, `sum_by_year`, `elapsed_years`, `computation_years`, plus `formula.*`
- Produces:
  - `di_family_max(pia_elig, aime, elig_year, *, policy)` — at eligibility: `min(1.5×PIA, max(PIA, 0.85×AIME))`, each rounded
  - `childcare_aime(earnings, elig_year, comp_years, ordinary_dropout, childcare, *, first_year=None, last_year=None, policy) -> aime`
  - `disabled_worker(earnings, birth_year, birth_month, onset_year, onset_month, *, first_year=None, birth_day=15, onset_day=15, entitlement=None, benefit=None, childcare=None, policy) -> Benefit`. Here `entitlement`/`benefit` are `(year, month)` pairs of arrays, defaulting to onset + 5 months and the entitlement month.
  - Test-side: `disabled_cases(rng, n)`, `run_disabled(case)`

Rules (from `freeze_years_cal`, `n_cal`, `apply_di_max`, `ChildCareCalc`):
- **Eligibility:** `elig = min(adjusted birth year + 62, onset_year)`.
- **Computation years:** `computation_years(..., disabled=True)`.
- **Earnings window:** earnings count through `last_year = min(benefit_year - 1, onset_year if not (onset is 1 January) else onset_year - 1)`. Freeze years start the year after onset.
- **DI maximum:** applies when entitlement ≥ July 1980. `mfb_ent = max(apply_colas(di_family_max(pia_elig, aime)), pia_ent)`, and a special-minimum winner takes the wage-indexed DI maximum as its MFB (`apply_di_max`).
- **Benefit factor:** 1.0 (no prior retirement benefit).
- **Child-care dropout:** applies when entitlement ≥ July 1980 and any child-care year is given. `drop_max = min(3 - ordinary_dropout, comp_years - 2)` if `ordinary_dropout < 3`, else 0.
  - Among the selected top years, child-care years with capped earnings ≤ $0.01 are dropped in year order, up to `drop_max`.
  - If the limit isn't reached, swap: selected empty non-child-care years are deselected and unselected empty child-care years are dropped, pairwise in year order, up to the limit.
  - AIME = `floor(sum of remaining selected / ((comp_years - drops) × 12))`.
  - The child-care PIA wins only if strictly higher; its MFB uses its own AIME.

- [ ] **Step 1: Add DI cases and the engine runner**

Append to `tests/cases.py`:
```python
def disabled_cases(rng: np.random.Generator, n: int, childcare: bool = False) -> list[Case]:
    cases = []
    for _ in range(n):
        by, bm = int(rng.integers(1950, 2000)), int(rng.integers(1, 13))
        onset_age = int(rng.integers(24, 61))
        oy = by + onset_age
        if oy > 2060 or oy < 1985:
            continue
        om, od = int(rng.integers(1, 13)), int(rng.choice([5, 15, 28]))
        ent_idx = oy * 12 + om - 1 + 5
        ben_idx = ent_idx + int(rng.choice([0, 0, 12]))
        earn = career(rng, by, oy)
        extra: dict[str, object] = {"onset": (oy, om, od), "ent": divmod(ent_idx, 12),
                                    "ben": divmod(ben_idx, 12)}
        if childcare:
            yrs = [y for y in earn if rng.random() < 0.3]
            for y in yrs:
                earn[y] = 0.0
            extra["childcare"] = frozenset(yrs)
        cases.append(Case((by, bm, 15), earn, extra=extra))
    return cases
```

Append to `tests/engine.py`:
```python
def _my(pair: tuple[int, int]) -> eng.MonthYear:
    y, m0 = pair
    return eng.MonthYear(y, m0 + 1)


def run_disabled(case: Case, alt: int = 2) -> eng.Results:
    ent, ben = _my(case.extra["ent"]), _my(case.extra["ben"])  # type: ignore[arg-type]
    oy, om, od = case.extra["onset"]  # type: ignore[misc]
    lump = qc_lumps(case.earnings)
    w = eng.Worker(
        dob=date(*case.birth), sex=eng.Sex.MALE, benefit_type=eng.BenefitType.DISABILITY,
        earnings=case.earnings, entitlement=ent, benefit_date=ben,
        disability_periods=(eng.DisabilityPeriod(
            onset=date(oy, om, od), first_entitlement=ent,
            waiting_period_start=eng.MonthYear(oy, om) if od == 1 else
            eng.MonthYear(oy, om).add_months(1)),),
        childcare_years=case.extra.get("childcare", frozenset()),  # type: ignore[arg-type]
        qc_total_to_date=lump, qc_total_51_to_date=lump,
    )
    return eng.compute(w, params=present_law(alt))
```

- [ ] **Step 2: Write the failing differential test** — `tests/test_diff_disabled.py`

```python
import numpy as np
import pytest

from pyanypia import Policy, disabled_worker
from tests.cases import disabled_cases
from tests.engine import run_disabled

SUPPORTED = {"WAGE_IND", "SPEC_MIN", "CHILD_CARE"}


def _run(cases, alt):
    first = min(min(c.earnings) for c in cases)
    last = max(max(c.earnings) for c in cases)
    m = np.zeros((len(cases), last - first + 1))
    cc = np.zeros_like(m, dtype=bool)
    for i, c in enumerate(cases):
        for y, v in c.earnings.items():
            m[i, y - first] = v
        for y in c.extra.get("childcare", ()):
            cc[i, y - first] = True
    col = lambda f: np.array([f(c) for c in cases])  # noqa: E731
    ours = disabled_worker(
        m, col(lambda c: c.birth[0]), col(lambda c: c.birth[1]),
        col(lambda c: c.extra["onset"][0]), col(lambda c: c.extra["onset"][1]),
        first_year=first, onset_day=col(lambda c: c.extra["onset"][2]),
        entitlement=(col(lambda c: c.extra["ent"][0]), col(lambda c: c.extra["ent"][1] + 1)),
        benefit=(col(lambda c: c.extra["ben"][0]), col(lambda c: c.extra["ben"][1] + 1)),
        childcare=cc if cc.any() else None, policy=Policy.current_law(alt))
    bad, excluded = [], 0
    for i, c in enumerate(cases):
        r = run_disabled(c, alt)
        if r.method not in SUPPORTED:
            excluded += 1
            continue
        got = (ours.pia[i], ours.mfb[i], ours.benefit[i])
        want = (r.pia, r.mfb, r.monthly_benefit)
        if got != want:
            bad.append((i, c, got, want))
    assert not bad, f"{len(bad)} mismatches; first: {bad[:2]}"
    assert excluded <= 0.05 * len(cases)


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_disabled_vs_engine(alt):
    _run(disabled_cases(np.random.default_rng(200 + alt), 400), alt)


def test_childcare_vs_engine():
    _run(disabled_cases(np.random.default_rng(9), 400, childcare=True), 2)


@pytest.mark.slow
def test_disabled_vs_engine_large():
    _run(disabled_cases(np.random.default_rng(11), 5000), 2)


def test_disabled_vectorized_equals_scalar():
    cases = disabled_cases(np.random.default_rng(12), 40)
    first = min(min(c.earnings) for c in cases)
    last = max(max(c.earnings) for c in cases)
    m = np.zeros((len(cases), last - first + 1))
    for i, c in enumerate(cases):
        for y, v in c.earnings.items():
            m[i, y - first] = v
    by = np.array([c.birth[0] for c in cases])
    oy = np.array([c.extra["onset"][0] for c in cases])
    om = np.array([c.extra["onset"][1] for c in cases])
    whole = disabled_worker(m, by, 3, oy, om, first_year=first)
    for i in range(len(cases)):
        one = disabled_worker(m[i], int(by[i]), 3, int(oy[i]), int(om[i]), first_year=first)
        assert (one.pia, one.mfb, one.benefit) == (whole.pia[i], whole.mfb[i], whole.benefit[i])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_diff_disabled.py -q`
Expected: FAIL with `ImportError: cannot import name 'disabled_worker'`.

- [ ] **Step 4: Implement `src/pyanypia/disability.py`**

```python
"""Disability-specific pieces: the 1980-amendments family maximum and the
child-care dropout years (PiaMethod::diMax, ChildCareCalc)."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_earnings, as_float, as_int, out
from pyanypia.earnings import _indexed, _window, select_top
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import round_benefit


def di_family_max(
    pia_elig: ArrayLike, aime: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> float | np.ndarray:
    """85% of AIME, but not less than the PIA nor more than 150% of it, at eligibility."""
    p, a, e = np.broadcast_arrays(as_float("pia_elig", pia_elig), as_float("aime", aime),
                                  as_int("elig_year", elig_year))
    year = e - 1
    mfb85 = round_benefit(0.85 * a, year)
    mfb150 = round_benefit(1.5 * p, year)
    return out(np.where(mfb85 > mfb150, mfb150, np.where(mfb85 < p, p, mfb85)))  # type: ignore[no-any-return]


def childcare_aime(
    earnings: object, elig_year: ArrayLike, comp_years: ArrayLike, ordinary_dropout: ArrayLike,
    childcare: ArrayLike, *, first_year: int | None = None, last_year: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> float | np.ndarray:
    """AIME with up to three total dropout years, the extra ones being years
    with a child in care and no earnings (ChildCareCalc::childCareDropoutCal)."""
    m, first, single = as_earnings(earnings, first_year)  # type: ignore[arg-type]
    rows = m.shape[0]
    elig = np.broadcast_to(as_int("elig_year", elig_year), (rows,))
    n = np.broadcast_to(as_int("comp_years", comp_years), (rows,))
    drop0 = np.broadcast_to(as_int("ordinary_dropout", ordinary_dropout), (rows,))
    cc = np.broadcast_to(np.asarray(childcare, dtype=bool).reshape(-1, m.shape[1]), m.shape)
    last = None if last_year is None else np.broadcast_to(as_int("last_year", last_year), (rows,))
    window = _window(m, first, last)
    x = _indexed(window, first, elig, policy)
    capped = np.minimum(window, policy.taxmax[np.arange(first, first + m.shape[1]) - 1937])
    sel = select_top(x, n).astype(np.int8)  # 1 selected, 0 not, -1 dropped
    years = np.arange(first, first + m.shape[1])
    upper = np.full(rows, years[-1]) if last is None else last
    in_range = (years[None, :] >= max(first, 1951)) & (years[None, :] <= upper[:, None])
    empty = (capped <= 0.01) & in_range
    drop_max = np.where(drop0 < 3, np.minimum(3 - drop0, n - 2), 0)
    drops = np.zeros(rows, dtype=np.int64)
    for i in np.flatnonzero(drop_max > 0):
        row = sel[i]
        for j in np.flatnonzero((row == 1) & cc[i] & empty[i]):
            if drops[i] >= drop_max[i]:
                break
            row[j] = -1
            drops[i] += 1
        if drops[i] < drop_max[i]:
            out1 = np.flatnonzero((row == 1) & ~cc[i] & empty[i])
            in2 = np.flatnonzero((row == 0) & cc[i] & empty[i])
            for k in range(min(len(out1), len(in2), int(drop_max[i] - drops[i]))):
                row[out1[k]] = 0
                row[in2[k]] = -1
                drops[i] += 1
    total = np.zeros(rows)
    for j in range(m.shape[1]):
        total = total + np.where(sel[:, j] == 1, x[:, j], 0.0)
    result = np.floor(total / ((n - drops).astype(float) * 12.0))
    return out(result[0] if single else result)  # type: ignore[no-any-return]
```

`ChildCareCalc` checks the first loop's `drop >= drop_max` *after* each increment. The `break` placement above, before marking, gives the same count. Keep it exactly as written.

Add `disabled_worker` to `convenience.py`:
```python
def disabled_worker(
    earnings_: Any, birth_year: ArrayLike, birth_month: ArrayLike, onset_year: ArrayLike,
    onset_month: ArrayLike, *, first_year: int | None = None, birth_day: ArrayLike = 15,
    onset_day: ArrayLike = 15, entitlement: tuple[ArrayLike, ArrayLike] | None = None,
    benefit: tuple[ArrayLike, ArrayLike] | None = None, childcare: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> Benefit:
    """A disabled worker's benefit. `entitlement` and `benefit` are (year, month);
    entitlement defaults to five months after onset, benefit to entitlement."""
    from pyanypia import disability, minimum
    from pyanypia._arrays import check
    from pyanypia.dates import cola_year
    from pyanypia.rounding import floor_dollar

    m, first, single = as_earnings(earnings_, first_year)
    shape = (m.shape[0],)
    b = lambda k, v: np.broadcast_to(as_int(k, v), shape)  # noqa: E731
    by, bm, bd = b("birth_year", birth_year), b("birth_month", birth_month), b("birth_day", birth_day)
    oy, om, od = b("onset_year", onset_year), b("onset_month", onset_month), b("onset_day", onset_day)
    if entitlement is None:
        ey, em = from_month_index(month_index(oy, om) + 5)
    else:
        ey, em = b("entitlement_year", entitlement[0]), b("entitlement_month", entitlement[1])
    ben_y, ben_m = (ey, em) if benefit is None else (b("benefit_year", benefit[0]),
                                                     b("benefit_month", benefit[1]))
    check("entitlement", month_index(ey, em) < month_index(1980, 7), "before July 1980")
    ky, km = adjusted_birth(by, bm, bd)
    elig = np.minimum(ky + 62, oy)
    jan1 = (om == 1) & (od == 1)
    last_year = np.minimum(ben_y - 1, np.where(jan1, oy - 1, oy))
    elapsed = earnings.elapsed_years(by, bm, elig, birth_day=bd)
    comp = np.asarray(earnings.computation_years(by, bm, elig, birth_day=bd, disabled=True))
    aime = np.asarray(earnings.aime(m, elig, comp, first_year=first, last_year=last_year,
                                    policy=policy))
    pia_elig = np.asarray(formula.pia(aime, elig, policy=policy))
    if childcare is not None:
        cc_aime = np.asarray(disability.childcare_aime(
            m, elig, comp, elapsed - comp, childcare, first_year=first, last_year=last_year,
            policy=policy))
        cc_pia = np.asarray(formula.pia(cc_aime, elig, policy=policy))
        use_cc = cc_pia > pia_elig
        aime = np.where(use_cc, cc_aime, aime)
        pia_elig = np.where(use_cc, cc_pia, pia_elig)
    mfb_elig = np.asarray(disability.di_family_max(pia_elig, aime, elig, policy=policy))
    wage_pia = np.asarray(formula.apply_colas(pia_elig, elig, ben_y, ben_m, policy=policy))
    wage_mfb = np.maximum(np.asarray(formula.apply_colas(mfb_elig, elig, ben_y, ben_m,
                                                         policy=policy)), wage_pia)
    yoc = np.asarray(earnings.years_of_coverage(m, first_year=first, last_year=last_year,
                                                policy=policy))
    sm_pia, _ = minimum.special_minimum_pia(yoc, ben_y, ben_m, policy=policy)
    sm_pia = np.asarray(sm_pia)
    sm_wins = sm_pia > wage_pia
    pia = np.where(sm_wins, sm_pia, wage_pia)
    mfb = np.where(sm_wins, np.maximum(wage_mfb, sm_pia), wage_mfb)
    from pyanypia.rounding import round_benefit

    unrounded = round_benefit(1.0 * pia, cola_year(ben_y, ben_m))
    nra = np.asarray(claiming.normal_retirement_age(by, bm, birth_day=bd, policy=policy))
    return Benefit(**_scalarize(
        single, elig_year=elig, aime=aime, pia_elig=pia_elig, pia=pia, mfb=mfb, nra=nra,
        factor=np.ones(shape), benefit=floor_dollar(unrounded),
        method=np.where(sm_wins, "special_minimum", "wage_indexed"),
        insured=np.ones(shape, dtype=bool)))
```

Note: `insured` here is not computed. Disability insured status (20/40) is outside the spec's scope, and the docstring must say "`insured` is not evaluated for disabled workers (always True)". For the special-minimum-wins MFB: `apply_di_max` gives `high_max` (the wage-indexed DI maximum), and `set_high_mfb` takes it, so it is `wage_mfb`. Simplify the `np.maximum(wage_mfb, sm_pia)` to `wage_mfb` if the differential sweep says so. Exactness comes from the engine, not this note.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_diff_disabled.py -q && .venv/bin/pytest -m slow tests/test_diff_disabled.py -q`
Expected: PASS. For child-care mismatches, print the engine's `MethodResult` for `CHILD_CARE` (`r.methods["CHILD_CARE"].aime`) beside `childcare_aime`'s output.

- [ ] **Step 6: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/disability.py src/pyanypia/convenience.py src/pyanypia/__init__.py tests/cases.py tests/engine.py tests/test_diff_disabled.py
git commit -m "feat: disabled_worker with the DI family maximum and child-care dropout years

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Family and survivor benefits

**Files:**
- Create: `src/pyanypia/family.py`, `tests/test_diff_family.py`
- Modify: `src/pyanypia/convenience.py` (adds `deceased_worker`), `src/pyanypia/__init__.py`, `tests/cases.py`, `tests/engine.py`

**Interfaces:**
- Consumes: `formula`, `earnings`, `claiming.spouse_reduction_factor`, `Policy.nra`
- Produces:
  - `Auxiliary`: a frozen dataclass with `kind`, `birth_year`, `birth_month`, `claim_age=0`, `birth_day=15`, `present=True`, where every field except `kind` is array-like. `kind` is one of:
    - life: `"spouse"`, `"spouse_with_child"`, `"child"`
    - survivor: `"child"`, `"widow"`, `"disabled_widow"`, `"parent_with_child"`
  - `FamilyBenefits`: a frozen dataclass with `full`, `after_max`, `reduction_factor` and `benefit`, each shaped `(k, n)`
  - `family_benefits(worker_pia, worker_mfb, auxiliaries, *, benefit_year, benefit_month=12, survivor=False, policy) -> FamilyBenefits`
  - `deceased_worker(earnings, birth_year, birth_month, death_year, death_month, *, first_year=None, birth_day=15, benefit=(year, month), policy) -> Benefit`, giving the deceased's PIA and MFB at the benefit month. `factor=1`, `benefit=0`.

Rules (from `ardri_aux_cal`, `pia_cal3`):
- **Benefit rates** (share of the worker's PIA):
  - life: spouse 0.5, spouse_with_child 0.5, child 0.5
  - survivor: child 0.75, parent_with_child 0.75, widow 1.0, disabled_widow 1.0
- **Reductions:**
  - spouse: `spouse_reduction_factor(max(spouse_nra - claim_age, 0))`, where `spouse_nra` is the NRA for the spouse's own birth. The claim must be no earlier than `earliest_claim_age`.
  - widow: `1 - (months / (nra60 - 720)) * 0.285`, with `nra60 = policy.nra[adjusted_birth_year + 60]` and `months = max(nra60 - claim_age, 0)`. The claim must be at least 720.
  - disabled_widow: 0.715. The claim must be between 600 and 719 months.
  - others: none.
- **Steps:**
  1. full = `round_benefit(pia * rate, cy)`
  2. total = sequential sum over present auxiliaries
  3. ratio = `(mfb - pia)/total` (life) or `mfb/total` (survivor), clipped to [0, 1], and 1 if the total is 0
  4. after_max = `round_benefit(ratio * full, cy)`
  5. reduced = `round_benefit(arf * after_max, cy)` for reducible kinds
  6. benefit = `floor(reduced)`

Divorced spouses (outside the maximum) and the re-indexed widow(er) guarantee are out of scope; the docstring lists both. Survivor PIA:
- `elig = min(adjusted birth year + 62, death_year)`
- `comp = computation_years(..., death_year=death_year)`
- earnings count through the death year (`last_year = death_year`)
- COLAs from eligibility to the benefit month
- MFB from `family_max`

- [ ] **Step 1: Add family cases and the engine runners**

Append to `tests/cases.py`:
```python
LIFE_CONFIGS = ("spouse", "young_family", "kids")
SURVIVOR_CONFIGS = ("widow", "disabled_widow", "young_family", "child")


def life_family_cases(rng: np.random.Generator, n: int) -> list[Case]:
    cases = []
    for _ in range(n):
        by = int(rng.integers(1945, 1995))
        claim = int(rng.integers(745, 841))
        base = retired_cases(rng, 1)[0]
        base.birth, base.claim_age, base.benefit_age = (by, 3, 15), claim, claim
        ent_y = (12 * by + 2 + claim) // 12
        base.earnings = career(rng, by, ent_y - 1)
        cfg = str(rng.choice(LIFE_CONFIGS))
        sby = by + int(rng.integers(-4, 5))
        members = []
        if cfg == "spouse":
            s_ent = max(12 * sby + 6 + int(rng.integers(745, 805)), 12 * by + 2 + claim)
            members.append(("B ", (sby, 7, 20), s_ent))
        else:
            cby = ent_y - int(rng.integers(3, 15))
            if cfg == "young_family":
                members.append(("B2", (by + 15, 1, 15), 12 * by + 2 + claim))
            members.append(("C1", (cby, 4, 10), 12 * by + 2 + claim))
            members.append(("C2", (cby + 2, 9, 9), 12 * by + 2 + claim))
        latest = max([12 * by + 2 + claim] + [e for _, _, e in members])
        base.benefit_age = latest - (12 * by + 2)
        base.extra = {"family": members, "config": cfg}
        cases.append(base)
    return cases


def survivor_cases(rng: np.random.Generator, n: int) -> list[Case]:
    cases = []
    for _ in range(n):
        by = int(rng.integers(1945, 1995))
        dy = by + int(rng.integers(30, 75))
        if not 1986 <= dy <= 2070:
            continue
        death = (dy, int(rng.integers(1, 13)), 20)
        death_idx = 12 * dy + death[1] - 1
        cfg = str(rng.choice(SURVIVOR_CONFIGS))
        wby = by + int(rng.integers(-3, 6))
        members = []
        if cfg == "widow":
            members.append(("D ", (wby, 6, 10),
                            max(12 * wby + 5 + int(rng.integers(720, 820)), death_idx)))
        elif cfg == "disabled_widow":
            ent = max(12 * wby + 5 + int(rng.integers(600, 715)), death_idx)
            members.append(("W ", (wby, 6, 10), ent))
        else:
            cby = dy - int(rng.integers(2, 15))
            if cfg == "young_family":
                members.append(("E ", (by + 3, 2, 25), death_idx))
            members.append(("C1", (cby, 4, 10), death_idx))
        latest = max(e for _, _, e in members) + int(rng.choice([0, 12]))
        if latest // 12 > 2105:
            continue
        cases.append(Case((by, 3, 15), career(rng, by, dy),
                          extra={"family": members, "death": death, "ben": divmod(latest, 12),
                                 "config": cfg}))
    return cases
```

Append to `tests/engine.py`:
```python
def _family(case: Case) -> tuple[eng.FamilyMember, ...]:
    out = []
    for bic, dob, ent_idx in case.extra["family"]:  # type: ignore[attr-defined]
        y, m0 = divmod(ent_idx, 12)
        onset = None
        if bic.strip() == "W":
            onset = date(y - 1, m0 + 1, 5)
        out.append(eng.FamilyMember(bic=bic, dob=date(*dob), entitlement=eng.MonthYear(y, m0 + 1),
                                    disability_onset=onset))
    return tuple(out)


def run_life_family(case: Case, alt: int = 2) -> eng.Results:
    return run_retired(case, alt, family=_family(case))


def run_survivor(case: Case, alt: int = 2) -> eng.Results:
    lump = qc_lumps(case.earnings)
    w = eng.Worker(
        dob=date(*case.birth), sex=eng.Sex.MALE, benefit_type=eng.BenefitType.SURVIVOR,
        earnings=case.earnings, death_date=date(*case.extra["death"]),  # type: ignore[misc]
        benefit_date=_my(case.extra["ben"]),  # type: ignore[arg-type]
        family=_family(case), qc_total_to_date=lump, qc_total_51_to_date=lump,
    )
    return eng.compute(w, params=present_law(alt))
```

- [ ] **Step 2: Write the failing differential test** — `tests/test_diff_family.py`

```python
import numpy as np
import pytest

from pyanypia import Auxiliary, deceased_worker, family_benefits, retired_worker
from tests.cases import life_family_cases, survivor_cases
from tests.engine import run_life_family, run_survivor

KIND = {"B": "spouse", "B2": "spouse_with_child", "C1": "child", "C2": "child",
        "D": "widow", "W": "disabled_widow", "E": "parent_with_child"}


def _aux(case, kb_index):
    out = []
    for bic, (y, m, d), ent_idx in case.extra["family"]:
        ky, km = (y, m) if d != 1 else (y - (m == 1), (m - 2) % 12 + 1)
        out.append(Auxiliary(KIND[bic.strip()], y, m, birth_day=d,
                             claim_age=ent_idx - (12 * ky + km - 1)))
    return out


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_life_families_vs_engine(seed):
    bad = []
    for c in life_family_cases(np.random.default_rng(seed), 150):
        r = run_life_family(c)
        if r.method not in {"WAGE_IND", "SPEC_MIN"}:
            continue
        w = retired_worker(c.earnings, c.birth[0], c.birth[1], c.claim_age,
                           benefit_age=c.benefit_age)
        by, bm = divmod(12 * c.birth[0] + 2 + c.benefit_age, 12)
        fam = family_benefits(w.pia, w.mfb, _aux(c, None), benefit_year=by, benefit_month=bm + 1)
        got = [float(x) for x in np.ravel(fam.benefit)]
        want = [f.rounded_benefit for f in r.family]
        if got != want:
            bad.append((c, got, want))
    assert not bad, bad[:2]


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_survivors_vs_engine(seed):
    bad, excluded, total = [], 0, 0
    for c in survivor_cases(np.random.default_rng(seed), 200):
        total += 1
        r = run_survivor(c)
        if r.method not in {"WAGE_IND", "SPEC_MIN"} or any(f.pifc == "W" for f in r.family):
            excluded += 1
            continue
        dy, dm, dd = c.extra["death"]
        by, bm0 = c.extra["ben"]
        d = deceased_worker(c.earnings, c.birth[0], c.birth[1], dy, dm, birth_day=c.birth[2],
                            benefit=(by, bm0 + 1))
        assert (d.pia, d.mfb) == (r.pia, r.mfb), c
        fam = family_benefits(d.pia, d.mfb, _aux(c, None), benefit_year=by,
                              benefit_month=bm0 + 1, survivor=True)
        got = [float(x) for x in np.ravel(fam.benefit)]
        want = [f.rounded_benefit for f in r.family]
        if got != want:
            bad.append((c, got, want))
    assert not bad, bad[:2]
    assert excluded <= 0.25 * total  # re-indexed widow guarantee is out of scope
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_diff_family.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 4: Implement `src/pyanypia/family.py`**

```python
"""Benefits for spouses, children and survivors, and the family maximum
(PiaCal::ardriAuxCal, applyMfb, piaCal3).

Not covered: divorced spouses (outside the maximum) and the re-indexed
widow(er)'s guarantee for deaths before 62.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, check
from pyanypia._years import at
from pyanypia.claiming import earliest_claim_age, spouse_reduction_factor
from pyanypia.dates import adjusted_birth, cola_year
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit

LIFE_RATES = {"spouse": 0.5, "spouse_with_child": 0.5, "child": 0.5}
SURVIVOR_RATES = {"child": 0.75, "parent_with_child": 0.75, "widow": 1.0, "disabled_widow": 1.0}
REDUCIBLE = {"spouse", "widow", "disabled_widow"}


@dataclass(frozen=True)
class Auxiliary:
    kind: str
    birth_year: ArrayLike
    birth_month: ArrayLike
    claim_age: ArrayLike = 0   # months from adjusted birth to entitlement
    birth_day: ArrayLike = 15
    present: ArrayLike = True


@dataclass(frozen=True)
class FamilyBenefits:
    full: Any              # (k, n) rate x PIA, before the family maximum
    after_max: Any         # (k, n) after the family maximum
    reduction_factor: Any  # (k, n) age reduction (1.0 when none)
    benefit: Any           # (k, n) payable, whole dollars


def _reduction(aux: Auxiliary, shape: tuple[int, ...], policy: Policy) -> np.ndarray:
    claim = np.broadcast_to(as_int("claim_age", aux.claim_age), shape)
    present = np.broadcast_to(np.asarray(aux.present, dtype=bool), shape)
    if aux.kind == "spouse":
        ky, _ = adjusted_birth(aux.birth_year, aux.birth_month, aux.birth_day)
        check("claim_age", present & (claim < np.asarray(earliest_claim_age(aux.birth_day))),
              "spouse claims before the earliest retirement age")
        nra = at(policy.nra, np.broadcast_to(ky + 62, shape), "nra").astype(np.int64)
        return spouse_reduction_factor(np.maximum(nra - claim, 0), policy=policy)
    if aux.kind == "widow":
        ky, _ = adjusted_birth(aux.birth_year, aux.birth_month, aux.birth_day)
        check("claim_age", present & (claim < 720), "widow(er) claims before 60")
        nra = at(policy.nra, np.broadcast_to(ky + 60, shape), "nra").astype(np.int64)
        months = np.maximum(nra - claim, 0)
        return np.asarray(1.0 - (months.astype(float) / (nra - 720).astype(float)) * 0.285)
    if aux.kind == "disabled_widow":
        check("claim_age", present & ((claim < 600) | (claim >= 720)),
              "disabled widow(er) claims outside ages 50-59")
        return np.full(shape, 0.715)
    return np.ones(shape)


def family_benefits(
    worker_pia: ArrayLike, worker_mfb: ArrayLike, auxiliaries: Sequence[Auxiliary], *,
    benefit_year: ArrayLike, benefit_month: ArrayLike = 12, survivor: bool = False,
    policy: Policy = CURRENT_LAW,
) -> FamilyBenefits:
    rates = SURVIVOR_RATES if survivor else LIFE_RATES
    pia, mfb, by, bm = np.broadcast_arrays(as_float("worker_pia", worker_pia),
                                           as_float("worker_mfb", worker_mfb),
                                           as_int("benefit_year", benefit_year),
                                           as_int("benefit_month", benefit_month))
    shape = pia.shape
    cy = cola_year(by, bm)
    fulls, arfs = [], []
    for aux in auxiliaries:
        if aux.kind not in rates:
            raise ValueError(f"kind: {aux.kind!r} is not a "
                             f"{'survivor' if survivor else 'life'} beneficiary; "
                             f"expected one of {sorted(rates)}")
        present = np.broadcast_to(np.asarray(aux.present, dtype=bool), shape)
        fulls.append(np.where(present, round_benefit(pia * rates[aux.kind], cy), 0.0))
        arfs.append(_reduction(aux, shape, policy))
    total = np.zeros(shape)
    for f in fulls:
        total = total + f
    avail = mfb if survivor else mfb - pia
    ratio = np.divide(avail, total, out=np.ones(shape), where=total > 0.0)
    ratio = np.clip(ratio, 0.0, 1.0)
    after, paid = [], []
    for aux, f, arf in zip(auxiliaries, fulls, arfs, strict=True):
        a = round_benefit(ratio * f, cy)
        reduced = round_benefit(arf * a, cy) if aux.kind in REDUCIBLE else a
        after.append(a)
        paid.append(floor_dollar(reduced))
    return FamilyBenefits(full=np.array(fulls), after_max=np.array(after),
                          reduction_factor=np.array(arfs), benefit=np.array(paid))
```

Add `deceased_worker` to `convenience.py`:
```python
def deceased_worker(
    earnings_: Any, birth_year: ArrayLike, birth_month: ArrayLike, death_year: ArrayLike,
    death_month: ArrayLike, *, benefit: tuple[ArrayLike, ArrayLike],
    first_year: int | None = None, birth_day: ArrayLike = 15, policy: Policy = CURRENT_LAW,
) -> Benefit:
    """A deceased worker's PIA and family maximum at a survivor benefit month,
    for use with `family_benefits(..., survivor=True)`."""
    from pyanypia import minimum

    m, first, single = as_earnings(earnings_, first_year)
    shape = (m.shape[0],)
    b = lambda k, v: np.broadcast_to(as_int(k, v), shape)  # noqa: E731
    by, bm, bd = b("birth_year", birth_year), b("birth_month", birth_month), b("birth_day", birth_day)
    dy = b("death_year", death_year)
    ben_y, ben_m = b("benefit_year", benefit[0]), b("benefit_month", benefit[1])
    ky, _ = adjusted_birth(by, bm, bd)
    elig = np.minimum(ky + 62, dy)
    comp = np.asarray(earnings.computation_years(by, bm, elig, birth_day=bd, death_year=dy))
    aime = np.asarray(earnings.aime(m, elig, comp, first_year=first, last_year=dy, policy=policy))
    pia_elig = np.asarray(formula.pia(aime, elig, policy=policy))
    mfb_elig = np.asarray(formula.family_max(pia_elig, elig, policy=policy))
    wage_pia = np.asarray(formula.apply_colas(pia_elig, elig, ben_y, ben_m, policy=policy))
    wage_mfb = np.asarray(formula.apply_colas(mfb_elig, elig, ben_y, ben_m, policy=policy))
    yoc = np.asarray(earnings.years_of_coverage(m, first_year=first, last_year=dy, policy=policy))
    sm_pia, sm_mfb = (np.asarray(v) for v in minimum.special_minimum_pia(yoc, ben_y, ben_m,
                                                                         policy=policy))
    sm_wins = sm_pia > wage_pia
    nra = np.asarray(claiming.normal_retirement_age(by, bm, birth_day=bd, policy=policy))
    return Benefit(**_scalarize(
        single, elig_year=elig, aime=aime, pia_elig=pia_elig,
        pia=np.where(sm_wins, sm_pia, wage_pia), mfb=np.where(sm_wins, sm_mfb, wage_mfb),
        nra=nra, factor=np.ones(shape), benefit=np.zeros(shape),
        method=np.where(sm_wins, "special_minimum", "wage_indexed"),
        insured=np.ones(shape, dtype=bool)))
```

Export `Auxiliary`, `FamilyBenefits`, `family_benefits` and `deceased_worker`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_diff_family.py -q`
Expected: PASS. A disabled widow's onset in `tests/engine.py` is fixed at one year before entitlement, which keeps it valid for the engine. If the engine rejects a generated case (`PiaError`), fix the generator rather than skipping it.

- [ ] **Step 6: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/family.py src/pyanypia/convenience.py src/pyanypia/__init__.py tests/cases.py tests/engine.py tests/test_diff_family.py
git commit -m "feat: spouse, child and survivor benefits under the family maximum

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: WEP and GPO (optional, off by default)

**Files:**
- Create: `src/pyanypia/wep.py`, `tests/test_wep.py`
- Modify: `src/pyanypia/convenience.py` (`_apply_wep`), `src/pyanypia/__init__.py`

**Interfaces:**
- Consumes: `formula.pia(..., pct=...)`, `earnings.years_of_coverage(kind="wep")`, `rounding.round_benefit`
- Produces:
  - `wep_pia(aime, elig_year, years_of_coverage, pension, *, benefit_year, policy) -> pia_elig`. Its result is never above the regular PIA.
  - `gpo_offset(benefit, pension, *, policy) -> dollars`. This is the auxiliary benefit less `gpo_fraction × pension`, floored at 0 and paid in whole dollars.
  - `retired_worker(..., noncovered_pension=...)` applies `wep_pia` only when `policy.wep_enabled`

Rules (from `windfall_perc`, `windfall_cal`, `wep_app`):
- The WEP applies when `elig_year > 1985`, `pension > 0` and fewer than 30 years of coverage. Coverage uses the `yoc_wep` series, through `last_year`.
- **First percentage:** `p0 - 0.5` if `elig > 1989`, else `p0 - 0.10*(elig-1985)`. Raise it to `p0 - annual*(30-yoc)` if that's higher, where `annual` is 0.05 from benefit year 1989 and 0.10 before. Floor it at 0.
- **WEP PIA:** `test = pia(aime, elig, pct=(p0', p1, p2))` and `cap = regular - round_benefit(0.5*pension, elig-1)`. The WEP PIA is `test` if `test > cap`, else `cap`.
- **Policy switch:** with `policy.wep_enabled` the WEP applies regardless of benefit date (counterfactual). AnyPIA itself applies it only to benefits before January 2024.

- [ ] **Step 1: Write the failing tests** — `tests/test_wep.py`

```python
import numpy as np
from anypia_engine.engine.methods.wage_indexed import windfall_perc

from pyanypia import CURRENT_LAW, gpo_offset, retired_worker, wep_pia
from tests.cases import retired_cases
from tests.engine import run_retired

WEP = CURRENT_LAW.replace(wep_enabled=True)


def test_windfall_percentages_match_engine():
    for elig in range(1986, 2030):
        for yoc in range(0, 32):
            want = windfall_perc(elig, elig + 1, yoc)
            got_pia = wep_pia(3000.0, elig, yoc, 1000.0, benefit_year=elig + 1)
            assert got_pia <= wep_pia(3000.0, elig, 30, 1000.0, benefit_year=elig + 1)
            assert want[0] >= 0.0


def test_retired_with_pension_vs_engine():
    rng = np.random.default_rng(42)
    bad, n = [], 0
    for c in retired_cases(rng, 600):
        ky = c.birth[0]
        ent_y = (12 * ky + c.birth[1] - 1 + c.benefit_age) // 12
        if ent_y >= 2024 or ky + 62 <= 1986:
            continue
        pension = float(rng.uniform(200, 3000))
        r = run_retired(c, noncovered_pension=pension)
        if r.method not in {"WAGE_IND", "SPEC_MIN"}:
            continue
        n += 1
        ours = retired_worker(c.earnings, c.birth[0], c.birth[1], c.claim_age,
                              birth_day=c.birth[2], benefit_age=c.benefit_age,
                              noncovered_pension=pension, policy=WEP)
        if (ours.pia, ours.benefit) != (r.pia, r.monthly_benefit):
            bad.append((c, (ours.pia, ours.benefit), (r.pia, r.monthly_benefit)))
    assert n > 100 and not bad, bad[:2]


def test_wep_off_by_default():
    c = retired_cases(np.random.default_rng(1), 1)[0]
    a = retired_worker(c.earnings, c.birth[0], c.birth[1], c.claim_age, noncovered_pension=2000.0)
    b = retired_worker(c.earnings, c.birth[0], c.birth[1], c.claim_age)
    assert a.pia == b.pia


def test_gpo_offset():
    assert gpo_offset(1000.0, 900.0) == 400.0
    assert gpo_offset(np.array([500.0, 1000.0]), np.array([1500.0, 0.0])).tolist() == [0.0, 1000.0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_wep.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `src/pyanypia/wep.py`**

```python
"""Windfall elimination provision and government pension offset.

Both were repealed by the Social Security Fairness Act for benefits payable
after December 2023; they are here for historical and counterfactual work and
apply in the convenience functions only when `Policy.wep_enabled` /
`Policy.gpo_enabled` is set. The WEP follows AnyPIA (WageIndGeneral::
windfallCal); AnyPIA has no GPO, so `gpo_offset` follows the statute (42 USC
402(k)(5)) and is tested against hand arithmetic only.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, out
from pyanypia.formula import pia
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit

WINDFALL_YEARS = 30


def wep_pia(
    aime: ArrayLike, elig_year: ArrayLike, years_of_coverage: ArrayLike, pension: ArrayLike, *,
    benefit_year: ArrayLike, policy: Policy = CURRENT_LAW,
) -> float | np.ndarray:
    """PIA at eligibility after the windfall elimination provision."""
    a, e, yoc, pen, by = np.broadcast_arrays(
        as_float("aime", aime), as_int("elig_year", elig_year),
        as_int("years_of_coverage", years_of_coverage), as_float("pension", pension),
        as_int("benefit_year", benefit_year))
    p0 = policy.pia_pct[0]
    rv = np.where(e > 1989, p0 - 0.5, p0 - 0.10 * (e - 1985).astype(float))
    annual = np.where(by >= 1989, 0.05, 0.10)
    floor_pct = p0 - annual * (WINDFALL_YEARS - yoc).astype(float)
    rv = np.where(floor_pct > rv, floor_pct, rv)
    rv = np.where(rv < 0.0, 0.0, rv)
    pct = np.stack([rv] + [np.full(rv.shape, p) for p in policy.pia_pct[1:]], axis=-1)
    regular = np.asarray(pia(a, e, policy=policy))
    reduced = np.asarray(pia(a, e, policy=policy, pct=pct))
    cap = regular - round_benefit(0.5 * pen, e - 1)
    wep = np.where(reduced > cap, reduced, cap)
    applies = (e > 1985) & (pen > 0.0) & (yoc < WINDFALL_YEARS)
    return out(np.where(applies, wep, regular))  # type: ignore[no-any-return]


def gpo_offset(
    benefit: ArrayLike, pension: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> float | np.ndarray:
    """A spouse's or widow(er)'s benefit after the government pension offset."""
    b, p = np.broadcast_arrays(as_float("benefit", benefit), as_float("pension", pension))
    return out(floor_dollar(np.maximum(b - policy.gpo_fraction * p, 0.0)))  # type: ignore[no-any-return]
```

Replace `_apply_wep` in `convenience.py`:
```python
def _apply_wep(pia_elig, *, aime, elig, m, first, last_year, ben_y, pension, policy):
    pen = np.broadcast_to(np.asarray(pension, dtype=float), pia_elig.shape)
    if not policy.wep_enabled or not (pen > 0).any():
        return pia_elig
    from pyanypia.wep import wep_pia

    yoc = np.asarray(earnings.years_of_coverage(m, first_year=first, last_year=last_year,
                                                kind="wep", policy=policy))
    return np.asarray(wep_pia(aime, elig, yoc, pen, benefit_year=ben_y, policy=policy))
```

`test_windfall_percentages_match_engine` above only checks monotonicity. Strengthen it so the exact first percentage is compared: expose a private helper `_windfall_first_pct(elig, benefit_year, yoc, p0)` in `wep.py`, use it inside `wep_pia`, and assert `_windfall_first_pct(...) == windfall_perc(...)[0]` over the grid.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_wep.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, then commit**

```bash
.venv/bin/ruff check src tests && .venv/bin/mypy
git add src/pyanypia/wep.py src/pyanypia/convenience.py src/pyanypia/__init__.py tests/test_wep.py
git commit -m "feat: optional WEP (engine-validated) and GPO (statutory)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Docs, examples, release

**Files:**
- Rewrite: `README.md`, `CHANGELOG.md` (prepend 0.3.0)
- Create: `docs/examples/hypotheticals.py`, `docs/examples/microsim.py`, `tests/test_examples.py`

**Interfaces:**
- Consumes: the whole public API

- [ ] **Step 1: Write the examples**

`docs/examples/hypotheticals.py`:
```python
"""Hypothetical workers, one at a time."""

from pyanypia import CURRENT_LAW, retired_worker

# A steady $60,000 earner born June 1964, claiming at 62y1m, at FRA (67), and at 70.
earnings = {year: 60_000.0 for year in range(1986, 2026)}
for months in (62 * 12 + 1, 67 * 12, 70 * 12):
    b = retired_worker(earnings, 1964, 6, months)
    print(f"claim at {months // 12}y{months % 12}m: AIME {b.aime:,.0f}  PIA ${b.pia:,.2f}  "
          f"benefit ${b.benefit:,.0f}")

# The same worker under a lower top bracket (15% -> 10%).
reform = CURRENT_LAW.replace(pia_pct=(0.90, 0.32, 0.10))
b = retired_worker(earnings, 1964, 6, 67 * 12, policy=reform)
print(f"reform PIA ${b.pia:,.2f}")
```

`docs/examples/microsim.py`:
```python
"""100,000 synthetic workers in one vectorized call."""

import time

import numpy as np

from pyanypia import CURRENT_LAW, retired_worker

rng = np.random.default_rng(0)
n, first, last = 100_000, 1980, 2040
birth_year = rng.integers(1960, 1980, n)
level = rng.lognormal(mean=0.0, sigma=0.6, size=n)
years = np.arange(first, last + 1)
awi = CURRENT_LAW.awi[years - 1937]
earnings = level[:, None] * awi[None, :]
working = (years[None, :] >= birth_year[:, None] + 22) & (years[None, :] < birth_year[:, None] + 62)
earnings = np.where(working, earnings, 0.0)
claim_age = rng.integers(62 * 12 + 1, 70 * 12 + 1, n)

t = time.perf_counter()
b = retired_worker(earnings, birth_year, 6, claim_age, first_year=first)
print(f"{n:,} workers in {time.perf_counter() - t:.1f}s; median benefit ${np.median(b.benefit):,.0f}")
```

`tests/test_examples.py`:
```python
import runpy
import pathlib

import pytest

EX = pathlib.Path(__file__).parent.parent / "docs" / "examples"


def test_hypotheticals_runs(capsys):
    runpy.run_path(str(EX / "hypotheticals.py"))
    assert "reform PIA" in capsys.readouterr().out


@pytest.mark.slow
def test_microsim_runs(capsys):
    runpy.run_path(str(EX / "microsim.py"))
    assert "100,000 workers" in capsys.readouterr().out
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/pytest tests/test_examples.py -q -m "slow or not slow" && .venv/bin/python docs/examples/microsim.py`
Expected: PASS. Note the microsim timing for the README. If it is above roughly 30 s, profile first: `apply_colas` and `sum_by_year` loop over years, which is O(years) NumPy calls, so it should be fast.

- [ ] **Step 3: Rewrite `README.md`**

Sections, in this order. Every code block must be copied from the example files, so the tests keep it honest.
1. **H1 and one-paragraph pitch.** Benefit-formula functions, vectorized, penny-exact with AnyPIA (2026 TR).
2. **"Looking for the full calculator?"** Link `anthonycolavito/anypia-engine` and say why it moved.
3. **Install** — `pip install git+https://github.com/anthonycolavito/pyanypia`.
4. **Quickstart** — `hypotheticals.py`.
5. **Building blocks** — a table of each public function with a one-line description:
   - `eligibility_year`, `computation_years`, `aime`, `pia`, `family_max`, `di_family_max`, `apply_colas`
   - `normal_retirement_age`, `benefit_factor`, `monthly_benefit`
   - `special_minimum_pia`, `family_benefits`, `wep_pia`, `gpo_offset`
   - `retired_worker`, `disabled_worker`, `deceased_worker`
6. **Conventions** — ages in months from the adjusted birth month (with the 1st-of-month rule), earnings matrices with `first_year`, and the scalar-in/scalar-out rule.
7. **Policy and reforms** — primitive fields, `replace`, `with_series`, the three TR alternatives.
8. **Microsimulation** — `microsim.py` and its measured timing.
9. **Scope and exactness:**
   - exact for wage-indexed computations with eligibility in 1979 or later
   - list what's not included (old-start, transitional guarantee, frozen minimum, DI guarantee, re-indexed widow(er) guarantee, totalization, divorced spouses, disability insured status, earnings test)
   - pre-1978 QCs are approximated
   - GPO is statutory-only
   - WEP/GPO are off by default because the Social Security Fairness Act repealed them
10. **Testing** — the differential approach against `anypia-engine`.

- [ ] **Step 4: Prepend 0.3.0 to `CHANGELOG.md`**

```markdown
## 0.3.0 — 2026-10-04

**Breaking: pyanypia is now a library of benefit-formula functions.** The full
AnyPIA port (`Worker`, `compute`, `compare`, Statements, `.pia` files, batch,
reforms) moved to [anypia-engine](https://github.com/anthonycolavito/anypia-engine)
as `anypia_engine` 0.2.0, unchanged apart from the name.

- Vectorized functions over NumPy arrays: AIME, PIA, family maximum, COLAs,
  claiming-age factors, special minimum, family and survivor benefits, WEP/GPO.
- `Policy`: primitive policy parameters with derived series, replacing `Law`/`Reform`.
- Penny-exact against anypia-engine for wage-indexed computations (eligibility 1979+).
```

- [ ] **Step 5: Full verification**

```bash
.venv/bin/ruff check src tests docs/examples && .venv/bin/mypy && .venv/bin/pytest -q && .venv/bin/pytest -q -m slow
```
Expected: everything passes. Report the slow-sweep case counts and exclusion counts in the PR description.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md docs/examples tests/test_examples.py
git commit -m "docs: README, examples and changelog for the 0.3.0 formula library

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: STOP and confirm with the user, then publish**

Ask: "Ready to push `formula-library`, open a PR to `main`, and after CI is green merge it and tag v0.3.0?" Only after a yes:

```bash
git push -u origin formula-library
gh pr create --title "pyanypia 0.3.0: benefit-formula library" --body "$(cat <<'EOF'
Replaces the full AnyPIA port with vectorized benefit-formula functions; the
engine moved to anthonycolavito/anypia-engine. See CHANGELOG.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
gh pr merge --merge && git switch main && git pull
git tag -a v0.3.0 -m "pyanypia 0.3.0" && git push origin v0.3.0
gh release create v0.3.0 --title v0.3.0 --notes-file <(sed -n '/## 0.3.0/,/## 0.2.0/p' CHANGELOG.md | sed '$d')
```

Then verify in a fresh venv that `pip install git+https://github.com/anthonycolavito/pyanypia@v0.3.0` imports and runs `hypotheticals.py`.
