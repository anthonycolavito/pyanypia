import pyanypia


def test_import_and_version() -> None:
    assert pyanypia.__version__.startswith("0.")
