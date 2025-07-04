import pytest


@pytest.fixture
def words() -> list[str]:
    return ["One", "Two"]
