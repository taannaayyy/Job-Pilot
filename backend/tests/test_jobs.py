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
    # A rebuilt app must never show the previous UI from the window's cache.
    assert res.headers["cache-control"] == "no-cache"
    assert client.get("/api/jobs").status_code == 200


def test_city_and_district(client):
    job = make_job(client, city="Istanbul", district="Kadıköy")
    assert (job["city"], job["district"]) == ("Istanbul", "Kadıköy")
    res = client.patch(f"/api/jobs/{job['id']}", json={"city": "  ", "district": None}).json()
    assert (res["city"], res["district"]) == (None, None)
    make_job(client, company="Other", city="Ankara")
    assert [j["company"] for j in client.get("/api/jobs?q=ankara").json()] == ["Other"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("insider.com", "https://insider.com"),
        ("https://www.Insider.com/careers?x=1", "https://insider.com"),
        ("http://jobs.trendyol.com", "https://jobs.trendyol.com"),
        ("", None),
    ],
)
def test_website_is_normalized(client, raw, expected):
    job = make_job(client, company_website=raw)
    assert job["company_website"] == expected
    assert (job["logo_url"] is None) == (expected is None)


def test_invalid_website_rejected(client):
    assert client.post("/api/jobs", json={"company": "A", "title": "x", "company_website": "not a site"}).status_code == 422


def test_blank_website_keeps_company_website(client):
    make_job(client, company_website="acme.ai")
    job = make_job(client, title="Data Scientist")
    assert job["company_website"] == "https://acme.ai"


def test_logo_is_fetched_once_and_cached(client):
    calls = []
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50

    def fake_fetch(domain):
        calls.append(domain)
        return png if domain == "acme.ai" else None

    client.app.state.logos.fetch = fake_fetch
    job = make_job(client, company_website="acme.ai")
    for _ in range(2):
        res = client.get(job["logo_url"])
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
    assert calls == ["acme.ai"]

    other = make_job(client, company="Nologo", company_website="nologo.dev")
    assert client.get(other["logo_url"]).status_code == 404
    assert client.get(other["logo_url"]).status_code == 404
    assert calls == ["acme.ai", "nologo.dev"]

    plain = make_job(client, company="Plain")
    assert client.get(f"/api/companies/{plain['company_id']}/logo").status_code == 404


def test_migration_splits_old_location():
    import importlib

    m = importlib.import_module("jobpilot.migrations.versions.78178a8c7016_company_website_and_city_district")
    assert m._split_location("Istanbul, Pendik ") == ("Istanbul", "Pendik")
    assert m._split_location("kadikoy") == ("Istanbul", "Kadıköy")
    assert m._split_location("İstanbul") == ("Istanbul", None)
    assert m._split_location("Ankara") == ("Ankara", None)


def test_district_implies_side(client):
    job = make_job(client, city="Istanbul", district="Kadıköy", side="avrupa")
    assert (job["side"], job["district"]) == ("anadolu", "Kadıköy")


def test_side_without_district(client):
    job = make_job(client, city="Istanbul", side="avrupa")
    assert (job["city"], job["side"], job["district"]) == ("Istanbul", "avrupa", None)
    res = client.patch(f"/api/jobs/{job['id']}", json={"district": "Pendik"}).json()
    assert (res["side"], res["district"]) == ("anadolu", "Pendik")


def test_other_city_clears_side_and_district(client):
    job = make_job(client, city="Istanbul", district="Şişli")
    res = client.patch(f"/api/jobs/{job['id']}", json={"city": "Ankara"}).json()
    assert (res["city"], res["side"], res["district"]) == ("Ankara", None, None)
    assert client.post("/api/jobs", json={"company": "A", "title": "x", "side": "north"}).status_code == 422


def test_side_migration_backfills_existing_jobs(tmp_path):
    import sqlite3

    from alembic import command
    from alembic.config import Config

    from jobpilot.main import MIGRATIONS_DIR

    db = tmp_path / "old.db"
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "78178a8c7016")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO company (id, name, name_key) VALUES (1, 'A', 'a')")
    for i, (city, district) in enumerate([("Istanbul", "Pendik"), ("Istanbul", "Şişli"), ("Ankara", None)], 1):
        con.execute(
            "INSERT INTO job (id, company_id, title, city, district, status, notes, date_saved)"
            " VALUES (?, 1, 't', ?, ?, 'saved', '', '2026-10-29 00:00:00')",
            (i, city, district),
        )
    con.commit()
    command.upgrade(cfg, "head")
    assert con.execute("SELECT side FROM job ORDER BY id").fetchall() == [("anadolu",), ("avrupa",), (None,)]


def test_watchlist_add_and_list(client):
    res = client.post(
        "/api/companies",
        json={
            "name": "KUIS AI Center",
            "kind": "research",
            "website": "ai.ku.edu.tr",
            "careers_url": "ai.ku.edu.tr/positions",
            "linkedin_url": "https://www.linkedin.com/company/kuis-ai",
        },
    )
    assert res.status_code == 201, res.text
    org = res.json()
    assert org["kind"] == "research"
    assert org["website"] == "https://ai.ku.edu.tr"
    assert org["careers_url"] == "https://ai.ku.edu.tr/positions"
    assert org["watching"] and org["date_watched"]
    assert org["openings"] is None and org["last_checked_at"] is None
    assert org["logo_url"]

    make_job(client, company="Not Watched Inc")
    assert [c["name"] for c in client.get("/api/companies?watching=true").json()] == ["KUIS AI Center"]
    assert len(client.get("/api/companies").json()) == 2


def test_watching_existing_company_keeps_its_jobs_and_website(client):
    job = make_job(client, company="Trendyol", company_website="trendyol.com")
    assert job["company_watching"] is False
    org = client.post("/api/companies", json={"name": "trendyol", "kind": "company"}).json()
    assert org["id"] == job["company_id"]
    assert org["website"] == "https://trendyol.com"
    assert (org["job_count"], org["active_job_count"]) == (1, 1)
    assert client.get(f"/api/jobs/{job['id']}").json()["company_watching"] is True


def test_recording_a_check_stamps_the_date(client):
    org = client.post("/api/companies", json={"name": "Getir"}).json()
    res = client.patch(f"/api/companies/{org['id']}", json={"openings": "hiring"}).json()
    assert res["openings"] == "hiring" and res["last_checked_at"]
    res = client.patch(f"/api/companies/{org['id']}", json={"watching": False}).json()
    assert res["watching"] is False


def test_company_rename_conflict_and_delete_rules(client):
    a = client.post("/api/companies", json={"name": "Alpha"}).json()
    client.post("/api/companies", json={"name": "Beta"})
    assert client.patch(f"/api/companies/{a['id']}", json={"name": "beta"}).status_code == 409
    assert client.patch(f"/api/companies/{a['id']}", json={"name": "Alpha Labs"}).json()["name"] == "Alpha Labs"

    job = make_job(client, company="Beta")
    assert client.delete(f"/api/companies/{job['company_id']}").status_code == 409
    assert client.delete(f"/api/companies/{a['id']}").status_code == 204
    assert client.get(f"/api/companies/{a['id']}").status_code == 404


def test_job_type(client):
    job = make_job(client, job_type="internship")
    assert job["job_type"] == "internship"
    assert make_job(client)["job_type"] is None
    res = client.patch(f"/api/jobs/{job['id']}", json={"job_type": "full_time"}).json()
    assert res["job_type"] == "full_time"
    assert client.post("/api/jobs", json={"company": "A", "title": "x", "job_type": "gig"}).status_code == 422


def test_awaiting_decision_status(client):
    job = make_job(client)
    res = client.patch(f"/api/jobs/{job['id']}", json={"status": "awaiting"}).json()
    assert res["status"] == "awaiting"
    assert res["date_applied"] is not None  # past the interviews means applied
    org = client.post("/api/companies", json={"name": "Acme AI"}).json()
    assert org["active_job_count"] == 1
