import pathlib
import runpy

import pytest

EXAMPLES = pathlib.Path(__file__).parent.parent / "docs" / "examples"


def test_hypotheticals_runs(capsys):
    runpy.run_path(str(EXAMPLES / "hypotheticals.py"))
    out = capsys.readouterr().out
    assert "reform PIA" in out and "spouse benefit" in out


@pytest.mark.slow
def test_microsim_runs(capsys):
    runpy.run_path(str(EXAMPLES / "microsim.py"))
    assert "100,000 workers" in capsys.readouterr().out
