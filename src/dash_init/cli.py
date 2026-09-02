"""dash-init: scaffold a new Plotly Dash project.

Templates are plain directories under ``templates/``. Every file in a
template is copied with token substitution. Two filename conventions:

* a trailing ``.template`` suffix is stripped on copy (it keeps template
  code out of the way of linters, test collectors, and import machinery)
* a ``dot_`` prefix becomes a leading dot (``dot_gitignore.template``
  is written as ``.gitignore``), because packaging tools skip dotfiles

Tokens available inside template files and file names:

* ``{{app_name}}``    the project name as typed, e.g. ``sales-tracker``
* ``{{app_title}}``   a human title derived from it, e.g. ``Sales Tracker``
* ``{{create_date}}`` today's date, ISO format
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from importlib import resources
from pathlib import Path

from . import __version__, remote

NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")


def _templates_root():
    return resources.files(__package__) / "templates"


def _addons_root():
    return resources.files(__package__) / "addons"


def available_templates() -> list[str]:
    return sorted(p.name for p in _templates_root().iterdir() if p.is_dir())


def _substitute(text: str, app_name: str) -> str:
    title = _title(app_name)
    return (
        text.replace("{{app_name}}", app_name)
        .replace("{{app_title}}", title)
        .replace("{{create_date}}", date.today().isoformat())
    )


def _dest_name(name: str, app_name: str) -> str:
    if name.endswith(".template"):
        name = name[: -len(".template")]
    if name.startswith("dot_"):
        name = "." + name[len("dot_"):]
    return _substitute(name, app_name)


def _render(
    src,
    dest_dir: Path,
    app_name: str,
    overwrite: bool = True,
    skipped: list[Path] | None = None,
    exclude: frozenset[str] = frozenset(),
) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in src.iterdir():
        if entry.is_dir():
            written += _render(
                entry, dest_dir / _dest_name(entry.name, app_name), app_name,
                overwrite=overwrite, skipped=skipped, exclude=exclude,
            )
        else:
            target = dest_dir / _dest_name(entry.name, app_name)
            if target.name in exclude:
                continue
            if not overwrite and target.exists():
                if skipped is not None:
                    skipped.append(target)
                continue
            content = _substitute(entry.read_text(encoding="utf-8"), app_name)
            target.write_text(content, encoding="utf-8")
            written.append(target)
    return written


def _template_requirements(template: str) -> list[str]:
    """Dependency specs a built-in template needs, from its requirements file."""
    src = _templates_root() / template / "requirements.txt.template"
    if not src.is_file():
        return []
    return remote._parse_requirements(src.read_text(encoding="utf-8"))


def _add_deps(project_dir: Path, deps: list[str], install: bool) -> bool:
    """Get ``deps`` into an existing pyproject.toml.

    Delegates to ``uv add`` (which edits pyproject.toml, updates uv.lock and
    installs into the venv) rather than rewriting the user's file ourselves.
    Returns True if the dependencies were actually added.
    """
    if not deps:
        return False
    quoted = " ".join(f'"{d}"' for d in deps)
    if install and shutil.which("uv"):
        print(f"\nAdding dependencies to your project:\n  uv add {quoted}\n")
        proc = subprocess.run(["uv", "add", *deps], cwd=project_dir)
        if proc.returncode != 0:
            raise SystemExit(
                f"dash-init: 'uv add' failed (exit code {proc.returncode}). "
                f"Add the dependencies yourself:  uv add {quoted}"
            )
        return True
    print(
        "\nYour pyproject.toml was left untouched. Add the dependencies yourself:\n"
        f"  uv add {quoted}\n"
        "or:\n"
        f"  pip install {quoted}"
    )
    return False


def _title(app_name: str) -> str:
    return re.sub(r"[-_]+", " ", app_name).strip().title()


def _next_steps(
    app_name: str, entry: str, docker: bool,
    in_place: bool = False, deps_added: bool = False,
) -> str:
    cd = "" if in_place else f"  cd {app_name}\n"
    if deps_added:
        text = f"\nNext steps:\n{cd}  uv run {entry}\n"
    else:
        text = (
            "\nNext steps:\n"
            + cd
            + "  python -m venv .venv && source .venv/bin/activate   # Windows: .venv\\Scripts\\activate\n"
            "  pip install -r requirements.txt\n"
            f"  python {entry}\n"
            "\nOr with uv:\n"
            + cd
            + "  uv sync\n"
            f"  uv run {entry}\n"
        )
    if docker:
        text += (
            "\nOr with Docker:\n"
            + cd
            + f"  docker build -t {app_name} .\n"
            f"  docker run -p 8050:8050 {app_name}\n"
        )
    return text


def init(
    app_name: str, template: str, parent: Path,
    docker: bool = False, install: bool = True,
) -> Path:
    """Create a project from a template. Returns its directory.

    ``app_name`` may be ``"."``: scaffold into ``parent`` itself (name taken
    from the directory), skipping files that already exist. If a
    pyproject.toml is already there, the template's dependencies are added
    via ``uv add`` (or printed, when uv is missing or ``install`` is False)
    instead of writing the template's own pyproject/requirements.
    """
    in_place = app_name == "."
    if in_place:
        app_name = parent.resolve().name
        if not NAME_RE.fullmatch(app_name):
            raise SystemExit(
                f"dash-init: current directory name {app_name!r} is not a valid "
                "project name. Use letters, digits, '.', '-' and '_', starting "
                "with a letter, or run: dash-init create <name>"
            )
    elif not NAME_RE.fullmatch(app_name):
        raise SystemExit(
            f"dash-init: invalid project name {app_name!r}. Use letters, "
            "digits, '.', '-' and '_', starting with a letter"
        )
    spec = remote.parse_spec(template)
    builtins = available_templates()
    if spec is None and template not in builtins:
        raise SystemExit(
            f"dash-init: unknown template {template!r}; "
            f"available: {', '.join(builtins + sorted(remote.registry_templates()))} "
            "or gh:owner/repo[/sub/dir][@ref]"
        )
    if in_place:
        if spec is not None:
            raise SystemExit(
                "dash-init: remote templates cannot scaffold into the current "
                "directory yet; use a built-in template or run: "
                f"dash-init create <name> -t {template}"
            )
        project_dir = parent
    else:
        project_dir = parent / app_name
        if project_dir.exists() and any(project_dir.iterdir()):
            raise SystemExit(f"dash-init: directory {project_dir} already exists and is not empty")

    had_pyproject = in_place and (project_dir / "pyproject.toml").is_file()
    exclude = frozenset({"pyproject.toml", "requirements.txt"}) if had_pyproject else frozenset()
    skipped: list[Path] = []
    notes: list[str] = []
    if spec is None:
        files = _render(
            _templates_root() / template, project_dir, app_name,
            overwrite=not in_place, skipped=skipped, exclude=exclude,
        )
        source = f"the '{template}' template"
    else:
        print(f"Fetching {spec.slug} ...")
        files = remote.fetch(spec, project_dir)
        notes = remote.configure(project_dir, app_name, _title(app_name))
        source = f"{spec.slug}"
    if docker:
        files += _render(
            _addons_root() / "docker", project_dir, app_name,
            overwrite=not in_place, skipped=skipped,
        )

    where = "the current directory" if in_place else app_name
    print(f"Created {where} from {source}:\n")
    for f in sorted(set(files)):
        print(f"  {f.relative_to(parent)}")
    if skipped:
        print("\nSkipped (already exist, left untouched):")
        for f in sorted(set(skipped)):
            print(f"  {f.relative_to(parent)}")
    for n in notes:
        print(f"\n  * {n}")

    deps_added = False
    if had_pyproject:
        deps_added = _add_deps(project_dir, _template_requirements(template), install)

    entry = remote.entry_point(project_dir) or "app.py"
    print(_next_steps(app_name, entry, docker, in_place=in_place, deps_added=deps_added))
    return project_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dash-init",
        description="Project tooling for Plotly Dash.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  dash-init create my-dashboard\n"
            "  dash-init create .                 # scaffold into the current directory\n"
            "  dash-init create sales-app -t bootstrap\n"
            "  dash-init create api-monitor -t multipage --docker\n"
            "  dash-init create shop -t ecommerce-admin\n"
            "  dash-init create demo -t gh:someone/repo/examples/app\n"
            "  dash-init templates\n"
        ),
    )
    parser.add_argument("-V", "--version", action="version", version=f"dash-init {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    create = sub.add_parser(
        "create", help="scaffold a new Dash project",
        description="Scaffold a new Plotly Dash project from a template.",
    )
    create.add_argument(
        "name",
        help="name of the project directory to create, or '.' to scaffold "
             "into the current directory (existing files are never overwritten)",
    )
    create.add_argument(
        "-t", "--template", default="minimal",
        help="built-in or hub template name, or gh:owner/repo[/sub/dir][@ref] (default: minimal)",
    )
    create.add_argument(
        "--docker", "--dockerfile", action="store_true", dest="docker",
        help="also generate a Dockerfile and .dockerignore",
    )
    create.add_argument(
        "--no-install", action="store_true",
        help="with '.', print the dependencies to add instead of running 'uv add'",
    )

    sub.add_parser("templates", help="list available templates")

    args = parser.parse_args(argv)

    if args.command == "templates":
        print("built-in:")
        for t in available_templates():
            print(f"  {t}")
        print("\nfrom dash-templates-hub (downloaded on create):")
        for name, desc in remote.registry_templates().items():
            print(f"  {name:18} {desc}")
        print("\nany GitHub directory:  -t gh:owner/repo[/sub/dir][@ref]")
        return 0
    if args.command == "create":
        init(args.name, args.template, Path.cwd(), docker=args.docker, install=not args.no_install)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
