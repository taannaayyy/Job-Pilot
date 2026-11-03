import json
import os
import stat
import subprocess
import sys

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from jobpilot import ai, taxonomy
from jobpilot.main import create_app
from jobpilot import skills


# ---- Through the API


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "test.db")
    c = TestClient(app, base_url="http://127.0.0.1")
    c.put("/api/ai/settings", json={"provider": "none"})  # never reach a real model in tests
    c.app = app
    return c


def target(client, title="AI Engineer", group="AI Engineer (now)", connect=("Python", "SQL"), nice=()):
    """A target job of the role group, connected by hand to the skills named."""
    group_id = next((g["id"] for g in client.get("/api/role-groups").json() if g["name"] == group), None)
    if group_id is None:
        group_id = client.post("/api/role-groups", json={"name": group}).json()["id"]
    job = client.post("/api/jobs", json={"company": "Acme AI", "title": title}).json()
    res = client.patch(f"/api/jobs/{job['id']}", json={"raw_text": "Requirements\n- Python", "target_group_id": group_id})
    assert res.status_code == 200, res.text
    for name in connect:
        importance = "nice" if name in nice else "must"
        res = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": name, "importance": importance})
        assert res.status_code == 201, res.text
    return client.get(f"/api/jobs/{job['id']}").json(), group_id


def _under(client, parent, *names):
    """Grows the starting tree: the skills, under the node named parent."""
    for name in names:
        res = client.post("/api/skills", json={"name": name, "parent_id": _skills(client)[parent]["id"]})
        assert res.status_code == 201, res.text


def _skills(client):
    return {s["name"]: s for s in client.get("/api/skills").json()}


def test_becoming_a_target_reads_nothing(client):
    job, group_id = target(client, connect=())
    assert job["requirements"] == [] and job["raw_text"] == "Requirements\n- Python"
    assert not any(k.startswith("extract") for k in job)
    assert client.get("/api/role-groups").json() == [{"id": group_id, "name": "AI Engineer (now)", "job_count": 1}]
    assert set(client.get("/api/skill-gap").json()) == {"targets", "coverage", "skills", "postings"}


def test_gap_list_counts_jobs_and_coverage(client):
    target(client, "AI Engineer")
    _, group_id = target(client, "ML Engineer", connect=("Python", "Kubernetes", "Go"), nice=("Go",))
    gap = client.get("/api/skill-gap", params={"group_id": group_id}).json()
    assert gap["targets"] == 2
    rows = {s["name"]: s for s in gap["skills"]}
    assert (rows["Python"]["jobs"], rows["Python"]["must"]) == (2, 2)
    assert (rows["Go"]["nice"], rows["Go"]["placed"]) == (1, False)  # not in the tree: Unsorted
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


def test_a_skills_connection_to_a_posting(client):
    job, _ = target(client, connect=())
    docker = _skills(client)["Docker"]
    client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "Docker", "evidence": " 3+ years with Docker "})
    detail = client.get(f"/api/skills/{docker['id']}").json()
    assert [(j["title"], j["evidence"], j["importance"]) for j in detail["jobs"]] == [("AI Engineer", "3+ years with Docker", "must")]
    # From the skill's side, the note and importance can change.
    detail = client.patch(f"/api/skills/{docker['id']}/jobs/{job['id']}", json={"evidence": "Docker Compose", "importance": "nice"}).json()
    assert [(j["evidence"], j["importance"]) for j in detail["jobs"]] == [("Docker Compose", "nice")]
    # It counts on Docker; the node above it only adds it up.
    rows = {s["name"]: s for s in client.get("/api/skill-gap").json()["skills"]}
    assert rows["Docker"]["job_ids"] == [job["id"]] and rows["DevOps"]["job_ids"] == []
    assert [r["name"] for r in client.get(f"/api/jobs/{job['id']}").json()["requirements"]] == ["Docker"]
    # Disconnected.
    assert client.delete(f"/api/skills/{docker['id']}/jobs/{job['id']}").json()["jobs"] == []
    assert client.get(f"/api/jobs/{job['id']}").json()["requirements"] == []


def test_a_group_is_never_asked_for(client):
    job, _ = target(client, connect=())
    # A group only organizes.
    assert client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "cloud"}).status_code == 422


def test_only_targets_count(client):
    target(client)
    plain = client.post("/api/jobs", json={"company": "Beta", "title": "Data Scientist"}).json()
    client.post(f"/api/jobs/{plain['id']}/requirements", json={"name": "Git"})
    rows = {s["name"]: s for s in client.get("/api/skill-gap").json()["skills"]}
    assert rows["Git"]["jobs"] == 0 and rows["Python"]["jobs"] == 1


def test_a_jobs_skills_from_its_own_side(client):
    job, _ = target(client, connect=("Python",))
    job = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "Ranking models", "importance": "nice"}).json()
    assert {r["name"]: r["importance"] for r in job["requirements"]} == {"Python": "must", "Ranking models": "nice"}
    python = next(r for r in job["requirements"] if r["name"] == "Python")
    job = client.patch(f"/api/jobs/{job['id']}/requirements/{python['id']}", json={"importance": "nice"}).json()
    assert next(r for r in job["requirements"] if r["name"] == "Python")["importance"] == "nice"
    job = client.delete(f"/api/jobs/{job['id']}/requirements/{python['id']}").json()
    assert [r["name"] for r in job["requirements"]] == ["Ranking models"]
    # Added again by name: the same skill as before.
    job = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "python"}).json()
    assert {r["name"] for r in job["requirements"]} == {"Python", "Ranking models"}
    assert not _skills(client)["Ranking models"]["placed"]  # a name the tree doesn't have: Unsorted


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


# ---- AI settings (for writing descriptions)


def test_api_keys_are_never_sent_back(client, tmp_path):
    res = client.put("/api/ai/settings", json={"provider": "anthropic", "providers": {"anthropic": {"api_key": "sk-secret", "model": "claude-haiku-5-5"}}})
    body = res.json()
    assert "sk-secret" not in res.text
    assert body["providers"]["anthropic"] == {"model": "claude-haiku-5-5", "has_key": True}
    path = tmp_path / "ai-settings.json"
    assert json.loads(path.read_text())["providers"]["anthropic"]["api_key"] == "sk-secret"
    # Only its owner can read it. Windows has no such mode bits: %APPDATA% is private to the user already.
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    # Leaving the key out keeps it; an empty key removes it.
    client.put("/api/ai/settings", json={"provider": "ollama", "providers": {"anthropic": {"model": "claude-opus-5-5"}}})
    assert client.get("/api/ai/settings").json()["providers"]["anthropic"]["has_key"] is True
    client.put("/api/ai/settings", json={"provider": "ollama", "providers": {"anthropic": {"api_key": ""}}})
    assert client.get("/api/ai/settings").json()["providers"]["anthropic"]["has_key"] is False


def test_ai_settings_only_answer_the_app(tmp_path):
    other = TestClient(create_app(tmp_path / "t.db"), base_url="http://evil.example")
    assert other.get("/api/ai/settings").status_code == 403


class ReadyModel(ai.Provider):
    name = "ollama"

    def chat(self, system, messages):
        return " Ready. "


def test_testing_a_model_asks_it_for_a_short_answer(client, monkeypatch):
    monkeypatch.setitem(ai._CLASSES, "ollama", ReadyModel)
    res = client.post("/api/ai/test", json={"provider": "ollama"}).json()
    assert (res["used"], res["reply"]) == ("Ollama", "Ready.")
    assert client.post("/api/ai/test", json={"provider": "none"}).status_code == 422


# ---- Providers, with fake servers


def test_ollama_uses_the_first_installed_model(monkeypatch):
    calls = []

    def fake(url, body=None, headers=None, timeout=0):
        calls.append((url, body))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:3b"}, {"name": "bge-m3:latest"}]}
        if url.endswith("/api/show"):
            return {"capabilities": ["embedding"] if body["model"].startswith("bge") else ["completion"]}
        return {"message": {"content": "Move Docker."}}

    monkeypatch.setattr(ai, "_http_json", fake)
    ollama = ai.Ollama({"base_url": "http://localhost:11434", "model": ""})
    assert ollama.models() == ["llama3.2:3b", "qwen2.5:3b"]  # not the embedding model
    assert ollama.chat("system", [{"role": "user", "content": "hi"}]) == "Move Docker."
    assert calls[-1][1]["model"] == "llama3.2:3b"
    assert calls[-1][1]["messages"][0] == {"role": "system", "content": "system"}


def test_ollama_not_running(monkeypatch):
    def fake(*a, **k):
        raise ConnectionRefusedError

    monkeypatch.setattr(ai, "_http_json", fake)
    with pytest.raises(ai.AIError, match="isn't running"):
        ai.Ollama({"model": "x"}).chat("system", [{"role": "user", "content": "hi"}])


def test_openai_compatible_chat(monkeypatch):
    bodies = []

    def fake(url, body=None, headers=None, timeout=0):
        bodies.append((url, body, headers))
        return {"choices": [{"message": {"content": "Sure."}}]}

    monkeypatch.setattr(ai, "_http_json", fake)
    provider = ai.OpenAICompatible({"base_url": "https://api.groq.com/openai/v1/", "model": "llama", "api_key": "k"})
    assert provider.chat("system", [{"role": "user", "content": "hi"}]) == "Sure."
    url, body, headers = bodies[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions" and body["model"] == "llama"
    assert headers == {"Authorization": "Bearer k"}
    with pytest.raises(ai.AIError, match="Choose a model"):
        ai.OpenAICompatible({"model": ""}).chat("system", [{"role": "user", "content": "hi"}])


def _claude(monkeypatch, handler):
    def client(self):
        return anthropic.Anthropic(api_key="k", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)

    monkeypatch.setattr(ai.Claude, "_client", client)
    return ai.Claude({"model": "claude-haiku-5-5", "api_key": "k"})


def test_claude_chat(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": "Move Docker."}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        })

    assert _claude(monkeypatch, handler).chat("system", [{"role": "user", "content": "hi"}]) == "Move Docker."
    assert seen["model"] == "claude-haiku-5-5" and seen["system"] == "system"


def test_claude_wrong_key(monkeypatch):
    def handler(request):
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})

    with pytest.raises(ai.AIError, match="key is wrong"):
        _claude(monkeypatch, handler).chat("system", [{"role": "user", "content": "hi"}])


def test_claude_needs_a_key():
    with pytest.raises(ai.AIError, match="Paste your Claude API key"):
        ai.Claude({"model": "claude-haiku-5-5", "api_key": ""}).chat("system", [{"role": "user", "content": "hi"}])


# ---- Claude Code


HI = [{"role": "user", "content": "hi"}]


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


def test_claude_code_chat(monkeypatch, claude_bin):
    calls = _fake_cli(monkeypatch, json.dumps({"type": "result", "is_error": False, "result": "Move Docker."}))
    reply = ai.ClaudeCode({"path": claude_bin, "model": "sonnet"}).chat("the tree", [
        {"role": "user", "content": "Recommend"}, {"role": "assistant", "content": "Move X"}, {"role": "user", "content": "Why?"},
    ])
    assert reply == "Move Docker."
    cmd = calls[0]["cmd"]
    # It can only read what it's given: no tools, no MCP servers, no settings, no saved sessions.
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert {"-p", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(cmd)
    assert cmd[cmd.index("--model") + 1] == "sonnet" and cmd[cmd.index("--system-prompt") + 1] == "the tree"
    # One prompt at a time: the conversation so far goes with it.
    assert "User: Recommend" in calls[0]["prompt"] and "You: Move X" in calls[0]["prompt"]
    assert calls[0]["prompt"].endswith("Why?")
    # Run in an empty folder of its own, not the app's or a project's.
    assert "jobpilot-" in calls[0]["cwd"] and not os.path.exists(calls[0]["cwd"])


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
        ai.ClaudeCode({"path": claude_bin}).chat("system", HI)


def test_claude_code_crash_and_timeout(monkeypatch, claude_bin):
    _fake_cli(monkeypatch, stdout="", stderr="segfault", code=139)
    with pytest.raises(ai.AIError, match="segfault"):
        ai.ClaudeCode({"path": claude_bin}).chat("system", HI)
    _fake_cli(monkeypatch, error=subprocess.TimeoutExpired("claude", 1))
    with pytest.raises(ai.AIError, match="too long"):
        ai.ClaudeCode({"path": claude_bin}).chat("system", HI)


def test_claude_code_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)
    monkeypatch.setattr(ai, "_CLAUDE_PLACES", (str(tmp_path / "nope"),))
    with pytest.raises(ai.AIError, match="isn't installed"):
        ai.ClaudeCode({}).models()
    with pytest.raises(ai.AIError, match="no Claude Code at"):
        ai.ClaudeCode({"path": str(tmp_path / "missing")}).chat("system", HI)


def test_claude_code_is_found_outside_path(monkeypatch, claude_bin):
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)  # an app opened from Finder has a short PATH
    monkeypatch.setattr(ai, "_CLAUDE_PLACES", (claude_bin,))
    assert ai.ClaudeCode({}).binary() == claude_bin


def test_claude_code_settings_round_trip(client):
    body = client.put("/api/ai/settings", json={
        "provider": "claude_code", "providers": {"claude_code": {"path": "~/bin/claude", "model": "sonnet"}},
    }).json()
    assert body["provider"] == "claude_code"
    assert body["providers"]["claude_code"] == {"path": "~/bin/claude", "model": "sonnet", "effort": "medium"}
    assert client.put("/api/ai/settings", json={
        "provider": "claude_code", "providers": {"claude_code": {"effort": "extreme"}},
    }).status_code == 422


def test_claude_code_defaults_to_opus_at_medium_effort(monkeypatch, tmp_path, claude_bin):
    monkeypatch.setattr(ai.shutil, "which", lambda _: claude_bin)
    calls = _fake_cli(monkeypatch, json.dumps({"is_error": False, "result": "ok"}))
    ai.Settings(tmp_path / "s.json").provider().chat("system", HI)
    cmd = calls[0]["cmd"]
    assert (cmd[cmd.index("--model") + 1], cmd[cmd.index("--effort") + 1]) == ("claude-opus-5-5", "medium")
    assert ai.Settings(tmp_path / "s.json").provider().describe() == "Claude Code Opus 5.5, medium effort"


def test_claude_code_effort_is_passed_on(monkeypatch, claude_bin):
    calls = _fake_cli(monkeypatch, json.dumps({"is_error": False, "result": "ok"}))
    ai.ClaudeCode({"path": claude_bin, "model": "claude-haiku-5-5", "effort": "max"}).chat("system", HI)
    assert calls[0]["cmd"][calls[0]["cmd"].index("--effort") + 1] == "max"
    ai.ClaudeCode({"path": claude_bin, "model": "", "effort": ""}).chat("system", HI)  # Claude Code's own defaults
    assert "--effort" not in calls[1]["cmd"] and "--model" not in calls[1]["cmd"]


def test_default_is_claude_code_when_installed(monkeypatch, tmp_path, claude_bin):
    monkeypatch.setattr(ai.shutil, "which", lambda _: claude_bin)
    assert ai.Settings(tmp_path / "a.json").load()["provider"] == "claude_code"
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)
    monkeypatch.setattr(ai, "_CLAUDE_PLACES", ())
    assert ai.Settings(tmp_path / "b.json").load()["provider"] == "ollama"


# ---- The tree


def test_the_starting_tree_is_the_users():
    nodes = list(taxonomy.nodes())
    assert nodes[0] == ("Technologies", None, 0, True)  # a group: only organizes
    assert ("Python", "Programming languages", 0, False) in nodes and ("AWS", "Cloud", 0, False) in nodes
    assert ("Domain knowledge", None, 1, True) in nodes and ("Soft skills", None, 3, True) in nodes
    # A general skeleton for any field: the user grows it from their postings.
    assert not {"Machine learning", "YOLO", "Pharmaceuticals", "Turkish"} & {n for n, _, _, _ in nodes}
    # No two nodes share a name.
    assert len({skills.skill_key(n) for n, _, _, _ in nodes}) == len(nodes)


def test_the_tree_starts_as_designed(client):
    rows = _skills(client)
    assert rows["Technologies"]["parent_id"] is None and rows["Technologies"]["placed"]
    assert rows["Python"]["parent_id"] == rows["Programming languages"]["id"]
    assert rows["Programming languages"]["parent_id"] == rows["Technologies"]["id"]
    assert rows["AWS"]["parent_id"] == rows["Cloud"]["id"]
    assert [rows[n]["position"] for n in ("Python", "JavaScript", "Java")] == [0, 1, 2]
    # In order: the tree's own order, from the top.
    assert client.get("/api/skills").json()[0]["name"] == "Technologies"


def test_postings_count_on_the_tree_and_the_rest_waits_in_unsorted(client):
    _under(client, "Python", "pandas")
    target(client, connect=("pandas", "SQL", "Keras"))
    gap = client.get("/api/skill-gap").json()
    rows = {s["name"]: s for s in gap["skills"]}
    assert rows["pandas"]["parent_id"] == rows["Python"]["id"] and rows["pandas"]["jobs"] == 1
    # The whole tree is there, asked for or not.
    assert rows["Python"]["jobs"] == 0 and rows["Technologies"]["jobs"] == 0 and "Git" in rows
    # Not in the tree: Unsorted, until the user places it.
    assert not rows["Keras"]["placed"] and rows["Keras"]["parent_id"] is None


def test_adding_moving_and_reordering_nodes(client):
    rows = _skills(client)
    cloud = rows["Cloud"]
    rows = {s["name"]: s for s in client.post("/api/skills", json={"name": " Oracle Cloud ", "parent_id": cloud["id"]}).json()}
    assert rows["Oracle Cloud"]["parent_id"] == cloud["id"] and rows["Oracle Cloud"]["position"] == 3
    client.patch(f"/api/skills/{rows['Oracle Cloud']['id']}", json={"index": 0})
    rows = _skills(client)
    assert [rows[n]["position"] for n in ("Oracle Cloud", "AWS", "Azure", "Google Cloud")] == [0, 1, 2, 3]
    # Dragged under another node; the ones it left close the gap.
    client.patch(f"/api/skills/{rows['Azure']['id']}", json={"parent_id": rows["Background"]["id"], "index": 1})
    rows = _skills(client)
    assert rows["Azure"]["parent_id"] == rows["Background"]["id"] and rows["Azure"]["position"] == 1
    assert rows["Education"]["position"] == 2 and rows["Google Cloud"]["position"] == 2
    # Out to the top level, at the end.
    client.patch(f"/api/skills/{rows['Azure']['id']}", json={"parent_id": None})
    rows = _skills(client)
    assert rows["Azure"]["parent_id"] is None and rows["Azure"]["position"] == 4
    client.patch(f"/api/skills/{rows['Azure']['id']}", json={"description": "Microsoft's cloud"})
    assert _skills(client)["Azure"]["description"] == "Microsoft's cloud"


def test_a_skill_cant_be_under_its_own_child(client):
    _under(client, "Python", "pandas")
    rows = _skills(client)
    pandas, python = rows["pandas"], rows["Python"]
    assert client.patch(f"/api/skills/{python['id']}", json={"parent_id": pandas["id"]}).status_code == 422
    assert client.patch(f"/api/skills/{python['id']}", json={"parent_id": python["id"]}).status_code == 422


def test_placing_a_skill_from_unsorted_and_back(client):
    _under(client, "Python", "pandas", "NumPy")
    target(client, connect=("Keras",))
    rows = _skills(client)
    client.patch(f"/api/skills/{rows['Keras']['id']}", json={"parent_id": rows["Python"]["id"]})
    rows = _skills(client)
    assert rows["Keras"]["placed"] and rows["Keras"]["parent_id"] == rows["Python"]["id"]
    assert rows["Keras"]["position"] == 2  # after the two libraries already there
    # Back to Unsorted: its children take its place.
    client.patch(f"/api/skills/{rows['Python']['id']}", json={"placed": False})
    rows = _skills(client)
    assert not rows["Python"]["placed"] and rows["pandas"]["parent_id"] == rows["Programming languages"]["id"]
    assert [rows[n]["position"] for n in ("pandas", "NumPy", "Keras", "JavaScript", "SQL")] == [0, 1, 2, 3, 5]


def test_removing_a_skill_takes_it_off_its_jobs(client):
    _under(client, "Python", "pandas")
    job, _ = target(client, connect=("Python", "pandas"))
    rows = _skills(client)
    rows = {s["name"]: s for s in client.delete(f"/api/skills/{rows['Python']['id']}").json()}
    assert "Python" not in rows
    assert rows["pandas"]["parent_id"] == rows["Programming languages"]["id"]  # moved up
    assert [r["name"] for r in client.get(f"/api/jobs/{job['id']}").json()["requirements"]] == ["pandas"]


def test_adding_a_group(client):
    rows = _skills(client)
    assert rows["Cloud"]["is_group"] and not rows["Python"]["is_group"]
    rows = {s["name"]: s for s in client.post("/api/skills", json={
        "name": "Search", "parent_id": rows["Technologies"]["id"], "is_group": True, "description": "Search engines"}).json()}
    assert rows["Search"]["is_group"] and rows["Search"]["description"] == "Search engines"
    client.post("/api/skills", json={"name": "Elasticsearch", "parent_id": rows["Search"]["id"]})
    assert _skills(client)["Elasticsearch"]["parent_id"] == rows["Search"]["id"]
    # A group can't take the name of a skill.
    assert client.post("/api/skills", json={"name": "python", "is_group": True}).status_code == 409


def test_renaming_a_skill_keeps_finding_it_under_the_old_name(client):
    target(client, connect=("PyTorch", "SQL"))
    torch = _skills(client)["PyTorch"]
    res = client.patch(f"/api/skills/{torch['id']}", json={"name": "Torch", "description": "Deep learning framework"})
    assert res.json()["name"] == "Torch" and res.json()["description"] == "Deep learning framework"
    # Added by its old name: the renamed skill, not a new one.
    other, _ = target(client, title="ML Engineer", connect=("PyTorch",))
    names = [s["name"] for s in client.get("/api/skills").json()]
    assert "Torch" in names and "PyTorch" not in names
    assert {r["name"] for r in other["requirements"]} == {"Torch"}
    # Two skills can't share a name.
    assert client.patch(f"/api/skills/{torch['id']}", json={"name": "sql"}).status_code == 409


def test_the_gap_says_which_postings_ask_for_each_skill(client):
    first, group = target(client, connect=("Python", "SQL"))
    second, _ = target(client, title="ML Engineer", connect=("Python",))
    gap = client.get(f"/api/skill-gap?group_id={group}").json()
    rows = {s["name"]: s for s in gap["skills"]}
    assert sorted(rows["Python"]["job_ids"]) == sorted([first["id"], second["id"]])
    assert rows["SQL"]["job_ids"] == [first["id"]]
    assert {p["title"] for p in gap["postings"]} == {"AI Engineer", "ML Engineer"}


def test_upgrading_keeps_skills_and_their_postings(tmp_path):
    """An old database: the skills it had keep their id in the tree, the rest wait in Unsorted."""
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import jobpilot

    db = tmp_path / "old.db"
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(jobpilot.__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "f2a6c8e1b4d9")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO skill (id, name, key, category, plan_note, created_at, group_locked, description, old_keys) "
                "VALUES (7, 'Python', 'python', 'tech', '', '2026-01-01', 1, '', ''), "
                "(8, 'Ranking', 'ranking', 'tech', '', '2026-01-01', 0, '', '')")
    con.commit()
    command.upgrade(cfg, "head")
    rows = {r[0]: r[1:] for r in con.execute(
        "SELECT s.name, s.id, s.placed, s.is_group, p.name FROM skill s LEFT JOIN skill p ON p.id = s.parent_id")}
    assert rows["Python"] == (7, 1, 0, "Programming languages")
    assert rows["Ranking"] == (8, 0, 0, None)
    assert rows["Docker"][1:] == (1, 0, "DevOps") and rows["Cloud"][2] == 1
    assert "extraction_status" not in {r[1] for r in con.execute("PRAGMA table_info(job)")}


# ---- Descriptions written by the AI


class WritingModel(ai.Provider):
    name = "ollama"

    def chat(self, system, messages):
        self.seen = (system, messages)
        return ' "Amazon\'s serverless\n compute service." '


def _skill(client, name):
    return next(s for s in client.get("/api/skills").json() if s["name"] == name)


def test_describe_sends_the_place_in_the_tree(client, monkeypatch):
    model = WritingModel({})
    monkeypatch.setattr(ai.Settings, "provider", lambda self, name=None, overrides=None: model)
    aws = _skill(client, "AWS")
    res = client.post("/api/ai/describe", json={"name": "Lambda", "parent_id": aws["id"]})
    assert res.json() == {"description": "Amazon's serverless compute service.", "used": "Ollama"}
    prompt = model.seen[1][0]["content"]
    assert prompt.startswith("Skill: Lambda\n") and "Technologies › Cloud › AWS" in prompt
    assert "Under it" not in prompt
    # Editing a node: what is under it goes too.
    cloud = _skill(client, "Cloud")
    client.post("/api/ai/describe", json={"name": "Cloud", "is_group": True, "parent_id": cloud["parent_id"], "skill_id": cloud["id"]})
    assert model.seen[1][0]["content"].startswith("Group: Cloud\n")
    assert "Under it: AWS, Azure, Google Cloud" in model.seen[1][0]["content"]


def test_no_ai_cant_describe(client):
    res = client.post("/api/ai/describe", json={"name": "YOLO"})
    assert res.status_code == 422


def test_a_skill_picked_from_the_description_keeps_the_words(client):
    job, _ = target(client, connect=())
    job = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "YOLO", "evidence": " YOLOv8\n models ", "evidence_at": 40}).json()
    assert [(r["name"], r["evidence"], r["evidence_at"]) for r in job["requirements"]] == [("YOLO", "YOLOv8 models", 40)]
    # Added again without words: the ones it had stay.
    job = client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "yolo", "importance": "nice"}).json()
    assert [(r["evidence"], r["evidence_at"], r["importance"]) for r in job["requirements"]] == [("YOLOv8 models", 40, "nice")]


def test_words_highlighted_in_the_description_are_not_skills(client):
    job = client.post("/api/jobs", json={"company": "Acme AI", "title": "AI Engineer"}).json()
    assert job["highlights"] == []
    res = client.patch(f"/api/jobs/{job['id']}", json={"raw_text": "We ship models weekly.", "highlights": [{"words": "ship models", "at": 3}]})
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["highlights"] == [{"words": "ship models", "at": 3, "note": ""}] and job["requirements"] == []
    # Other changes leave them; null doesn't erase them, an empty list does.
    assert client.patch(f"/api/jobs/{job['id']}", json={"notes": "x", "highlights": None}).json()["highlights"] == job["highlights"]
    assert client.patch(f"/api/jobs/{job['id']}", json={"highlights": []}).json()["highlights"] == []


def test_notes_on_highlights_and_on_skills_picked_from_the_description(client):
    job, _ = target(client, connect=("Python",))
    job = client.patch(f"/api/jobs/{job['id']}", json={"highlights": [{"words": "Python", "at": 15, "note": "Ask about it"}]}).json()
    assert job["highlights"][0]["note"] == "Ask about it"
    req = job["requirements"][0]
    assert req["note"] == ""
    job = client.patch(f"/api/jobs/{job['id']}/requirements/{req['id']}", json={"note": " Mostly pandas \n"}).json()
    assert (job["requirements"][0]["note"], job["requirements"][0]["importance"]) == ("Mostly pandas", "must")
    # Changing how much it matters leaves the note.
    job = client.patch(f"/api/jobs/{job['id']}/requirements/{req['id']}", json={"importance": "nice"}).json()
    assert (job["requirements"][0]["note"], job["requirements"][0]["importance"]) == ("Mostly pandas", "nice")


def test_the_gap_says_which_words_a_skill_was_picked_from(client):
    job, _ = target(client, connect=())
    client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "Keras", "evidence": "Keras or TensorFlow"})
    row = next(s for s in client.get("/api/skill-gap").json()["skills"] if s["name"] == "Keras")
    assert row["placed"] is False and row["quotes"] == ["Keras or TensorFlow"]


def test_a_removed_skill_comes_back_with_undo(client):
    _under(client, "Python", "pandas", "NumPy")
    job, _ = target(client, connect=())
    client.post(f"/api/jobs/{job['id']}/requirements", json={"name": "Python", "importance": "nice", "evidence": "Python", "evidence_at": 3})
    rows = _skills(client)
    python = rows["Python"]
    client.patch(f"/api/skills/{python['id']}", json={"description": "A language", "mark": "have"})
    client.delete(f"/api/skills/{python['id']}")
    assert "Python" not in _skills(client)
    res = client.post("/api/skills/undo-remove")
    assert res.status_code == 200 and res.json()["name"] == "Python"
    rows = _skills(client)
    # The same skill, in its place, with what was under it and its job.
    assert rows["Python"]["id"] == python["id"] and rows["Python"]["parent_id"] == python["parent_id"]
    assert rows["Python"]["position"] == 0 and rows["Python"]["description"] == "A language"
    assert [rows[n]["parent_id"] for n in ("pandas", "NumPy")] == [python["id"]] * 2
    assert [rows[n]["position"] for n in ("pandas", "NumPy", "JavaScript")] == [0, 1, 1]
    req = next(r for r in client.get(f"/api/jobs/{job['id']}").json()["requirements"] if r["name"] == "Python")
    assert (req["importance"], req["evidence"], req["evidence_at"], req["mark"]) == ("nice", "Python", 3, "have")
    # Nothing left to undo.
    assert client.post("/api/skills/undo-remove").status_code == 404


def test_undo_brings_back_the_last_removed_first(client):
    rows = _skills(client)
    client.delete(f"/api/skills/{rows['AWS']['id']}")
    client.delete(f"/api/skills/{rows['Git']['id']}")
    assert client.post("/api/skills/undo-remove").json()["name"] == "Git"
    assert client.post("/api/skills/undo-remove").json()["name"] == "AWS"
    assert _skills(client)["AWS"]["parent_id"] == rows["Cloud"]["id"]


def test_undo_skips_a_skill_added_again(client):
    rows = _skills(client)
    client.delete(f"/api/skills/{rows['Git']['id']}")
    client.post("/api/skills", json={"name": "git", "parent_id": rows["DevOps"]["id"]})
    assert client.post("/api/skills/undo-remove").status_code == 409
    assert client.post("/api/skills/undo-remove").status_code == 404


def test_a_skill_is_a_concept_or_a_tool(client):
    rows = _skills(client)
    assert rows["Docker"]["is_tool"] and rows["Python"]["is_tool"] and not rows["Software testing"]["is_tool"]
    assert not rows["Cloud"]["is_tool"]  # a group is neither
    rows = {s["name"]: s for s in client.post("/api/skills", json={
        "name": "Kubernetes", "parent_id": rows["DevOps"]["id"], "is_tool": True}).json()}
    assert rows["Kubernetes"]["is_tool"]
    client.patch(f"/api/skills/{rows['Software testing']['id']}", json={"is_tool": True})
    assert _skills(client)["Software testing"]["is_tool"]
    # A group can't be a tool.
    client.patch(f"/api/skills/{rows['Cloud']['id']}", json={"is_tool": True})
    assert not _skills(client)["Cloud"]["is_tool"]


def test_claude_code_from_npm_on_windows_runs_its_node_script(tmp_path, monkeypatch):
    """npm installs claude.cmd on Windows; it runs through cmd.exe, so the Node script is started instead."""
    assert ai._launcher("/usr/local/bin/claude") == ["/usr/local/bin/claude"]
    folder = tmp_path / "npm"
    script = folder / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("")
    (folder / "node.exe").write_text("")
    assert ai._launcher(str(folder / "claude.cmd")) == [str(folder / "node.exe"), str(script)]
    # No Node.js anywhere: says so.
    (folder / "node.exe").unlink()
    monkeypatch.setattr(ai.shutil, "which", lambda name: None)
    with pytest.raises(ai.AIError, match="Node.js"):
        ai._launcher(str(folder / "claude.cmd"))
