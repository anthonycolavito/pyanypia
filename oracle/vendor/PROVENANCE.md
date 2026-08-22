# Provenance

The C++ source in this directory is the Social Security Administration's
**Detailed Calculator (AnyPIA)** source code, published by SSA's Office of the
Chief Actuary (OACT) at ssa.gov (Detailed Calculator "source code" download).

- Version: 2026 Trustees Report edition
  (`oactobjs32/include/BaseYearNonFile.h`: `YEAR = 2026`, `TR_YEAR = 2026`;
  `source32/anypiab/anypiabdoc.cpp` header dated 8/26/2025).
- Copied from the archives `oactobjs32.zip` and `source32.zip` as extracted on
  2026-08-22. Subsets vendored: `oactobjs32/{include,misc,piadata,linux}` and
  `source32/anypiab` (console batch driver). The Windows MFC GUI
  (`source32/anypia32`), `piaout/`, `windows/`, and MSVC project files are not
  vendored. No other modifications were made; files here are pristine.
- Build patches, when required for modern toolchains, live in
  `oracle/patches/` and are applied to a work copy at build time — never to
  this directory.

## License

This source code is a work of the United States Government and is in the
public domain under 17 U.S.C. § 105. It is redistributed here for
reproducible differential testing of the `pyanypia` port against the official
calculator.
