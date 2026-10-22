from concurrent.futures import ThreadPoolExecutor

import pytest

from app.queue.engine import InvalidTransition, JobNotFound


def test_publish_persists_and_rejects_unsupported_task(engine):
    job = engine.publish("emails", "uppercase_text", {"text": "hello"})
    assert engine.get(job["id"])["status"] == "queued"
    with pytest.raises(ValueError, match="unsupported"):
        engine.publish("emails", "arbitrary", {})


def test_claim_oldest_ack_requires_owner_and_token(engine, clock):
    first = engine.publish("default", "uppercase_text", {"text": "one"})
    engine.publish("default", "uppercase_text", {"text": "two"})
    claimed = engine.claim("default", "worker-a", 10)
    assert claimed["id"] == first["id"]
    assert claimed["attempts"] == 1
    with pytest.raises(InvalidTransition):
        engine.ack(claimed["id"], "worker-b", claimed["lease_token"])
    clock.advance(1)
    done = engine.ack(claimed["id"], "worker-a", claimed["lease_token"], "ONE")
    assert done["status"] == "succeeded"
    assert done["result"] == "ONE"
    with pytest.raises(InvalidTransition):
        engine.ack(claimed["id"], "worker-a", claimed["lease_token"])


def test_retry_delay_and_dead_letter(engine, clock):
    job = engine.publish("default", "simulate_failure", {"fail_attempts": 4}, max_attempts=2)
    first = engine.claim("default", "worker-a")
    retried = engine.fail(job["id"], "worker-a", first["lease_token"], "failure")
    assert retried["status"] == "queued"
    assert retried["available_at"] == clock.now + 1
    assert engine.claim("default", "worker-b") is None
    clock.advance(1)
    second = engine.claim("default", "worker-b")
    dead = engine.fail(job["id"], "worker-b", second["lease_token"], "still failing")
    assert dead["status"] == "dead"
    assert dead["attempts"] == 2


def test_expired_lease_is_recovered_and_stale_ack_is_rejected(engine, clock):
    job = engine.publish("default", "uppercase_text", {"text": "x"})
    old = engine.claim("default", "worker-old", lease_seconds=2)
    clock.advance(2)
    assert engine.recover_expired() == 1
    assert engine.get(job["id"])["status"] == "queued"
    clock.advance(1)
    new = engine.claim("default", "worker-new")
    with pytest.raises(InvalidTransition):
        engine.ack(job["id"], "worker-old", old["lease_token"])
    engine.ack(job["id"], "worker-new", new["lease_token"])


def test_expired_exhausted_lease_becomes_dead(engine, clock):
    job = engine.publish("default", "uppercase_text", {"text": "x"}, max_attempts=1)
    engine.claim("default", "worker", lease_seconds=1)
    clock.advance(1)
    engine.recover_expired()
    assert engine.get(job["id"])["status"] == "dead"


def test_ack_after_lease_expiry_is_rejected(engine, clock):
    job = engine.publish("default", "uppercase_text", {"text": "x"})
    claim = engine.claim("default", "worker", lease_seconds=2)
    clock.advance(2)
    with pytest.raises(InvalidTransition, match="expired"):
        engine.ack(job["id"], "worker", claim["lease_token"])


def test_simultaneous_claims_are_distinct(engine):
    jobs = [engine.publish("concurrent", "uppercase_text", {"text": str(i)}) for i in range(12)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        claims = list(pool.map(lambda i: engine.claim("concurrent", f"worker-{i}"), range(12)))
    claimed_ids = [claim["id"] for claim in claims if claim]
    assert len(claimed_ids) == len(set(claimed_ids)) == len(jobs)


def test_list_filters_and_stats(engine):
    engine.publish("one", "uppercase_text", {"text": "x"})
    engine.publish("two", "calculate_sum", {"values": [1]})
    jobs, total = engine.list_jobs(queue_name="one", limit=10)
    assert total == 1
    assert len(jobs) == 1
    assert engine.stats()["counts"]["queued"] == 2


def test_unknown_job_is_not_found(engine):
    with pytest.raises(JobNotFound):
        engine.get("missing")
