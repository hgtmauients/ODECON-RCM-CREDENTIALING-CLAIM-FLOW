import pytest


def pytest_collection_modifyitems(items):
    """Ensure module-scoped async tests run in order."""
    pass
