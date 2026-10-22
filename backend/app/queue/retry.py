import math


def retry_delay(attempts: int, base_seconds: float = 1.0, max_seconds: float = 60.0) -> float:
    if isinstance(attempts, bool) or attempts < 1:
        raise ValueError("attempts must be a positive integer")
    if not isinstance(attempts, int):
        raise TypeError("attempts must be a positive integer")
    if not math.isfinite(base_seconds) or base_seconds <= 0:
        raise ValueError("base_seconds must be positive and finite")
    if not math.isfinite(max_seconds) or max_seconds < base_seconds:
        raise ValueError("max_seconds must be finite and at least base_seconds")
    return min(base_seconds * (2 ** (attempts - 1)), max_seconds)
