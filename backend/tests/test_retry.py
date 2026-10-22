import pytest

from app.queue.retry import retry_delay


def test_exponential_backoff_and_maximum_delay():
    assert retry_delay(1) == 1
    assert retry_delay(2) == 2
    assert retry_delay(3) == 4
    assert retry_delay(10) == 60


@pytest.mark.parametrize("attempts", [0, -1, True, 1.5])
def test_invalid_attempt_count_is_rejected(attempts):
    with pytest.raises((TypeError, ValueError)):
        retry_delay(attempts)
