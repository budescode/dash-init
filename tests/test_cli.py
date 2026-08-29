import runpy

import pytest

from dash_app.cli import available_templates, init, main

# extra import requirements per template, for smoke-run skipping
TEMPLATE_DEPS = {"bootstrap": ["dash_bootstrap_components"]}

ALL_TEMPLATES = available_templates()


def test_expected_templates_present():
    assert set(ALL_TEMPLATES) >= {"minimal", "multipage", "bootstrap", "csv"}


def test_templates_command(capsys):
    assert main(["templates"]) == 0
    out = capsys.readouterr().out
    for t in ALL_TEMPLATES:
        assert t in out


def test_create_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "my-app", "-t", "minimal", "--docker"]) == 0
    assert (tmp_path / "my-app" / "app.py").is_file()
    assert (tmp_path / "my-app" / "Dockerfile").is_file()


def test_no_command_prints_help(capsys):
    assert main([]) == 2
    assert "create" in capsys.readouterr().out


def test_init_writes_expected_files(tmp_path):
    project = init("my-app", "minimal", tmp_path)
    expected = ["app.py", "requirements.txt", "pyproject.toml", "README.md", ".gitignore", "assets/custom.css"]
    for rel in expected:
        assert (project / rel).is_file(), f"missing {rel}"
    assert not (project / "Dockerfile").exists(), "Dockerfile should be opt-in"


def test_docker_flag_adds_docker_files(tmp_path):
    project = init("my-app", "minimal", tmp_path, docker=True)
    dockerfile = (project / "Dockerfile").read_text(encoding="utf-8")
    assert (project / ".dockerignore").is_file()
    assert "gunicorn" in dockerfile
    assert "{{" not in dockerfile
    assert "docker build -t my-app ." in dockerfile


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_no_unrendered_tokens_or_template_suffixes(template, tmp_path):
    project = init("my-app", template, tmp_path)
    for f in project.rglob("*"):
        if f.is_file():
            assert not f.name.endswith(".template"), f.name
            assert "{{" not in f.read_text(encoding="utf-8"), f"unrendered token in {f}"


def test_tokens_substituted(tmp_path):
    project = init("sales_tracker", "minimal", tmp_path)
    app = (project / "app.py").read_text(encoding="utf-8")
    assert 'title="Sales Tracker"' in app


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_generated_app_starts(template, tmp_path):
    """The scaffold's whole promise: every generated app must actually run."""
    pytest.importorskip("dash")
    for dep in TEMPLATE_DEPS.get(template, []):
        pytest.importorskip(dep)
    project = init("smoke-app", template, tmp_path)
    # run app.py with __name__ != "__main__" so app.run() is not invoked
    module = runpy.run_path(str(project / "app.py"), run_name="smoke")
    app = module["app"]
    assert app.title == "Smoke App"
    assert module["server"] is app.server


def test_multipage_registers_pages(tmp_path):
    pytest.importorskip("dash")
    import dash

    project = init("pages-app", "multipage", tmp_path)
    runpy.run_path(str(project / "app.py"), run_name="smoke")
    paths = {p["relative_path"] for p in dash.page_registry.values()}
    assert "/" in paths and "/analytics" in paths


def test_refuses_existing_nonempty_dir(tmp_path):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "file.txt").write_text("hi")
    with pytest.raises(SystemExit):
        init("taken", "minimal", tmp_path)


def test_rejects_invalid_name(tmp_path):
    with pytest.raises(SystemExit):
        init("1bad/name", "minimal", tmp_path)


def test_rejects_unknown_template(tmp_path):
    with pytest.raises(SystemExit):
        init("my-app", "no-such-template", tmp_path)


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_pyproject_matches_requirements(template, tmp_path):
    """pyproject.toml must be valid and list the same deps as requirements.txt."""
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    project = init("my-app", template, tmp_path)
    data = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "my-app"
    reqs = [
        line.strip()
        for line in (project / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert sorted(data["project"]["dependencies"]) == sorted(reqs)
