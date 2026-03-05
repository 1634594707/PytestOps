import pytest

from ntf.assertions import AssertionEngine
from ntf.extract import ExtractStore


@pytest.fixture
def extract_store() -> ExtractStore:
    return ExtractStore()


@pytest.fixture
def assertion_engine() -> AssertionEngine:
    return AssertionEngine()
