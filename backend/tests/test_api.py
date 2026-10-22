from fastapi.testclient import TestClient

from app.api import create_app


def test_api_publish_claim_ack_and_validation(tmp_path):
    app = create_app(tmp_path / "api.sqlite")
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        response = client.post("/api/jobs", json={
            "queue_name": "api", "task_type": "uppercase_text", "payload": {"text": "hello"},
        })
        assert response.status_code == 201
        job = response.json()
        claim = client.post("/api/jobs/claim", json={
            "queue_name": "api", "worker_id": "test-worker", "lease_seconds": 20,
        })
        assert claim.status_code == 200
        leased = claim.json()
        ack = client.post(f"/api/jobs/{job['id']}/ack", json={
            "worker_id": "test-worker", "lease_token": leased["lease_token"],
        })
        assert ack.status_code == 200
        assert ack.json()["status"] == "succeeded"
        assert client.get("/api/jobs?status=succeeded").json()["total"] == 1
        assert client.post("/api/jobs", json={
            "queue_name": "api", "task_type": "not-allowed", "payload": {},
        }).status_code == 422


def test_api_not_found_and_conflict(tmp_path):
    app = create_app(tmp_path / "api.sqlite")
    with TestClient(app) as client:
        assert client.get("/api/jobs/missing").status_code == 404
        job = client.post("/api/jobs", json={
            "queue_name": "api", "task_type": "uppercase_text", "payload": {"text": "x"},
        }).json()
        claim = client.post("/api/jobs/claim", json={
            "queue_name": "api", "worker_id": "owner",
        }).json()
        response = client.post(f"/api/jobs/{job['id']}/ack", json={
            "worker_id": "other", "lease_token": claim["lease_token"],
        })
        assert response.status_code == 409


def test_jobs_survive_application_restart(tmp_path):
    database = tmp_path / "persistent.sqlite"
    with TestClient(create_app(database)) as first_client:
        job = first_client.post("/api/jobs", json={
            "queue_name": "persist", "task_type": "calculate_sum", "payload": {"values": [2, 3]},
        }).json()

    with TestClient(create_app(database)) as restarted_client:
        persisted = restarted_client.get(f"/api/jobs/{job['id']}")
        assert persisted.status_code == 200
        assert persisted.json()["payload"] == {"values": [2, 3]}
        assert persisted.json()["status"] == "queued"


def test_demo_endpoint_publishes_real_jobs_and_starts_workers(tmp_path):
    with TestClient(create_app(tmp_path / "demo.sqlite")) as client:
        response = client.post("/api/demo/run", json={
            "queue_name": "demo-test", "jobs": 2, "workers": 1,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["published"] == 2
        assert len(body["workers"]) == 1
        listed = client.get("/api/jobs?queue_name=demo-test&limit=10")
        assert listed.json()["total"] == 2
