import json
import os
import runpy

import pytest

from dash_init import remote
from dash_init.cli import init
from dash_init.remote import RemoteSpec, parse_spec


# --------------------------------------------------------------------------- #
# offline: a fake GitHub served from a dict
# --------------------------------------------------------------------------- #

FAKE_TREE = {
    "tpl/app.py": b"from dash import Dash\napp = Dash(__name__)\nserver = app.server\n",
    "tpl/requirements.txt": b"dash>=4.4.1\n# comment\npandas>=3.0.5\n",
    "tpl/pyproject.toml": b'[project]\nname = "hub-original"\nversion = "1.0"\n',
    "tpl/pages/home.py": b"# page\n",
    "tpl/screenshots/x.png": b"PNG",
    "tpl/__pycache__/app.cpython-311.pyc": b"\x00",
    "tpl/uv.lock": b"lock",
    "tpl/.DS_Store": b"junk",
    "tpl/notebooks/scratch.ipynb": b"{}",
    "other/app.py": b"# not ours\n",
}


@pytest.fixture
def fake_github(monkeypatch):
    def get_json(url):
        if url.endswith("/repos/acme/hub"):
            return {"default_branch": "trunk"}
        assert "/git/trees/" in url, url
        return {
            "sha": "deadbeef",
            "truncated": False,
            "tree": [{"path": p, "type": "blob", "size": len(b)} for p, b in FAKE_TREE.items()],
        }

    def get_bytes(url):
        prefix = f"{remote.RAW}/acme/hub/deadbeef/"
        assert url.startswith(prefix), url
        return FAKE_TREE[url[len(prefix):]]

    monkeypatch.setattr(remote, "_get_json", get_json)
    monkeypatch.setattr(remote, "_get_bytes", get_bytes)


def test_parse_spec_builtin_is_none():
    assert parse_spec("minimal") is None


def test_parse_spec_registry_pinned():
    spec = parse_spec("kiaalap")
    assert spec.owner == "budescode" and spec.repo == "dash-templates-hub"
    assert spec.path == "dash-kiaalap"
    assert spec.ref and len(spec.ref) == 40, "registry entries must be pinned to a commit"


@pytest.mark.parametrize("arg, expected", [
    ("gh:acme/hub", RemoteSpec("acme", "hub", "", None)),
    ("gh:acme/hub/tpl", RemoteSpec("acme", "hub", "tpl", None)),
    ("gh:acme/hub/a/b/c@v1.2", RemoteSpec("acme", "hub", "a/b/c", "v1.2")),
    ("gh:acme/hub@main", RemoteSpec("acme", "hub", "", "main")),
])
def test_parse_spec_gh(arg, expected):
    assert parse_spec(arg) == expected


def test_parse_spec_gh_bad():
    with pytest.raises(SystemExit):
        parse_spec("gh:onlyowner")


def test_fetch_copies_only_subdir_without_junk(fake_github, tmp_path):
    project = init("my-app", "gh:acme/hub/tpl", tmp_path)
    got = sorted(str(p.relative_to(project)) for p in project.rglob("*") if p.is_file())
    assert got == [".gitignore", "app.py", "pages/home.py", "pyproject.toml", "requirements.txt"]


def test_configure_renames_pyproject(fake_github, tmp_path):
    project = init("my-app", "gh:acme/hub/tpl", tmp_path)
    text = (project / "pyproject.toml").read_text()
    assert 'name = "my-app"' in text and "hub-original" not in text


def test_configure_generates_pyproject_when_missing(fake_github, tmp_path, monkeypatch):
    tree = {k: v for k, v in FAKE_TREE.items() if k != "tpl/pyproject.toml"}
    monkeypatch.setitem(globals(), "FAKE_TREE", tree)
    project = init("my-app", "gh:acme/hub/tpl", tmp_path)
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads((project / "pyproject.toml").read_text())
    assert data["project"]["name"] == "my-app"
    assert data["project"]["dependencies"] == ["dash>=4.4.1", "pandas>=3.0.5"]


def test_fetch_uses_default_branch_when_no_ref(fake_github, tmp_path):
    project = init("my-app", "gh:acme/hub/tpl", tmp_path)
    assert (project / "app.py").is_file()


def test_docker_addon_works_with_remote(fake_github, tmp_path):
    project = init("my-app", "gh:acme/hub/tpl", tmp_path, docker=True)
    assert (project / "Dockerfile").is_file()


def test_failed_fetch_leaves_no_partial_project(fake_github, tmp_path, monkeypatch):
    def boom(url):
        raise OSError("network down")
    monkeypatch.setattr(remote, "_get_bytes", boom)
    with pytest.raises(SystemExit):
        init("my-app", "gh:acme/hub/tpl", tmp_path)
    assert not (tmp_path / "my-app").exists()
    assert not list(tmp_path.glob(".dash-init-*")), "staging dir must be cleaned up"


# --------------------------------------------------------------------------- #
# online: every registry template must fetch and configure (CI sets the env)
# --------------------------------------------------------------------------- #

needs_network = pytest.mark.skipif(
    not os.environ.get("DASH_INIT_NETWORK_TESTS"), reason="set DASH_INIT_NETWORK_TESTS=1"
)


@needs_network
@pytest.mark.parametrize("name", sorted(remote.registry_templates()))
def test_registry_template_fetches(name, tmp_path):
    project = init("hub-app", name, tmp_path)
    assert remote.entry_point(project), "no app.py/run.py/main.py"
    assert (project / "pyproject.toml").is_file()
    assert (project / "requirements.txt").is_file()
    assert not list(project.rglob("__pycache__")) and not (project / "screenshots").exists()


# --------------------------------------------------------------------------- #
# transient network errors are retried
# --------------------------------------------------------------------------- #

def test_get_bytes_retries_transient_errors(monkeypatch):
    import io
    import urllib.error

    calls = []

    def urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))
        return io.BytesIO(b"ok")

    monkeypatch.setattr(remote.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(remote.time, "sleep", lambda s: None)
    assert remote._get_bytes("https://example.invalid/x") == b"ok"
    assert len(calls) == 3


def test_get_bytes_does_not_retry_404(monkeypatch):
    import urllib.error

    calls = []

    def urlopen(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(remote.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(remote.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        remote._get_bytes("https://example.invalid/x")
    assert len(calls) == 1
