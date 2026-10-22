import pytest

from app.database import initialize_database
from app.queue.engine import QueueEngine


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def engine(tmp_path, clock) -> QueueEngine:
    path = tmp_path / "test.sqlite"
    initialize_database(path)
    return QueueEngine(path, clock)
