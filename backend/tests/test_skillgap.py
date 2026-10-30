import json
import os
import stat
import subprocess

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

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
    by_name = {f.name: f for f in skills.find(POSTING)}
    # "2+ years of experience building machine learning systems": the years are about machine learning.
    assert (by_name["Machine learning"].min_years, by_name["Machine learning"].max_years) == (2, None)
    assert "Professional experience" not in found
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

    def extract(self, text, tree=None):
        self.tree = tree
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
                 "Data visualization tools", "Stakeholder management", "Teamwork", "Data structures and algorithms"]:
        assert task not in found, task
    # A category with its examples counts, and so does each example.
    assert {"Data preprocessing", "Model training", "Exploratory Data Analysis", "Pharmaceutical industry",
            "Cloud environments"} <= set(found)
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
    assert body["providers"]["anthropic"] == {"model": "claude-haiku-5-5", "has_key": True, "model_decides": True}
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


# ---- Who decides must or nice


SECTIONS = """Requirements
- Python
- SQL
The key duties are;
- Build models
- Experience with Kubernetes
"""


class DecidingModel(FakeModel):
    def __init__(self, decides):
        super().__init__([
            ai.ModelItem("Python", "language", Importance.MUST, "Python"),
            ai.ModelItem("Experience with Kubernetes", "tool", Importance.NICE, "Kubernetes"),
        ])
        self.config = {"model": "fake", "model_decides": decides}


def test_a_strong_model_decides_must_or_nice():
    found = {i.name: i.importance for i in extraction.extract(SECTIONS, DecidingModel(True)).items}
    assert found["Kubernetes"] == Importance.NICE  # the model read it as a plus
    assert found["Python"] == found["SQL"] == Importance.MUST


def test_otherwise_the_dictionary_decides():
    found = {i.name: i.importance for i in extraction.extract(SECTIONS, DecidingModel(False)).items}
    assert found["Kubernetes"] == Importance.MUST


def test_the_degree_rule_holds_even_when_the_model_decides():
    model = FakeModel([ai.ModelItem("BSc or MSc degree", "education", Importance.MUST, "BSc or MSc")])
    model.config = {"model": "fake", "model_decides": True}
    found = {i.name: i.importance for i in extraction.extract("Requirements\nBSc or MSc degree", model).items}
    assert (found["Bachelor's degree"], found["Master's degree"]) == (Importance.MUST, Importance.NICE)


def test_model_decides_is_saved_per_provider(client):
    client.put("/api/ai/settings", json={"provider": "ollama", "providers": {"ollama": {"model_decides": True}}})
    settings = client.get("/api/ai/settings").json()["providers"]
    assert settings["ollama"]["model_decides"] is True and settings["claude_code"]["model_decides"] is True


# ---- Claude Code


def _fake_cli(monkeypatch, stdout="", stderr="", code=0, error=None):
    calls = []

    def run(cmd, prompt, cwd, env):
        calls.append({"cmd": cmd, "prompt": prompt, "cwd": cwd, "env": env})
        if error:
            raise error
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    monkeypatch.setattr(ai, "_run_cli", run)
    return calls


@pytest.fixture
def claude_bin(tmp_path):
    path = tmp_path / "claude"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return str(path)


def test_claude_code_reads_structured_output(monkeypatch, claude_bin):
    calls = _fake_cli(monkeypatch, json.dumps({"type": "result", "is_error": False, "result": "", "structured_output": ANSWER}))
    items = ai.ClaudeCode({"path": claude_bin, "model": "sonnet"}).extract("posting text")
    assert [i.name for i in items] == ["PyTorch"]
    cmd = calls[0]["cmd"]
    # It can only read what it's given: no tools, no MCP servers, no settings, no saved sessions.
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert {"-p", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(cmd)
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == ai.SCHEMA
    assert calls[0]["prompt"].endswith("posting text")
    # Run in an empty folder of its own, not the app's or a project's.
    assert "jobpilot-" in calls[0]["cwd"] and not os.path.exists(calls[0]["cwd"])


def test_claude_code_without_a_model_uses_its_own_default(monkeypatch, claude_bin):
    calls = _fake_cli(monkeypatch, json.dumps({"is_error": False, "result": json.dumps(ANSWER)}))
    items = ai.ClaudeCode({"path": claude_bin, "model": ""}).extract("text")
    assert "--model" not in calls[0]["cmd"]
    assert [i.name for i in items] == ["PyTorch"]  # read from "result" when there's no structured_output


@pytest.mark.parametrize(
    "result, expected",
    [
        ("Not logged in · Please run /login", "isn't logged in"),
        ("Claude AI usage limit reached|1761868800", "usage limit"),
        ("There's an issue with the selected model (x).", "selected model"),
    ],
)
def test_claude_code_errors(monkeypatch, claude_bin, result, expected):
    _fake_cli(monkeypatch, json.dumps({"is_error": True, "result": result}), code=1)
    with pytest.raises(ai.AIError, match=expected):
        ai.ClaudeCode({"path": claude_bin}).extract("text")


def test_claude_code_crash_and_timeout(monkeypatch, claude_bin):
    _fake_cli(monkeypatch, stdout="", stderr="segfault", code=139)
    with pytest.raises(ai.AIError, match="segfault"):
        ai.ClaudeCode({"path": claude_bin}).extract("text")
    _fake_cli(monkeypatch, error=subprocess.TimeoutExpired("claude", 1))
    with pytest.raises(ai.AIError, match="too long"):
        ai.ClaudeCode({"path": claude_bin}).extract("text")


def test_claude_code_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)
    monkeypatch.setattr(ai, "_CLAUDE_PLACES", (str(tmp_path / "nope"),))
    with pytest.raises(ai.AIError, match="isn't installed"):
        ai.ClaudeCode({}).models()
    with pytest.raises(ai.AIError, match="no Claude Code at"):
        ai.ClaudeCode({"path": str(tmp_path / "missing")}).extract("text")


def test_claude_code_is_found_outside_path(monkeypatch, claude_bin):
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)  # an app opened from Finder has a short PATH
    monkeypatch.setattr(ai, "_CLAUDE_PLACES", (claude_bin,))
    assert ai.ClaudeCode({}).binary() == claude_bin


def test_claude_code_settings_round_trip(client):
    body = client.put("/api/ai/settings", json={
        "provider": "claude_code", "providers": {"claude_code": {"path": "~/bin/claude", "model": "sonnet"}},
    }).json()
    assert body["provider"] == "claude_code"
    assert body["providers"]["claude_code"] == {
        "path": "~/bin/claude", "model": "sonnet", "effort": "medium", "model_decides": True,
    }
    assert client.put("/api/ai/settings", json={
        "provider": "claude_code", "providers": {"claude_code": {"effort": "extreme"}},
    }).status_code == 422


def test_claude_code_defaults_to_opus_at_medium_effort(monkeypatch, tmp_path, claude_bin):
    monkeypatch.setattr(ai.shutil, "which", lambda _: claude_bin)
    calls = _fake_cli(monkeypatch, json.dumps({"is_error": False, "structured_output": ANSWER}))
    ai.Settings(tmp_path / "s.json").provider().extract("text")
    cmd = calls[0]["cmd"]
    assert (cmd[cmd.index("--model") + 1], cmd[cmd.index("--effort") + 1]) == ("claude-opus-5-5", "medium")
    assert ai.Settings(tmp_path / "s.json").provider().describe() == "Claude Code Opus 5.5, medium effort"


def test_claude_code_effort_is_passed_on(monkeypatch, claude_bin):
    calls = _fake_cli(monkeypatch, json.dumps({"is_error": False, "structured_output": ANSWER}))
    ai.ClaudeCode({"path": claude_bin, "model": "claude-haiku-5-5", "effort": "max"}).extract("text")
    assert calls[0]["cmd"][calls[0]["cmd"].index("--effort") + 1] == "max"
    ai.ClaudeCode({"path": claude_bin, "model": "", "effort": ""}).extract("text")  # Claude Code's own defaults
    assert "--effort" not in calls[1]["cmd"] and "--model" not in calls[1]["cmd"]


def test_default_is_claude_code_when_installed(monkeypatch, tmp_path, claude_bin):
    monkeypatch.setattr(ai.shutil, "which", lambda _: claude_bin)
    assert ai.Settings(tmp_path / "a.json").load()["provider"] == "claude_code"
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)
    monkeypatch.setattr(ai, "_CLAUDE_PLACES", ())
    assert ai.Settings(tmp_path / "b.json").load()["provider"] == "ollama"


# ---- The tree


def test_years_go_on_the_skill_they_are_about():
    found = {f.name: f for f in skills.find("Requirements\n- 3-5 years of Python and SQL\n- 5+ years of professional experience")}
    assert (found["Python"].min_years, found["Python"].max_years) == (3, 5)
    assert (found["SQL"].min_years, found["SQL"].max_years) == (3, 5)
    assert (found["Professional experience"].min_years, found["Professional experience"].group) == (5, "experience")


def test_degrees_carry_their_fields_and_libraries_their_language():
    found = {f.name: f for f in skills.find(
        "Requirements\nBSc in a quantitative field such as Computer Engineering, Mathematics, or related disciplines\npandas, PyTorch")}
    assert found["Bachelor's degree"].detail == "Computer Engineering, Mathematics"
    assert found["pandas"].parent == found["PyTorch"].parent == "Python"
    assert (found["pandas"].group, found["SQL"].group if "SQL" in found else "tech.databases") == ("tech.libraries", "tech.databases")


def test_the_model_files_in_the_users_tree_and_reports_years():
    tree = extraction.Tree.default()
    model = FakeModel([
        ai.ModelItem("Model training", "Knowledge areas › Machine learning", Importance.MUST, "model training"),
        ai.ModelItem("Professional experience", "Experience", Importance.MUST, "3+ years", min_years=3),
        ai.ModelItem("Python", "Technologies › Programming languages", Importance.MUST, "", min_years=2, max_years=4),
        ai.ModelItem("Quantitative field degree", "Education", Importance.MUST, "quantitative field"),
        ai.ModelItem("Feast", "Technologies › MLOps & dev tools", Importance.NICE, "Feast", parent="Made-up parent"),
    ])
    text = "Requirements\n- 3+ years in industry\n- Python\n- Model training\n- A quantitative field degree\n- Feast"
    found = {i.name: i for i in extraction.extract(text, model, tree=tree).items}
    assert model.tree == tree.groups  # the model saw the tree
    assert found["Model training"].group_path == "Knowledge areas › Machine learning"
    assert (found["Professional experience"].min_years, found["Professional experience"].group_key) == (3, "experience")
    assert (found["Python"].min_years, found["Python"].max_years) == (2, 4)  # years from the model on a dictionary skill
    assert "Quantitative field degree" not in found  # degrees come from the dictionary
    assert found["Feast"].parent == "Made-up parent"


def test_the_prompt_lists_the_tree():
    text = ai.prompt(ai.default_tree())
    assert "- Technologies › Cloud & infrastructure: AWS" in text and "- Soft skills:" in text
    assert ai.schema(ai.default_tree())["properties"]["requirements"]["items"]["properties"]["group"]["enum"][0] == (
        "Technologies › Programming languages"
    )


def _groups(client):
    return {g["name"]: g for g in client.get("/api/skill-groups").json()}


def test_extracted_skills_are_filed_with_their_parents(client):
    target(client, text="Requirements\n- pandas and SQL\n- 3+ years of AWS")
    groups = {g["id"]: g["name"] for g in client.get("/api/skill-groups").json()}
    gap = client.get("/api/skill-gap").json()
    rows = {s["name"]: s for s in gap["skills"]}
    assert groups[rows["pandas"]["group_id"]] == "Libraries & frameworks"
    assert groups[rows["SQL"]["group_id"]] == "Databases & SQL"
    assert rows["AWS"]["years"] == ["3+"]
    python = next(s for s in client.get("/api/skills").json() if s["name"] == "Python")
    assert rows["pandas"]["parent_id"] == python["id"]
    assert {g["name"] for g in gap["groups"]} >= {"Technologies", "Soft skills"}


def test_editing_the_tree(client):
    tech = _groups(client)["Technologies"]
    groups = client.post("/api/skill-groups", json={"name": "Vector search", "parent_id": tech["id"]}).json()
    new = next(g for g in groups if g["name"] == "Vector search")
    assert new["position"] == 7  # after the seven starting subgroups
    client.patch(f"/api/skill-groups/{new['id']}", json={"index": 0})
    assert _groups(client)["Vector search"]["position"] == 0
    assert _groups(client)["Programming languages"]["position"] == 1
    client.patch(f"/api/skill-groups/{new['id']}", json={"name": "Search", "description": "Elasticsearch, vector search"})
    assert _groups(client)["Search"]["description"] == "Elasticsearch, vector search"
    # Not inside itself or its own subgroups.
    assert client.patch(f"/api/skill-groups/{tech['id']}", json={"parent_id": new["id"]}).status_code == 422


def test_dragging_a_group_into_another_place(client):
    groups = _groups(client)
    cloud, know, ml = groups["Cloud & infrastructure"], groups["Knowledge areas"], groups["Machine learning"]
    client.patch(f"/api/skill-groups/{cloud['id']}", json={"parent_id": know["id"], "index": 1})
    groups = _groups(client)
    assert groups["Cloud & infrastructure"]["parent_id"] == know["id"]
    assert groups["Cloud & infrastructure"]["position"] == 1 and groups["Deep learning"]["position"] == 2
    assert groups["Machine learning"]["position"] == ml["position"] == 0
    # The groups it left close the gap.
    tech = sorted((g for g in groups.values() if g["parent_id"] == groups["Technologies"]["id"]), key=lambda g: g["position"])
    assert [g["position"] for g in tech] == list(range(6))
    # Out to the top level, at the end.
    client.patch(f"/api/skill-groups/{cloud['id']}", json={"parent_id": None})
    groups = _groups(client)
    assert groups["Cloud & infrastructure"]["parent_id"] is None
    assert groups["Cloud & infrastructure"]["position"] == max(g["position"] for g in groups.values() if g["parent_id"] is None)


def test_deleting_a_group_moves_its_skills_and_subgroups_up(client):
    target(client, text="Requirements\n- Docker")
    groups = _groups(client)
    cloud, tech = groups["Cloud & infrastructure"], groups["Technologies"]
    client.post("/api/skill-groups", json={"name": "Containers", "parent_id": cloud["id"]})
    client.delete(f"/api/skill-groups/{cloud['id']}")
    groups = _groups(client)
    assert "Cloud & infrastructure" not in groups and groups["Containers"]["parent_id"] == tech["id"]
    docker = next(s for s in client.get("/api/skill-gap").json()["skills"] if s["name"] == "Docker")
    assert docker["group_id"] == tech["id"]


def test_a_skill_the_user_moves_stays_there(client):
    job, _ = target(client, text="Requirements\n- Docker")
    soft = _groups(client)["Soft skills"]
    docker = next(s for s in client.get("/api/skill-gap").json()["skills"] if s["name"] == "Docker")
    detail = client.patch(f"/api/skills/{docker['id']}", json={"group_id": soft["id"]}).json()
    assert detail["group_locked"] is True
    client.post(f"/api/jobs/{job['id']}/extract")
    docker = next(s for s in client.get("/api/skill-gap").json()["skills"] if s["name"] == "Docker")
    assert docker["group_id"] == soft["id"]


def test_a_skill_cant_be_under_its_own_child(client):
    target(client, text="Requirements\n- pandas")
    by_name = {s["name"]: s for s in client.get("/api/skills").json()}
    pandas, python = by_name["pandas"], by_name["Python"]
    assert pandas["parent_id"] == python["id"]
    assert client.patch(f"/api/skills/{python['id']}", json={"parent_id": pandas["id"]}).status_code == 422


def test_old_skills_are_filed_on_upgrade(tmp_path):
    from jobpilot.models import Skill

    app = create_app(tmp_path / "t.db", inline_extraction=True)
    with app.state.sessionmaker() as session:
        session.add_all([Skill(name="pandas", key="pandas", category="framework"),
                         Skill(name="Ranking", key="ranking", category="concept")])
        session.commit()
        extraction.refile(session, extraction.Tree.load(session))
        session.commit()
        tree = extraction.Tree.load(session)
        pandas = session.scalar(select(Skill).where(Skill.key == "pandas"))
        ranking = session.scalar(select(Skill).where(Skill.key == "ranking"))
        assert pandas.group_id == tree.id_of_key["tech.libraries"] and pandas.parent.name == "Python"
        assert ranking.group_id is None  # its old kind was the model's guess; the next reading files it


class ChattyModel(ai.Provider):
    name = "ollama"

    def chat(self, system, messages):
        self.seen = (system, messages)
        return "Move Docker to Cloud & infrastructure."


def test_recommendation_chat_sends_the_whole_tree(client, monkeypatch):
    target(client, text="Requirements\n- pandas\n- Docker")
    model = ChattyModel({})
    monkeypatch.setattr(ai.Settings, "provider", lambda self, name=None, overrides=None: model)
    res = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "Recommend changes"}]})
    assert res.json() == {"reply": "Move Docker to Cloud & infrastructure.", "used": "Ollama"}
    system, messages = model.seen
    assert "[Technologies]" in system and "[Soft skills]" in system
    assert "- Python (in 0 jobs)" not in system  # only skills jobs ask for
    # pandas once, in its own group, pointing at Python, not again under Python.
    assert system.count("- pandas") == 1 and "- pandas (in 1 job, belongs to Python)" in system
    assert "- Docker (in 1 job)" in system
    assert messages == [{"role": "user", "content": "Recommend changes"}]


def test_the_dictionary_cant_chat(client):
    res = client.post("/api/ai/chat", json={"provider": "none", "messages": [{"role": "user", "content": "hi"}]})
    assert res.status_code == 422


def test_skills_are_items_in_the_tree(client):
    target(client, text="Requirements\n- Python and pandas")
    langs = _groups(client)["Programming languages"]
    skills = {s["name"]: s for s in client.get("/api/skills").json()}
    assert skills["Python"]["jobs"] == 1 and skills["Python"]["group_id"] == langs["id"]
    # Added by hand: next to Python, at the same level.
    skills = {s["name"]: s for s in client.post("/api/skills", json={"name": " Go ", "group_id": langs["id"]}).json()}
    assert skills["Go"]["group_id"] == langs["id"] and skills["Go"]["placed"] and skills["Go"]["jobs"] == 0
    # Dragged under another skill.
    client.patch(f"/api/skills/{skills['pandas']['id']}", json={"group_id": langs["id"], "parent_id": skills["Go"]["id"]})
    assert next(s for s in client.get("/api/skills").json() if s["name"] == "pandas")["parent_id"] == skills["Go"]["id"]
    assert "Go" not in {s["name"] for s in client.delete(f"/api/skills/{skills['Go']['id']}").json()}


def test_removing_a_skill_takes_it_off_its_jobs_for_good(client):
    job, _ = target(client, text="Requirements\n- Python and pandas")
    python = next(s for s in client.get("/api/skills").json() if s["name"] == "Python")
    rows = {s["name"]: s for s in client.delete(f"/api/skills/{python['id']}").json()}
    assert rows["Python"]["jobs"] == 0 and not rows["Python"]["placed"] and rows["Python"]["group_id"] is None
    assert rows["pandas"]["parent_id"] is None
    assert "Python" not in {r["name"] for r in client.get(f"/api/jobs/{job['id']}").json()["requirements"]}
    # Reading the posting again doesn't bring it back.
    client.post(f"/api/jobs/{job['id']}/extract")
    assert "Python" not in {r["name"] for r in client.get(f"/api/jobs/{job['id']}").json()["requirements"]}


def test_the_model_learns_a_group_from_its_skills(client):
    search = next(g for g in client.post("/api/skill-groups", json={"name": "Search"}).json() if g["name"] == "Search")
    client.post("/api/skills", json={"name": "Elasticsearch", "group_id": search["id"]})
    with client.app.state.sessionmaker() as session:
        tree = extraction.Tree.load(session)
    assert next(g for g in tree.groups if g.path == "Search").description == "Includes: Elasticsearch"


def test_renaming_a_skill_keeps_finding_it_under_the_old_name(client):
    job, _ = target(client, text="Requirements\n- PyTorch and SQL")
    rows = {s["name"]: s for s in client.get("/api/skills").json()}
    torch = rows["PyTorch"]
    res = client.patch(f"/api/skills/{torch['id']}", json={"name": "Torch", "description": "Deep learning framework"})
    assert res.json()["name"] == "Torch" and res.json()["description"] == "Deep learning framework"
    # A posting that says PyTorch lands on the renamed skill, not a new one.
    other, _ = target(client, title="ML Engineer", text="Requirements\n- PyTorch")
    names = [s["name"] for s in client.get("/api/skills").json()]
    assert "Torch" in names and "PyTorch" not in names
    assert {r["name"] for r in client.get(f"/api/jobs/{other['id']}").json()["requirements"]} == {"Torch"}
    # Two skills can't share a name.
    assert client.patch(f"/api/skills/{torch['id']}", json={"name": "sql"}).status_code == 409
