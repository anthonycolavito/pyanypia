"""Error hierarchy mirroring PiaException.

Codes are the C++ resource ids (Resource.h) so differential tests can
assert that pyanypia rejects exactly the cases the oracle rejects.
Messages are pyanypia's own wording.
"""

from __future__ import annotations


class PiaError(Exception):
    """A calculation or input-validation error, with the AnyPIA resource
    id (when one corresponds) as ``code``."""

    def __init__(self, code: int, message: str = "") -> None:
        self.code = code
        super().__init__(message or f"PIA error {code}")


# Resource ids used across the package (transcribed from Resource.h as
# they are needed; names keep the C++ suffix for greppability).
PIA_IDS_QCTOT0 = 61437
PIA_IDS_RELERNPOS = 62050
PIA_IDS_ROUND = 62033
PIA_IDS_DATEMONTH = 62055
PIA_IDS_DATEYEAR = 62056
PIA_IDS_DATEDAY = 62057
PIA_IDS_AGEMONTH = 62096
