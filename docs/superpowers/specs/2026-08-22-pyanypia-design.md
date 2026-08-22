# pyanypia — Design

**Date:** 2026-08-22
**Status:** Approved
**Author:** Anthony Colavito, with Claude

## Summary

`pyanypia` is a pure-Python port of the calculation engine inside SSA's Detailed
Calculator (AnyPIA), 2026 Trustees Report version. It computes Social Security
benefits — retirement, disability, survivor, and family — from a worker's earnings
record, under present law or under user-specified policy reforms, and matches the
official C++ calculator **to the cent**.

The architecture is a Pythonic re-architecture of the C++ (immutable input models,
pure calculation functions, a declarative reform layer) — **but the arithmetic is
not re-architected**: inside every calculation step, operation order and SSA's
rounding rules are transliterated faithfully from the C++, and the port is
differential-tested against a locally compiled `anypiab` oracle.

## Goals

1. **Penny-exact**: identical results to `anypiab` (2026 TR version) across a broad
   generated case suite — all PIA methods, all benefit types, reform scenarios.
2. **Usable in research**: clean single-case API for notebooks; batch API for many
   workers (DataFrame in/out); baseline-vs-reform comparison as a first-class call.
3. **Interoperable**: read and write official `.pia` case files.
4. **Complete**: everything `anypiab` computes, including the LawChange reform
   machinery — excluding only the Windows GUI and printed-page output formatting.
5. **Maintainable across annual updates**: when SSA publishes next year's source,
   the update should be a localized data/params change, not an archaeology project.

## Non-goals

- No GUI (the `anypia32` MFC program is out of scope).
- No reproduction of the `piaout` printed-page layouts; `results` provides its own
  structured detail and plain-text rendering instead.
- No numpy vectorization of the engine in v1. Batch = fast scalar loop +
  `multiprocessing`. (Vectorization would reorder float arithmetic and jeopardize
  penny-exactness; revisit only with the oracle harness as a safety net.)
- Not an official SSA product; README carries a clear disclaimer.

## Source material

- C++ source: `~/Desktop/Benefit calculator source code/` — `oactobjs32/`
  (`include/` 183 headers; `piadata/` 155 files, ~28K LOC core; `misc/` utilities;
  `piaout/` output classes, unported; `linux/`, `windows/` platform shims) and
  `source32/anypiab/` (console batch driver). `BaseYearNonFile.h` confirms
  YEAR = 2026, TR_YEAR = 2026.
- The C++ source is a US government work (public domain). It is **vendored into
  this repo** under `oracle/vendor/` with a provenance note, so the oracle can be
  built reproducibly here and in CI.

## Package architecture

```
pyanypia/
├── rounding.py      # SSA rounding primitives (dime-down, dollar-truncate,
│                    #   quarter-round, cent-round…) on IEEE doubles.
│                    #   The fidelity bedrock; property-tested vs the C++ helpers.
├── params/          # Law parameters and their projection:
│                    #   historical AWI series, wage bases (OASDI + HI), bend
│                    #   points, COLAs, QC amounts, NRA/age schedules, PIA tables,
│                    #   special-minimum amounts, catch-up increases; TR2026
│                    #   assumption sets (alternatives I, II, III) and
│                    #   user-specified assumptions. Data ported from the C++
│                    #   *NonFile classes into generated Python data modules
│                    #   (exact values, importable without parsing).
├── worker.py        # Immutable input model: Worker (DOB, sex, annual earnings,
│                    #   QCs pre-1978, disability periods, military service,
│                    #   noncovered employment/pension, railroad) and Family
│                    #   (spouse, children, widow(er), parents) for family benefits.
├── engine/          # Calculation core as pure functions:
│   ├── insured.py   #   QC totals, fully/currently/DI insured status
│   ├── aime.py      #   wage indexing, elapsed/base/computation years, dropout,
│   │                #     AIME and AMW computation
│   ├── methods/     #   one module per PIA method: wage_indexed, old_start,
│   │                #     pia_table, trans_guar, special_min, frozen_min,
│   │                #     dib_guar, childcare, reindexed_widow, totalization,
│   │                #     wage_indexed_nonfreeze
│   ├── select.py    #   method applicability rules + highest-PIA selection
│   └── benefit.py   #   COLA chains, early-retirement reduction, DRCs,
│                    #     family maximum (incl. combined maxima), earnings test,
│                    #     WEP and GPO, final benefit rounding
├── law.py           # Law = params + rule switches. Law.present_law() is the
│                    #   baseline; Reform is a declarative modification spec
│                    #   (re-architected LawChange layer).
├── results.py       # Rich result objects: indexed-earnings table, every
│                    #   method's PIA/MFB, selected method, insured status,
│                    #   monthly benefit(s); .detail() plain-text rendering.
├── io/              # .pia case-file reader/writer (official format round-trip).
└── batch.py         # compute over iterables / DataFrames; multiprocessing.
                     #   pandas is an optional extra; core is stdlib-only.
```

### Top-level API sketch

```python
import pyanypia as pia

w = pia.Worker(dob="1960-03-15", sex="F", earnings={1982: 14_000.0, ...})
r = pia.compute(w, benefit_date="2027-01")          # present law by default
r.pia, r.mba, r.aime, r.method                       # SSA's numbers, to the cent
r.methods["wage_indexed"].pia                        # per-method intermediates
r.detail()                                           # text detail, notebook-friendly

reform = pia.Reform(...)                             # declarative law changes
cmp = pia.compare(w, reform, benefit_date="2027-01") # baseline vs reform

df_out = pia.batch.compute(df_in)                    # DataFrame in → out
case = pia.io.read_pia("case.pia"); pia.io.write_pia(case, "out.pia")
```

Money values are Python floats carrying the same IEEE-double results as the C++
(exact to the cent after SSA rounding); `results` provides formatted-string and
integer-cent accessors at the boundary.

## Fidelity strategy

1. All money arithmetic flows through `rounding.py`, which replicates the C++
   helpers (`BenefitAmount` rounding, dime rounding down, dollar truncation,
   quarter-of-coverage rounding, 0.05 adjustments) on IEEE doubles. Never bare
   `round()`; no Decimal in the engine; no reduction reordering.
2. Inside each engine function, the computational step order follows the
   corresponding C++ routine. Re-architecture happens at module boundaries only.
3. Era-specific branches (pre-1977 law, 1977 law, 1978+ new start, 1990+ WEP, …)
   are ported as written, even where they look redundant — they are load-bearing.

## Oracle validation harness (repo `oracle/`, not shipped in the wheel)

- `oracle/vendor/` — vendored SSA C++ source (public domain), untouched.
- `oracle/build/` — Makefile building `anypiab` with clang++/g++ against system
  Boost headers (`brew install boost` on macOS; `libboost-dev` on ubuntu CI).
  Only header-only Boost pieces are used (date_time, serialization traits).
- `oracle/instrumented/` — a small patched copy of the `anypiab` driver whose
  `savecase` dumps intermediates (AIME, each method's PIA and MFB, insured status,
  benefit amounts) as JSON lines, so a divergence localizes to one engine function.
- `oracle/cases/` — a case **generator** sweeping: birth years 1910s–2000s ×
  benefit types (retirement, disability, survivor, family configurations) ×
  earnings patterns (steady, sporadic, always-max, zeros, late-start, military,
  noncovered) × entitlement ages × assumption alternatives × reform files.
- `tests/test_oracle.py` — runs generated cases through both implementations and
  asserts cent-equality on final and intermediate values. Runs locally and in a
  GitHub Actions job (ubuntu + libboost-dev). A fast smoke subset runs on every
  push; the full sweep runs nightly/on-demand.

Secondary validation: SSA Handbook / published worked examples as fixed unit
tests; `.pia` files round-trip byte-compatibly on the fields anypiab consumes.

## Reform layer (LawChange re-architecture)

The C++ `LawChange*` classes (~25) are mostly parameter overrides plus a few
alternate computations. Python design:

- `Reform` — a declarative spec (dataclass) whose fields correspond to LawChange
  capabilities: new PIA formula (NEWFORMULA), bend-point growth changes
  (BPFRACWAGE, BPMINCONST, BPSPECRATE), COLA changes (COLACHANGE), NRA schedule
  changes (NRACHANGE), wage-base changes (WAGEBASECHG), tax-rate changes
  (TAXRATECHG), widow factor (WIDFACTOR), wife factor (WIFEFACTOR), marriage
  length (MARRLENGTH), childcare credits/dropouts, declining-percent formulas,
  dropout changes, special minimum changes, all-earnings computation, age-65
  computation point, taxation of benefits changes, PSA accounts.
- `Law.apply(reform)` produces a new `Law`; parameter-style changes modify
  `params`, computation-style changes flip strategy hooks in `engine/`.
- Oracle parity: `anypiab` consumes law-change files, so the case generator also
  emits law-change scenarios and reform runs are differential-tested the same way.

## Delivery phases

Each phase ends with oracle-validated tests green, committed, and pushed.

1. **Scaffold** — repo layout, packaging (`pyproject.toml`), CI, vendored oracle
   source, oracle build working on this Mac, case generator skeleton.
2. **Bedrock** — `rounding.py` + the full `params/` data port (transcribing the
   `*NonFile` C++ data: AWI, bases, benefit increases, bend points, QC amounts,
   PIA tables, special-min tables, TR2026 projections). Tedious and critical.
3. **Modern retirement end-to-end** — worker model, insured status, AIME,
   wage-indexed method, COLAs, reduction/DRC, benefit rounding, and the initial
   `results` objects that expose it all. **First penny-exact milestone; already
   useful in real work.**
4. **All benefit types under the modern method** — disability (incl. freeze),
   survivor, family maximum and combined maxima, earnings test, WEP/GPO.
5. **Historical + special methods** — old-start (all variants), PIA table,
   transitional guarantee, special minimum, frozen minimum, DIB guarantee,
   childcare dropout, re-indexed widow(er), totalization, non-freeze.
6. **I/O, batch, facade polish** — `.pia` reader/writer, DataFrame batch +
   multiprocessing, `compare()`, docs and examples.
7. **Reform layer** — `Reform`/`Law.apply`, engine hooks, law-change oracle cases.

After the initial build, run multi-agent specialist review (per standing
preference) and iterate until sign-off.

## Testing strategy

- TDD throughout (superpowers workflow): unit tests per engine function using
  hand-computed or handbook values, then oracle differential suites per phase.
- Property tests for `rounding.py` against the C++ helper semantics.
- Golden `.pia` round-trip tests.
- CI: lint (ruff), type-check (mypy on public API), unit + smoke oracle diff on
  push; full oracle sweep nightly/on-demand.

## Repo & housekeeping

- Public repo `pyanypia` on the user's GitHub; local checkout `~/pyanypia`.
- MIT license for the port, with attribution: derived from SSA/OACT's public
  domain Detailed Calculator source (2026 TR version); "not an official SSA
  product" disclaimer; no warranty for benefit decisions.
- Python ≥ 3.11. Zero runtime dependencies; `pyanypia[pandas]` extra for batch
  DataFrame support. Dev deps: pytest, ruff, mypy.
- Conventional layout: `src/pyanypia/`, `tests/`, `oracle/`, `docs/`.

## Risks

- **Oracle build friction**: 2005-era C++ may need small portability patches
  (kept in `oracle/instrumented/`, vendor tree untouched). Verified: Apple
  clang 14 present; Boost headers required (`brew install boost`).
- **Data transcription errors** in Phase 2 — mitigated by extracting values
  programmatically from the C++ source where possible, plus oracle diffs.
- **Float-order divergence** — mitigated by the transliteration rule and by
  intermediate-level oracle comparison, which catches divergences at the step
  where they occur.
- **Scope**: this is a large multi-phase port; phases are sequenced so the
  package is useful from Phase 3 onward.
