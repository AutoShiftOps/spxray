"""Shared fixtures for the sql-sp-companion test suite."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    return GOLDEN


@pytest.fixture
def client():
    """FastAPI test client with the free tier active."""
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


@pytest.fixture
def free_tier(monkeypatch):
    monkeypatch.delenv("SPC_LICENSE_KEY", raising=False)
    from limits import FREE
    return FREE


@pytest.fixture
def enterprise_tier(monkeypatch):
    monkeypatch.setenv("SPC_LICENSE_KEY", "SPC-ENT-TESTKEY-000000000")
    from limits import ENTERPRISE
    return ENTERPRISE


def sql_fixture(name: str) -> str:
    """
    Load a .sql fixture the same way /analyze does: raw bytes through
    read_bytes_safe, not a hardcoded UTF-8 text read. Fixtures are UTF-8 in
    practice except utf16_bom.sql (deliberately saved as UTF-16LE with a BOM
    to exercise the decoder) -- read_bytes_safe tries utf-8 first, so this is
    a no-op for every other fixture; only utf16_bom.sql actually depends on it.
    """
    from main import read_bytes_safe
    return read_bytes_safe((FIXTURES / name).read_bytes())


def tables_of(physical) -> set:
    return {k for k in physical if k != "__UNRESOLVED__"}


def cols_of(physical, key) -> set:
    return physical.get(key, {}).get("columns", set())


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Regenerate golden snapshot files instead of asserting against them.",
    )
