import importlib.metadata

import pyanypia


def test_import_and_version() -> None:
    """The version in the package and the version in the metadata must
    agree. Asserting only a prefix let them drift: pyproject said
    0.1.0.dev0 while the CHANGELOG announced 0.2.0, and nothing noticed.
    """
    assert pyanypia.__version__ == importlib.metadata.version("pyanypia")
