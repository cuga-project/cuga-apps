import pytest


def pytest_collection_modifyitems(config, items):
    """Default async tests to asyncio mode without forcing a plugin marker."""
    for item in items:
        if "asyncio" in item.keywords:
            item.add_marker(pytest.mark.asyncio)
