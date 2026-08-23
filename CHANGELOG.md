# Changelog

All notable changes to pyanypia are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-08-23

The first published release. Version 0.1.0 existed only as a development
version (`0.1.0.dev0`) and was never tagged or uploaded, so everything
below is new to anyone installing this.

### Added

- **The benefit engine**, a pure-Python port of the calculation in SSA's
  Detailed Calculator (AnyPIA), 2026 Trustees Report edition. Retirement,
  disability, survivor and auxiliary benefits; every PIA method the
  calculator implements — wage-indexed, old-start, PIA table, transitional
  guarantee, special minimum, frozen minimum, disability guarantee,
  child-care, re-indexed widow and the non-freeze computations — with
  method selection, the family maximum, and totalization.
- **`compute(worker)`** and a `Results` object exposing the AIME, every
  applicable method's PIA and MFB, the method that won, the family
  maximum, each family member's benefit, and the payable amount.
- **`compare(worker, reform)`** and a declarative reform layer
  (`pyanypia.law`) covering nine of the calculator's LawChange types:
  `NRACHANGE`, `COLACHANGE`, `WAGEBASECHG`, `DIDROP5`, `NEWFORMULA`,
  `DECLINEPERC`, `NEWSPECMIN`, `AGE65COMP` and `CHILDCAREDROPOUT`. A
  reform naming anything else is refused rather than silently ignored.
- **Social Security Statement estimates** (`calculate_statement`).
- **`.pia` file support** — the official case format, read and written.
  Files pyanypia writes are read identically by the official calculator,
  which is itself a test.
- **Batch computation** (`pyanypia.batch`), with a pandas DataFrame
  interface behind the `pandas` extra.
- **All three Trustees Report alternatives**, I, II and III.

### Fidelity

- 9,302 differential cases, each compared field by field against the
  compiled C++ oracle and matching to the cent: insured status,
  eligibility year, every method's AIME/PIA/MFB, the winning method, the
  family maximum, the reduction or credit months, every family member's
  benefit, and the payable amount. Cases the calculator rejects must be
  rejected with the same error code.
- The oracle is rebuilt from the vendored SSA source in CI on every push,
  and the committed goldens are re-derived from that fresh build, so the
  claim is checked rather than asserted.

### Known limitations

Documented in full in the README, and in short: most of the calculator's
forty LawChange types never reach the batch path's output and are out of
scope; the bend-point reforms cannot be computed by the calculator at all
and are refused; railroad earnings are not credited; and the Statement's
disability estimate is unavailable below full retirement age, because the
official calculator cannot produce one either — the other estimates are
returned and the reason is recorded on the result.

[0.2.0]: https://github.com/anthonycolavito/pyanypia/releases/tag/v0.2.0
