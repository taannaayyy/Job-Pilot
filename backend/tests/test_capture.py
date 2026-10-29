import base64

import pytest
from fastapi.testclient import TestClient

from jobpilot import linkedin
from jobpilot.main import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


@pytest.fixture
def client(tmp_path):
    # The extension settings only answer the app's own host name.
    return TestClient(create_app(tmp_path / "test.db"), base_url="http://127.0.0.1")


@pytest.fixture
def token(client):
    return client.get("/api/extension").json()["token"]


def capture(client, token, **overrides):
    body = {
        "url": "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=ml",
        "title": "Machine Learning Engineer",
        "company": "Acme AI",
        "company_linkedin_url": "https://www.linkedin.com/company/acme-ai/life/",
        "location": "Kadıköy, İstanbul, Türkiye",
        "workplace": "Hybrid",
        "employment_type": "Full-time",
        "description": "We build models.",
        **overrides,
    }
    return client.post("/api/capture", json=body, headers={"X-JobPilot-Token": token})


def test_ping_tells_the_extension_whether_its_key_works(client, token):
    assert client.get("/api/ping").json() == {"app": "jobpilot", "token_ok": False}
    assert client.get("/api/ping", headers={"X-JobPilot-Token": "nope"}).json()["token_ok"] is False
    assert client.get("/api/ping", headers={"X-JobPilot-Token": token}).json()["token_ok"] is True
    assert client.get("/api/extension").json()["last_seen"] is not None


def test_capture_needs_the_key(client, token):
    assert capture(client, "").status_code == 401
    assert capture(client, "wrong").status_code == 401
    assert client.get("/api/jobs").json() == []


def test_capture_creates_a_saved_job(client, token):
    res = capture(client, token)
    assert res.status_code == 200, res.text
    assert res.json()["created"] is True
    job = client.get(f"/api/jobs/{res.json()['job']['id']}").json()
    assert job["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert (job["city"], job["side"], job["district"]) == ("Istanbul", "anadolu", "Kadıköy")
    assert (job["work_mode"], job["job_type"], job["source"]) == ("hybrid", "full_time", "LinkedIn")
    assert job["status"] == "saved"
    assert job["raw_text"] == "We build models."
    org = client.get(f"/api/companies/{job['company_id']}").json()
    assert org["linkedin_url"] == "https://www.linkedin.com/company/acme-ai/"


def test_same_linkedin_job_is_saved_once(client, token):
    first = capture(client, token).json()
    again = capture(client, token, url="https://www.linkedin.com/jobs/view/4012345678/", title="Changed")
    assert again.json()["created"] is False
    assert again.json()["job"]["id"] == first["job"]["id"]
    assert len(client.get("/api/jobs").json()) == 1

    # Pasting the same posting's link by hand is caught too.
    res = client.post(
        "/api/jobs",
        json={"company": "Acme AI", "title": "ML", "url": "https://www.linkedin.com/jobs/view/ml-at-acme-4012345678"},
    )
    assert res.status_code == 409
    assert "Machine Learning Engineer" in res.json()["detail"]


def test_company_is_matched_by_its_linkedin_page(client, token):
    capture(client, token)
    capture(client, token, url="https://www.linkedin.com/jobs/view/4099999999/", company="Acme AI Inc.")
    assert {j["company"] for j in client.get("/api/jobs").json()} == {"Acme AI"}


def test_captured_logo_wins_over_the_website(client, token):
    calls = []
    client.app.state.logos.fetch = lambda domain: calls.append(domain)
    make = client.post("/api/jobs", json={"company": "Acme AI", "title": "Old", "company_website": "acme.ai"})
    assert make.status_code == 201

    job = capture(client, token, logo_base64=base64.b64encode(PNG).decode()).json()["job"]
    assert job["logo_url"].endswith("src=linkedin")
    res = client.get(job["logo_url"])
    assert res.status_code == 200 and res.content == PNG
    assert calls == []


def test_bad_logo_is_ignored(client, token):
    svg = base64.b64encode(b"<svg onload='x()'></svg>").decode()
    job = capture(client, token, logo_base64=svg).json()["job"]
    assert job["logo_url"] is None
    job = capture(client, token, url="https://www.linkedin.com/jobs/view/4011111111/", company="B", logo_base64="%%").json()["job"]
    assert job["logo_url"] is None


def test_non_linkedin_page_is_rejected(client, token):
    assert capture(client, token, url="https://example.com/jobs/1").status_code == 422


def test_new_key_locks_out_the_old_one(client, token):
    new = client.post("/api/extension/token", json={}).json()["token"]
    assert new != token
    assert capture(client, token).status_code == 401
    assert capture(client, new).status_code == 200


def test_extension_settings_refuse_other_hosts_and_form_posts(client, tmp_path):
    other = TestClient(client.app, base_url="http://evil.example")
    assert other.get("/api/extension").status_code == 403
    assert client.post("/api/extension/token", content="x", headers={"content-type": "text/plain"}).status_code == 415


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Kadıköy, İstanbul, Türkiye", ("Istanbul", "Kadıköy")),
        ("Istanbul, Türkiye (Hybrid)", ("Istanbul", None)),
        ("İstanbul Metropolitan Area", ("Istanbul", None)),
        ("Sariyer, Istanbul, Turkey", ("Istanbul", "Sarıyer")),
        ("Ankara, Türkiye", ("Ankara", None)),
        ("Türkiye (Remote)", (None, None)),
        ("Greater London", ("London", None)),
        (None, (None, None)),
    ],
)
def test_parse_location(raw, expected):
    assert linkedin.parse_location(raw) == expected


def test_job_id_from_url():
    assert linkedin.job_id_from_url("https://www.linkedin.com/jobs/view/4012345678/?refId=x") == "4012345678"
    assert linkedin.job_id_from_url("https://tr.linkedin.com/jobs/view/ml-engineer-at-acme-4012345678") == "4012345678"
    assert linkedin.job_id_from_url("https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678") == "4012345678"
    assert linkedin.job_id_from_url("https://example.com/jobs/view/4012345678") is None
    assert linkedin.job_id_from_url(None) is None


def test_work_mode_and_job_type():
    assert linkedin.parse_work_mode("On-site") == "onsite"
    assert linkedin.parse_work_mode(None, "Istanbul (Remote)") == "remote"
    assert linkedin.parse_job_type("INTERN") == "internship"
    assert linkedin.parse_job_type("Tam zamanlı") == "full_time"
    assert linkedin.parse_job_type("FULL_TIME") == "full_time"


def test_migration_fills_linkedin_ids(tmp_path):
    import sqlite3

    from alembic import command

    from jobpilot.main import MIGRATIONS_DIR
    from alembic.config import Config

    db = tmp_path / "old.db"
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "1ce10cf9c0b2")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO company (id, name, name_key, kind, notes, watching) VALUES (1, 'A', 'a', 'company', '', 0)")
    for i, url in enumerate(
        ["https://www.linkedin.com/jobs/view/4012345678/", "https://www.linkedin.com/jobs/view/4012345678", "https://a.com"]
    ):
        con.execute(
            "INSERT INTO job (id, company_id, title, url, status, notes, date_saved) VALUES (?, 1, 't', ?, 'saved', '', '2026-01-01')",
            (i + 1, url),
        )
    con.commit()
    command.upgrade(cfg, "head")
    rows = con.execute("SELECT id, linkedin_job_id FROM job ORDER BY id").fetchall()
    assert rows == [(1, "4012345678"), (2, None), (3, None)]
