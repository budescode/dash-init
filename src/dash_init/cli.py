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


def _render(src, dest_dir: Path, app_name: str) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in src.iterdir():
        if entry.is_dir():
            written += _render(entry, dest_dir / _dest_name(entry.name, app_name), app_name)
        else:
            target = dest_dir / _dest_name(entry.name, app_name)
            content = _substitute(entry.read_text(encoding="utf-8"), app_name)
            target.write_text(content, encoding="utf-8")
            written.append(target)
    return written


def _title(app_name: str) -> str:
    return re.sub(r"[-_]+", " ", app_name).strip().title()


def _next_steps(app_name: str, entry: str, docker: bool) -> str:
    text = (
        "\nNext steps:\n"
        f"  cd {app_name}\n"
        "  python -m venv .venv && source .venv/bin/activate   # Windows: .venv\\Scripts\\activate\n"
        "  pip install -r requirements.txt\n"
        f"  python {entry}\n"
        "\nOr with uv:\n"
        f"  cd {app_name}\n"
        "  uv sync\n"
        f"  uv run {entry}\n"
    )
    if docker:
        text += (
            "\nOr with Docker:\n"
            f"  cd {app_name}\n"
            f"  docker build -t {app_name} .\n"
            f"  docker run -p 8050:8050 {app_name}\n"
        )
    return text


def init(app_name: str, template: str, parent: Path, docker: bool = False) -> Path:
    """Create a new project directory from a template. Returns its path."""
    if not NAME_RE.fullmatch(app_name):
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
    project_dir = parent / app_name
    if project_dir.exists() and any(project_dir.iterdir()):
        raise SystemExit(f"dash-init: directory {project_dir} already exists and is not empty")

    notes: list[str] = []
    if spec is None:
        files = _render(_templates_root() / template, project_dir, app_name)
        source = f"the '{template}' template"
    else:
        print(f"Fetching {spec.slug} ...")
        files = remote.fetch(spec, project_dir)
        notes = remote.configure(project_dir, app_name, _title(app_name))
        source = f"{spec.slug}"
    if docker:
        files += _render(_addons_root() / "docker", project_dir, app_name)

    print(f"Created {app_name} from {source}:\n")
    for f in sorted(set(files)):
        print(f"  {f.relative_to(parent)}")
    for n in notes:
        print(f"\n  * {n}")
    entry = remote.entry_point(project_dir) or "app.py"
    print(_next_steps(app_name, entry, docker))
    return project_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dash-init",
        description="Project tooling for Plotly Dash.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  dash-init create my-dashboard\n"
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
    create.add_argument("name", help="name of the project directory to create")
    create.add_argument(
        "-t", "--template", default="minimal",
        help="built-in or hub template name, or gh:owner/repo[/sub/dir][@ref] (default: minimal)",
    )
    create.add_argument(
        "--docker", "--dockerfile", action="store_true", dest="docker",
        help="also generate a Dockerfile and .dockerignore",
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
        init(args.name, args.template, Path.cwd(), docker=args.docker)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
