import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobpilot import capture, system
from jobpilot.main import create_app
from jobpilot.system import generic, macos


def test_every_system_module_has_the_same_functions():
    assert set(macos.__all__) == set(generic.__all__)
    for name in macos.__all__:
        assert callable(getattr(macos, name)) and callable(getattr(generic, name)), name


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_keeps_the_data_where_it_was():
    assert system.data_dir is macos.data_dir
    assert system.data_dir() == Path.home() / "Library" / "Application Support" / "JobPilot"


def test_windows_data_goes_to_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert generic.data_dir() == tmp_path / "JobPilot"


def test_open_chrome_copies_the_extension_and_its_location(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(capture, "EXTENSION_INSTALL_DIR", tmp_path / "Chrome Extension")
    monkeypatch.setattr(capture.system, "chrome_installed", lambda: True)
    monkeypatch.setattr(capture.system, "copy_to_clipboard", lambda text: calls.append(("clipboard", text)))
    monkeypatch.setattr(capture.system, "open_in_chrome", lambda url: calls.append(("chrome", url)))
    client = TestClient(create_app(tmp_path / "test.db"), base_url="http://127.0.0.1")

    res = client.post("/api/extension/install", json={})
    assert res.status_code == 200, res.text
    folder = tmp_path / "Chrome Extension"
    assert (folder / "manifest.json").is_file()
    assert calls == [("clipboard", str(folder)), ("chrome", "chrome://extensions/")]

    monkeypatch.setattr(capture.system, "chrome_installed", lambda: False)
    assert client.post("/api/extension/install", json={}).status_code == 404
