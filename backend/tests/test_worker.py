import asyncio

from app.workers.worker import WorkerManager


def test_worker_executes_allowlisted_task_and_stops(engine):
    async def scenario():
        job = engine.publish("worker-test", "uppercase_text", {"text": "queueforge"})
        manager = WorkerManager(engine, poll_seconds=0.01)
        started = await manager.start("worker-test", 1)
        assert len(started) == 1
        try:
            async def wait_for_completion():
                while engine.get(job["id"])["status"] != "succeeded":
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_completion(), timeout=2)
        finally:
            stopped = await manager.stop("worker-test")
        assert stopped[0]["status"] == "stopped"
        assert engine.get(job["id"])["result"] == "QUEUEFORGE"

    asyncio.run(scenario())


def test_worker_cancellation_does_not_ack_incomplete_work(engine, clock):
    async def scenario():
        job = engine.publish(
            "worker-test", "simulate_failure", {"fail_attempts": 0, "delay_seconds": 5}
        )
        manager = WorkerManager(engine, poll_seconds=0.01)
        await manager.start("worker-test", 1)
        try:
            async def wait_until_running():
                while not manager.list() or manager.list()[0]["current_job_id"] is None:
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_until_running(), timeout=2)
        finally:
            await manager.stop("worker-test")
        assert engine.get(job["id"])["status"] == "leased"
        clock.advance(31)
        engine.recover_expired()
        assert engine.get(job["id"])["status"] == "queued"

    asyncio.run(scenario())
