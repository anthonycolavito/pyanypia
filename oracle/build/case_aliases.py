"""Creates case-variant header symlinks in the staged build tree.

Parts of the vendored source include a header under a different case than
the file actually carries -- ``anypiab.cpp`` asks for ``AnypiabDoc.h``
while the file is ``anypiabdoc.h``. That compiles on a case-insensitive
filesystem (macOS, Windows, where this code was written) and fails on a
case-sensitive one (Linux).

Rather than patch the vendored source in six places, this scans the staged
tree for includes whose exact-case file is missing but which match a real
header case-insensitively, and drops a symlink next to it. Run from the
Makefile after staging; the vendor tree itself is never touched.

    python3 case_aliases.py <staged-dir> [<staged-dir>...]

Pass the staged source trees themselves, not their parent: a stray second
copy of the sources under the given root would capture the symlinks and
leave the tree that actually gets compiled unaliased.
"""

from __future__ import annotations

import pathlib
import re
import sys

INCLUDE = re.compile(r'#include\s+"([^"]+)"')
HEADER_GLOBS = ("*.h", "*.H", "*.hpp")
SOURCE_GLOBS = ("*.cpp", "*.h", "*.H", "*.hpp")


def main(roots: list[pathlib.Path]) -> int:
    if not roots:
        print("case_aliases: no staged directories given", file=sys.stderr)
        return 2
    missing = [r for r in roots if not r.is_dir()]
    if missing:
        for root in missing:
            print(f"case_aliases: no such directory: {root}", file=sys.stderr)
        return 2

    headers: dict[str, pathlib.Path] = {}
    for root in roots:
        for pattern in HEADER_GLOBS:
            for path in root.rglob(pattern):
                headers.setdefault(path.name, path)
    by_lower = {name.lower(): path for name, path in headers.items()}

    sources = [p for root in roots for g in SOURCE_GLOBS for p in root.rglob(g)]
    made = 0
    for source in sources:
        try:
            text = source.read_text(errors="replace")
        except OSError:
            continue
        for match in INCLUDE.finditer(text):
            wanted = match.group(1).split("/")[-1]
            if wanted in headers:
                continue
            actual = by_lower.get(wanted.lower())
            if actual is None:
                # a Boost header, or a file this build does not compile
                continue
            link = actual.parent / wanted
            if link.is_symlink() or link.exists():
                # already aliased, or the filesystem is case-insensitive
                # and the include resolves on its own
                continue
            link.symlink_to(actual.name)
            headers[wanted] = link
            made += 1
            print(f"case alias: {wanted} -> {actual.name}")
    if made:
        print(f"case_aliases: {made} symlink(s) created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main([pathlib.Path(a) for a in sys.argv[1:]]))
