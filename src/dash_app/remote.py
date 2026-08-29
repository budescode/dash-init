"""Remote templates: pull a directory from a GitHub repo and configure it.

Two ways to name one:

* a **registry** name from ``registry.json``: curated, pinned to a commit
* an explicit spec ``gh:owner/repo[/sub/dir][@ref]``: anything on GitHub

Fetching uses only the standard library: one call to the Git Trees API to
list files, then each file is downloaded from raw.githubusercontent.com.
Only the requested directory is transferred, minus repo clutter
(screenshots, notebooks, caches, lockfiles).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# Paths (relative to the template dir) never copied into a new project.
JUNK_DIRS = {"screenshots", "notebooks", "__pycache__", ".git", ".idea", ".vscode"}
JUNK_FILES = {".DS_Store", "uv.lock", "poetry.lock", ".python-version", "Thumbs.db"}
JUNK_SUFFIXES = (".pyc", ".pyo")

DEFAULT_GITIGNORE = ".venv/\n__pycache__/\n*.pyc\n.env\n"


@dataclass(frozen=True)
class RemoteSpec:
    owner: str
    repo: str
    path: str  # subdirectory inside the repo, "" for the root
    ref: str | None  # branch, tag or commit; None = default branch

    @property
    def slug(self) -> str:
        s = f"{self.owner}/{self.repo}"
        if self.path:
            s += f"/{self.path}"
        if self.ref:
            s += f"@{self.ref}"
        return s


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

def _registry() -> dict:
    return json.loads((resources.files(__package__) / "registry.json").read_text("utf-8"))


def registry_templates() -> dict[str, str]:
    """name -> description for every curated remote template."""
    return {k: v["description"] for k, v in _registry()["templates"].items()}


def parse_spec(name: str) -> RemoteSpec | None:
    """Turn a template argument into a RemoteSpec, or None if it is a builtin."""
    reg = _registry()
    if name in reg["templates"]:
        owner, repo = reg["repo"].split("/", 1)
        return RemoteSpec(owner, repo, reg["templates"][name]["path"], reg["ref"])
    if name.startswith("gh:"):
        body = name[3:]
        ref = None
        if "@" in body:
            body, ref = body.rsplit("@", 1)
        parts = [p for p in body.split("/") if p]
        if len(parts) < 2:
            raise SystemExit(f"dash-app: bad template spec {name!r}, expected gh:owner/repo[/sub/dir][@ref]")
        owner, repo, *sub = parts
        return RemoteSpec(owner, repo, "/".join(sub), ref)
    return None


# --------------------------------------------------------------------------- #
# HTTP (thin, replaceable in tests)
# --------------------------------------------------------------------------- #

def _headers() -> dict[str, str]:
    h = {"User-Agent": "dash-app", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (https only)
        return r.read()


def _get_json(url: str) -> dict:
    return json.loads(_get_bytes(url).decode("utf-8"))


def _explain(err: Exception, spec: RemoteSpec) -> SystemExit:
    if isinstance(err, urllib.error.HTTPError):
        if err.code == 404:
            return SystemExit(f"dash-app: {spec.slug} not found on GitHub (check owner/repo, path and ref)")
        if err.code in (403, 429):
            return SystemExit(
                "dash-app: GitHub API rate limit hit. Set GITHUB_TOKEN to raise it, or try again later"
            )
        return SystemExit(f"dash-app: GitHub returned HTTP {err.code} for {spec.slug}")
    if isinstance(err, urllib.error.URLError):
        return SystemExit(f"dash-app: could not reach GitHub ({err.reason}). Are you online?")
    return SystemExit(f"dash-app: failed to fetch {spec.slug}: {err}")


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #

def _is_junk(rel: PurePosixPath) -> bool:
    if any(part in JUNK_DIRS for part in rel.parts[:-1]):
        return True
    return rel.name in JUNK_FILES or rel.name.endswith(JUNK_SUFFIXES)


def _list_files(spec: RemoteSpec) -> tuple[str, list[str]]:
    """Return (resolved commit sha, [paths relative to spec.path])."""
    ref = spec.ref
    if ref is None:
        ref = _get_json(f"{API}/repos/{spec.owner}/{spec.repo}")["default_branch"]
    tree = _get_json(f"{API}/repos/{spec.owner}/{spec.repo}/git/trees/{ref}?recursive=1")
    if tree.get("truncated"):
        raise SystemExit(f"dash-app: {spec.slug} is too large to list via the GitHub API")
    prefix = spec.path.rstrip("/") + "/" if spec.path else ""
    files = []
    for entry in tree["tree"]:
        if entry["type"] != "blob" or not entry["path"].startswith(prefix):
            continue
        rel = PurePosixPath(entry["path"][len(prefix):])
        if ".." in rel.parts or rel.is_absolute() or _is_junk(rel):
            continue
        files.append(str(rel))
    if not files:
        raise SystemExit(f"dash-app: no files found at {spec.slug}")
    return tree["sha"], files


def fetch(spec: RemoteSpec, dest: Path) -> list[Path]:
    """Download the template directory into ``dest`` (must not exist). Returns files written."""
    try:
        sha, files = _list_files(spec)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        raise _explain(e, spec) from None

    base = f"{RAW}/{spec.owner}/{spec.repo}/{sha}/"
    if spec.path:
        base += spec.path.rstrip("/") + "/"

    staging = Path(tempfile.mkdtemp(prefix=".dash-app-", dir=dest.parent))
    try:
        def grab(rel: str) -> Path:
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_get_bytes(base + rel))
            return target

        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(grab, files))
        except (urllib.error.URLError, OSError) as e:
            raise _explain(e, spec) from None
        shutil.move(str(staging), str(dest))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return sorted(p for p in dest.rglob("*") if p.is_file())


# --------------------------------------------------------------------------- #
# configure
# --------------------------------------------------------------------------- #

def _parse_requirements(text: str) -> list[str]:
    return [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith(("#", "-"))
    ]


def _pyproject_from_requirements(app_name: str, title: str, reqs: list[str]) -> str:
    deps = "\n".join(f'    "{r}",' for r in reqs)
    return (
        "[project]\n"
        f'name = "{app_name}"\n'
        'version = "0.1.0"\n'
        f'description = "{title}, a Plotly Dash app"\n'
        'readme = "README.md"\n'
        'requires-python = ">=3.11"\n'
        f"dependencies = [\n{deps}\n]\n"
    )


def configure(project_dir: Path, app_name: str, title: str) -> list[str]:
    """Make a fetched template look like *this* project. Returns notes for the user."""
    notes: list[str] = []
    pyproject = project_dir / "pyproject.toml"
    requirements = project_dir / "requirements.txt"

    if pyproject.is_file():
        text = pyproject.read_text("utf-8")
        new, n = re.subn(r'(?m)^name\s*=\s*"[^"]*"', f'name = "{app_name}"', text, count=1)
        if n:
            pyproject.write_text(new, "utf-8")
            notes.append(f"set project name to {app_name!r} in pyproject.toml")
    elif requirements.is_file():
        reqs = _parse_requirements(requirements.read_text("utf-8"))
        pyproject.write_text(_pyproject_from_requirements(app_name, title, reqs), "utf-8")
        notes.append("generated pyproject.toml from requirements.txt")

    gitignore = project_dir / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text(DEFAULT_GITIGNORE, "utf-8")
        notes.append("added .gitignore")
    return notes


def entry_point(project_dir: Path) -> str | None:
    for candidate in ("app.py", "run.py", "main.py"):
        if (project_dir / candidate).is_file():
            return candidate
    return None
