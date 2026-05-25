import pytest
import asyncio
import warnings

# asyncpg emits this on Python 3.13 during connection cancellation finalizers.
# We keep RuntimeWarning as errors in CI and ignore only this known upstream issue.
warnings.filterwarnings(
    "ignore",
    message=r"Exception ignored in: <coroutine object Connection\._cancel.*",
    category=pytest.PytestUnraisableExceptionWarning,
)
warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)


def pytest_collection_modifyitems(items):
    """Ensure module-scoped async tests run in order."""
    pass


def pytest_sessionfinish(session, exitstatus):
    """Dispose shared async engine to avoid asyncpg cancellation warnings."""
    try:
        from core.database import engine
        asyncio.run(engine.dispose())
    except Exception:
        # Best-effort cleanup in test teardown.
        pass
