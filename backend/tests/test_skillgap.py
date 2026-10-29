import json
import stat

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from jobpilot import ai, extraction, skills
from jobpilot.main import create_app
from jobpilot.models import Importance

POSTING = """About the job
We are looking for an AI Engineer to join our Applied ML team.

What you'll do
- Build retrieval-augmented generation (RAG) pipelines
- Deploy models to production with Docker and Kubernetes on AWS

Requirements
- BSc in Computer Science; MSc is a plus
- 2+ years of experience building machine learning systems in production
- Strong Python skills; experience with PyTorch and Hugging Face Transformers
- Fluent English; Turkish is a plus

Nice to have
- Experience with LangChain

What we offer
- Python lunches and mentorship
"""


def names(found):
    return {f.name: f.importance for f in found}


def test_dictionary_reads_sections_and_clauses():
    found = names(skills.find(POSTING))
    assert found["Python"] == found["PyTorch"] == found["Hugging Face"] == Importance.MUST
    assert found["Docker"] == found["Kubernetes"] == found["AWS"] == found["RAG"] == Importance.MUST
    assert found["Bachelor's degree"] == Importance.MUST and found["Master's degree"] == Importance.NICE
    assert found["English"] == Importance.MUST and found["Turkish"] == Importance.NICE
    assert found["2+ years of experience"] == Importance.MUST
    assert found["LangChain"] == Importance.NICE
    assert "Mentoring" not in found  # from the company's offer, not a requirement


@pytest.mark.parametrize(
    "text",
    [
        "Work with the rest of the team",
        "Send your CV to us",
        "React to customer feedback quickly",
        "You will excel at communication",
        "Spring 2027 internship",
        "Spark curiosity in others",
        "Fine-tune open-source models for Turkish and English",
    ],
)
def test_dictionary_ignores_ordinary_words(text):
    found = names(skills.find(text))
    assert not {"REST APIs", "Computer vision", "React", "Excel", "Spring", "Apache Spark", "English", "Turkish",
                "Open-source contributions"} & set(found), found


def test_dictionary_keeps_similar_languages_apart():
    found = names(skills.find("Requirements\nC++, C# or Go, and R for statistics; not R&D"))
    assert {"C++", "C#", "Go", "R"} <= set(found)
    assert "C" not in found


def test_lookup_merges_spellings():
    assert skills.lookup("pytorch")[0] == skills.lookup("Torch")[0] == "PyTorch"
    assert skills.lookup("Hugging Face Transformers")[0] == "Hugging Face"
    assert skills.lookup("Underwater basket weaving") is None


class FakeModel(ai.Provider):
    name = "ollama"

    def __init__(self, items=None, error=None):
        super().__init__({"model": "fake"})
        self.items, self.error = items or [], error

    def extract(self, text):
        if self.error:
            raise ai.AIError(self.error)
        return self.items


def test_model_only_adds_skills_the_dictionary_doesnt_know():
    model = FakeModel([
        ai.ModelItem("Experience with PyTorch and Docker", "experience", Importance.NICE, "PyTorch and Docker"),
        ai.ModelItem("torch", "framework", Importance.NICE, "PyTorch"),
        ai.ModelItem("Ranking models", "concept", Importance.MUST, "ranking models"),
        ai.ModelItem("Kafka", "tool", Importance.MUST, "Kafka"),  # not in the posting
    ])
    result = extraction.extract("Requirements\n- PyTorch\n- Docker\n- Ranking models", model)
    by_name = {i.name: i for i in result.items}
    # The dictionary read "Requirements"; the model doesn't overrule it.
    assert by_name["PyTorch"].importance == by_name["Docker"].importance == Importance.MUST
    assert by_name["Ranking models"].source == "model"
    assert set(by_name) == {"PyTorch", "Docker", "Ranking models"}
    assert result.used == "Dictionary + Ollama fake" and result.warning is None


# From a real posting: the duties list turned into "skills" by a small model.
DUTIES = """The requirements for the successful candidate are;
BSc or MSc degree in a quantitative field such as Computer Engineering, Mathematics, Statistics
Good understanding of Machine Learning algorithms such as regression, classification and clustering
Hands-on experience with data preprocessing, feature engineering, model training, and model evaluation
Familiarity with data visualization tools such as Power BI, Tableau, or equivalent
The key duties of the successful candidate are;
Perform exploratory data analysis (EDA) and generate actionable insights
Monitor model performance and contribute to model improvement activities
Work with senior team members and business stakeholders to translate business needs into analytical solutions
Prepare analytical outputs, reports, and visualizations for technical and non-technical stakeholders
Document analytical methodologies, assumptions, and model results
Collaborate with data engineers
Experience in cloud environments (Azure, AWS, GCP)
Knowledge of pharmaceutical industry
"""


def test_tasks_are_not_skills():
    model = FakeModel([
        ai.ModelItem(n, "tool", Importance.MUST, "")
        for n in [
            "Business translation", "Monitoring", "Report preparation", "Model documentation",
            "Hands-on experience with data preprocessing, feature engineering, model training, and model evaluation",
            "Exploratory Data Analysis (EDA)", "Experience in cloud environments (Azure, AWS, GCP)",
            "Familiarity with data visualization tools", "Knowledge of pharmaceutical industry",
            "Experience with deploying with Docker",
        ]
    ])
    found = {i.name: i for i in extraction.extract(DUTIES, model).items}
    for task in ["Business translation", "Monitoring", "Report preparation", "Model documentation", "Docker",
                 "Cloud environments", "Data visualization tools", "Stakeholder management", "Teamwork",
                 "Data structures and algorithms"]:
        assert task not in found, task
    assert {"Data preprocessing", "Model training", "Exploratory Data Analysis", "Pharmaceutical industry"} <= set(found)
    assert {"Feature engineering", "Model evaluation", "AWS", "Azure", "Google Cloud", "Tableau"} <= set(found)


def test_bsc_or_msc_requires_only_the_bsc():
    found = names(skills.find(DUTIES))
    assert (found["Bachelor's degree"], found["Master's degree"]) == (Importance.MUST, Importance.NICE)
    found = names(skills.find("Requirements\nMSc or PhD in Computer Science"))
    assert (found["Master's degree"], found["PhD"]) == (Importance.MUST, Importance.NICE)
    found = names(skills.find("Requirements\nBSc in Computer Science\nMSc in Statistics"))
    assert found["Master's degree"] == Importance.MUST  # both asked for, not as alternatives


def test_fields_of_study_and_task_words_are_not_skills():
    found = names(skills.find("Requirements\nBSc in Mathematics, Statistics or a related field\nGood understanding of statistical analysis"))
    assert found["Statistics"] == Importance.MUST and "statistical" in skills.find(
        "Requirements\nBSc in Mathematics, Statistics or a related field\nGood understanding of statistical analysis"
    )[-1].evidence
    assert "Statistics" not in names(skills.find("Requirements\nBSc in Mathematics, Statistics or a related field"))
    assert "Communication" not in names(skills.find("Ensure communication between teams"))
    assert "Communication" in names(skills.find("Excellent communication skills"))
    assert "AI agents" not in names(skills.find("Train our customer support agents"))
    model = FakeModel([ai.ModelItem("Experience with MLOps, model deployment and automation", "practice", Importance.NICE, "")])
    assert "Automation" not in {i.name for i in extraction.extract("Experience with MLOps, model deployment and automation", model).items}


def test_sentence_headings():
    found = names(skills.find("What we need:\nPython\nIt would be a plus if you have:\nDocker\nKubernetes"))
    assert found == {"Python": Importance.MUST, "Docker": Importance.NICE, "Kubernetes": Importance.NICE}


def test_model_names_for_degrees_and_languages_are_merged():
    model = FakeModel([
        ai.ModelItem("BSc in Computer Science", "education", Importance.MUST, "BSc"),
        ai.ModelItem("Fluent English", "spoken_language", Importance.MUST, "Fluent English"),
    ])
    result = extraction.extract("Requirements\n- BSc in CS\n- Fluent English", model)
    assert {i.name: i.importance for i in result.items} == {"Bachelor's degree": Importance.MUST, "English": Importance.MUST}


def test_dictionary_still_works_when_the_model_fails():
    result = extraction.extract("Requirements\n- Python", FakeModel(error="Ollama isn't running."))
    assert [i.name for i in result.items] == ["Python"]
    assert (result.used, result.warning) == ("Dictionary", "Ollama isn't running.")


# ---- Through the API


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "test.db", inline_extraction=True)
    c = TestClient(app, base_url="http://127.0.0.1")
    c.put("/api/ai/settings", json={"provider": "none"})  # never reach a real model in tests
    c.app = app
    return c


def target(client, title="AI Engineer", group="AI Engineer (now)", text=POSTING):
    group_id = next((g["id"] for g in client.get("/api/role-groups").json() if g["name"] == group), None)
    if group_id is None:
        group_id = client.post("/api/role-groups", json={"name": group}).json()["id"]
    job = client.post("/api/jobs", json={"company": "Acme AI", "title": title}).json()
    res = client.patch(f"/api/jobs/{job['id']}", json={"raw_text": text, "target_group_id": group_id})
    assert res.status_code == 200, res.text
    return res.json(), group_id


def test_becoming_a_target_reads_the_description(client):
    job, group_id = target(client)
    assert job["extraction_status"] == "done"
    assert job["extracted_with"] == "Dictionary"
    assert {"Python", "Docker", "RAG"} <= {r["name"] for r in job["requirements"]}
    assert client.get("/api/role-groups").json() == [{"id": group_id, "name": "AI Engineer (now)", "job_count": 1}]


def test_gap_list_counts_jobs_and_coverage(client):
    target(client, "AI Engineer")
    _, group_id = target(client, "ML Engineer", text="Requirements\n- Python\n- Kubernetes\nNice to have\n- Go")
    gap = client.get("/api/skill-gap", params={"group_id": group_id}).json()
    assert (gap["targets"], gap["extracted"], gap["pending"]) == (2, 2, 0)
    rows = {s["name"]: s for s in gap["skills"]}
    assert (rows["Python"]["jobs"], rows["Python"]["must"]) == (2, 2)
    assert gap["skills"][0]["jobs"] == 2  # most asked for first
    assert gap["coverage"] == 0

    python = rows["Python"]["id"]
    client.patch(f"/api/skills/{python}", json={"mark": "have", "plan_note": "Daily"})
    client.patch(f"/api/skills/{rows['Go']['id']}", json={"mark": "ignore"})
    gap = client.get("/api/skill-gap", params={"group_id": group_id}).json()
    total = sum((2 * s["must"] + s["nice"]) for s in gap["skills"] if s["mark"] != "ignore")
    assert gap["coverage"] == pytest.approx(4 / total)

    detail = client.get(f"/api/skills/{python}").json()
    assert [j["title"] for j in detail["jobs"]] == ["AI Engineer", "ML Engineer"]
    assert detail["plan_note"] == "Daily"
    assert [(h["from_mark"], h["to_mark"]) for h in detail["history"]] == [(None, "have")]


def test_only_targets_count(client):
    target(client)
    plain = client.post("/api/jobs", json={"company": "Beta", "title": "Data Scientist"}).json()
    client.patch(f"/api/jobs/{plain['id']}", json={"raw_text": "Requirements\n- Tableau"})
    names_ = {s["name"] for s in client.get("/api/skill-gap").json()["skills"]}
    assert "Tableau" not in names_ and "Python" in names_


def test_requirements_the_user_adds_survive_a_new_extraction(client):
    job, _ = target(client, text="Requirements\n- Python")
    job = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "Ranking models", "importance": "nice"}).json()
    python = next(r for r in job["requirements"] if r["name"] == "Python")
    job = client.delete(f"/api/jobs/{job['id']}/requirements/{python['id']}").json()
    assert {r["name"] for r in job["requirements"]} == {"Ranking models"}

    # Removed stays removed and added stays added when the description is read again.
    job = client.post(f"/api/jobs/{job['id']}/extract").json()
    assert {r["name"]: r["source"] for r in job["requirements"]} == {"Ranking models": "user"}
    assert "Python" not in {s["name"] for s in client.get("/api/skill-gap").json()["skills"]}

    # Adding it back by hand undoes the removal.
    job = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "python"}).json()
    assert {r["name"] for r in job["requirements"]} == {"Python", "Ranking models"}


def test_changing_the_description_reads_it_again(client):
    job, _ = target(client, text="Requirements\n- Python")
    job = client.patch(f"/api/jobs/{job['id']}", json={"raw_text": "Requirements\n- Rust"}).json()
    assert [r["name"] for r in job["requirements"]] == ["Rust"]


def test_study_only_and_deleting_a_group(client):
    job, group_id = target(client)
    job = client.patch(f"/api/jobs/{job['id']}", json={"study_only": True}).json()
    assert job["study_only"] is True
    assert client.get("/api/jobs").json()[0]["study_only"] is True
    assert client.delete(f"/api/role-groups/{group_id}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").json()["target_group_id"] is None
    assert client.get("/api/skill-gap").json()["targets"] == 0


def test_group_names_are_unique(client):
    client.post("/api/role-groups", json={"name": "AI Engineer"})
    assert client.post("/api/role-groups", json={"name": "ai  engineer"}).status_code == 409


def test_unknown_group_is_rejected(client):
    job = client.post("/api/jobs", json={"company": "Acme", "title": "X"}).json()
    assert client.patch(f"/api/jobs/{job['id']}", json={"target_group_id": 999}).status_code == 404


def test_api_keys_are_never_sent_back(client, tmp_path):
    res = client.put("/api/ai/settings", json={"provider": "anthropic", "providers": {"anthropic": {"api_key": "sk-secret", "model": "claude-haiku-5-5"}}})
    body = res.json()
    assert "sk-secret" not in res.text
    assert body["providers"]["anthropic"] == {"model": "claude-haiku-5-5", "has_key": True}
    path = tmp_path / "ai-settings.json"
    assert json.loads(path.read_text())["providers"]["anthropic"]["api_key"] == "sk-secret"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    # Leaving the key out keeps it; an empty key removes it.
    client.put("/api/ai/settings", json={"provider": "ollama", "providers": {"anthropic": {"model": "claude-opus-5-5"}}})
    assert client.get("/api/ai/settings").json()["providers"]["anthropic"]["has_key"] is True
    client.put("/api/ai/settings", json={"provider": "ollama", "providers": {"anthropic": {"api_key": ""}}})
    assert client.get("/api/ai/settings").json()["providers"]["anthropic"]["has_key"] is False


def test_ai_settings_only_answer_the_app(tmp_path):
    other = TestClient(create_app(tmp_path / "t.db", inline_extraction=True), base_url="http://evil.example")
    assert other.get("/api/ai/settings").status_code == 403


def test_dictionary_only_test_run(client):
    res = client.post("/api/ai/test", json={"provider": "none"}).json()
    assert res["used"] == "Dictionary only"
    assert {"Python", "SQL", "PyTorch", "Docker", "Kubernetes"} <= set(res["found"])


# ---- Providers, with fake servers


ANSWER = {"requirements": [{"name": "PyTorch", "category": "framework", "importance": "must", "evidence": "PyTorch"}]}


def test_ollama_uses_the_first_installed_model(monkeypatch):
    calls = []

    def fake(url, body=None, headers=None, timeout=0):
        calls.append((url, body))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:3b"}, {"name": "bge-m3:latest"}]}
        if url.endswith("/api/show"):
            return {"capabilities": ["embedding"] if body["model"].startswith("bge") else ["completion"]}
        return {"message": {"content": json.dumps(ANSWER)}}

    monkeypatch.setattr(ai, "_http_json", fake)
    ollama = ai.Ollama({"base_url": "http://localhost:11434", "model": ""})
    assert ollama.models() == ["llama3.2:3b", "qwen2.5:3b"]  # not the embedding model
    items = ollama.extract("text")
    assert [i.name for i in items] == ["PyTorch"]
    assert calls[-1][1]["model"] == "llama3.2:3b" and calls[-1][1]["format"] == ai.SCHEMA


def test_ollama_not_running(monkeypatch):
    def fake(*a, **k):
        raise ConnectionRefusedError

    monkeypatch.setattr(ai, "_http_json", fake)
    with pytest.raises(ai.AIError, match="isn't running"):
        ai.Ollama({"model": "x"}).extract("text")


def test_openai_compatible_falls_back_to_json_mode(monkeypatch):
    import io
    import urllib.error

    bodies = []

    def fake(url, body=None, headers=None, timeout=0):
        bodies.append((body, headers))
        if body["response_format"]["type"] == "json_schema":
            raise urllib.error.HTTPError(url, 400, "bad", {}, io.BytesIO(b'{"error": {"message": "no schema"}}'))
        return {"choices": [{"message": {"content": json.dumps(ANSWER)}}]}

    monkeypatch.setattr(ai, "_http_json", fake)
    provider = ai.OpenAICompatible({"base_url": "https://api.groq.com/openai/v1/", "model": "llama", "api_key": "k"})
    assert [i.name for i in provider.extract("text")] == ["PyTorch"]
    assert bodies[1][0]["response_format"] == {"type": "json_object"}
    assert bodies[1][1] == {"Authorization": "Bearer k"}


def _claude(monkeypatch, handler):
    def client(self):
        return anthropic.Anthropic(api_key="k", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)

    monkeypatch.setattr(ai.Claude, "_client", client)
    return ai.Claude({"model": "claude-haiku-5-5", "api_key": "k"})


def test_claude_asks_for_json_and_reads_it(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": json.dumps(ANSWER)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        })

    items = _claude(monkeypatch, handler).extract("text")
    assert [i.name for i in items] == ["PyTorch"]
    assert seen["model"] == "claude-haiku-5-5"
    assert seen["output_config"]["format"]["type"] == "json_schema"


def test_claude_wrong_key(monkeypatch):
    def handler(request):
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})

    with pytest.raises(ai.AIError, match="key is wrong"):
        _claude(monkeypatch, handler).extract("text")


def test_claude_needs_a_key():
    with pytest.raises(ai.AIError, match="Paste your Claude API key"):
        ai.Claude({"model": "claude-haiku-5-5", "api_key": ""}).extract("text")
