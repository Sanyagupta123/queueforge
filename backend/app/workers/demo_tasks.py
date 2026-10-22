import asyncio
import math
from typing import Any


async def execute(task_type: str, payload: dict[str, Any], attempts: int) -> Any:
    if task_type == "uppercase_text":
        text = payload.get("text")
        if not isinstance(text, str):
            raise ValueError("uppercase_text requires a string field named 'text'")
        return text.upper()
    if task_type == "calculate_sum":
        values = payload.get("values")
        if not isinstance(values, list) or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) for value in values
        ):
            raise ValueError("calculate_sum requires a list of numbers in 'values'")
        result = sum(values)
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("sum result must be finite")
        return result
    if task_type == "simulate_failure":
        fail_attempts = payload.get("fail_attempts", 1)
        if isinstance(fail_attempts, bool) or not isinstance(fail_attempts, int) or not 0 <= fail_attempts <= 10:
            raise ValueError("fail_attempts must be an integer between 0 and 10")
        delay = payload.get("delay_seconds", 0)
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= 10:
            raise ValueError("delay_seconds must be between 0 and 10")
        if delay:
            await asyncio.sleep(delay)
        if attempts <= fail_attempts:
            raise RuntimeError(f"Configured demo failure on attempt {attempts}")
        return {"message": "succeeded after configured failures", "attempts": attempts}
    raise ValueError("unsupported task type")
