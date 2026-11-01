import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobpilot import capture, system
from jobpilot.main import create_app
from jobpilot.system import generic, macos, windows


def test_every_system_module_has_the_same_functions():
    assert set(macos.__all__) == set(generic.__all__) == set(windows.__all__)
    for name in macos.__all__:
        for module in (macos, generic, windows):
            assert callable(getattr(module, name)), (module.__name__, name)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_keeps_the_data_where_it_was():
    assert system.data_dir is macos.data_dir
    assert system.data_dir() == Path.home() / "Library" / "Application Support" / "JobPilot"


def test_windows_data_goes_to_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert windows.data_dir() == tmp_path / "JobPilot"


def test_windows_finds_who_holds_the_port():
    netstat = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1012
  TCP    127.0.0.1:18765        0.0.0.0:0              LISTENING       77
  TCP    127.0.0.1:8765         127.0.0.1:52011        ESTABLISHED     5000
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242
  TCP    [::]:8765              [::]:0                 LISTENING       4243
"""
    assert windows.listening_pid(netstat, 8765) == 4242  # not 18765, not the open connection
    assert windows.listening_pid(netstat, 9999) is None
    assert windows.image_name('"Docker Desktop.exe","4242","Console","1","120,544 K"\r\n') == "Docker Desktop"
    assert windows.image_name("INFO: No tasks are running which match the specified criteria.") is None


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
