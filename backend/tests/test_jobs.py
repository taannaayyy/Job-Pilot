import pytest
from fastapi.testclient import TestClient

from jobpilot.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "test.db"))


def make_job(client, **overrides):
    body = {"company": "Acme AI", "title": "ML Engineer", **overrides}
    res = client.post("/api/jobs", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_records_initial_event(client):
    job = make_job(client)
    assert job["status"] == "saved"
    assert job["date_applied"] is None
    assert [(e["from_status"], e["to_status"]) for e in job["events"]] == [(None, "saved")]


def test_applied_stamps_date_once(client):
    job = make_job(client)
    applied = client.patch(f"/api/jobs/{job['id']}", json={"status": "applied"}).json()
    assert applied["date_applied"] is not None
    assert applied["date_applied"].endswith(("Z", "+00:00"))

    client.patch(f"/api/jobs/{job['id']}", json={"status": "interview"})
    again = client.patch(f"/api/jobs/{job['id']}", json={"status": "applied"}).json()
    assert again["date_applied"] == applied["date_applied"]
    assert [e["to_status"] for e in again["events"]] == ["saved", "applied", "interview", "applied"]


def test_same_status_adds_no_event(client):
    job = make_job(client)
    res = client.patch(f"/api/jobs/{job['id']}", json={"status": "saved"}).json()
    assert len(res["events"]) == 1


def test_create_as_applied(client):
    job = make_job(client, status="applied")
    assert job["date_applied"] is not None


def test_later_stage_stamps_applied_date(client):
    job = make_job(client)
    res = client.patch(f"/api/jobs/{job['id']}", json={"status": "interview"}).json()
    assert res["date_applied"] is not None
    assert make_job(client, status="screening")["date_applied"] is not None
    assert make_job(client, status="rejected")["date_applied"] is None


def test_company_is_deduplicated(client):
    make_job(client, company="Acme AI")
    make_job(client, company="  acme   ai ", title="Data Scientist")
    jobs = client.get("/api/jobs").json()
    assert {j["company"] for j in jobs} == {"Acme AI"}


def test_filters(client):
    make_job(client, company="Foo", title="Data Scientist", work_mode="remote")
    make_job(client, company="Bar", title="AI Engineer", work_mode="onsite", status="applied")
    assert [j["company"] for j in client.get("/api/jobs?status=applied").json()] == ["Bar"]
    assert [j["company"] for j in client.get("/api/jobs?work_mode=remote").json()] == ["Foo"]
    assert [j["company"] for j in client.get("/api/jobs?q=data").json()] == ["Foo"]
    assert [j["company"] for j in client.get("/api/jobs?q=bar").json()] == ["Bar"]


def test_update_fields_and_delete(client):
    job = make_job(client)
    res = client.patch(
        f"/api/jobs/{job['id']}",
        json={"notes": "Talked to recruiter", "next_action": "Follow up Friday", "company": "Other Co"},
    ).json()
    assert res["notes"] == "Talked to recruiter"
    assert res["next_action"] == "Follow up Friday"
    assert res["company"] == "Other Co"

    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_validation(client):
    assert client.post("/api/jobs", json={"company": "", "title": "x"}).status_code == 422
    assert client.post("/api/jobs", json={"company": "A", "title": "x", "url": "nope"}).status_code == 422
    assert client.post("/api/jobs", json={"company": "A", "title": "x", "status": "bogus"}).status_code == 422


def test_serves_built_ui(client):
    from jobpilot.main import WEB_DIR

    if not (WEB_DIR / "index.html").is_file():
        pytest.skip("UI not built")
    res = client.get("/")
    assert res.status_code == 200
    assert "<div id=\"root\">" in res.text
    assert client.get("/api/jobs").status_code == 200
