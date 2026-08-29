# dash-app

**Project generator for [Plotly Dash](https://dash.plotly.com): one command to a running app.**

```bash
pip install dash-app
dash-app create my-dashboard
cd my-dashboard
pip install -r requirements.txt     # or: uv sync
python app.py                       # or: uv run app.py
```

You get a working, current Dash app with a callback, a chart, an `assets/`
folder, a README, `requirements.txt` + `pyproject.toml`, and a `.gitignore`.
Not a throwaway "hello world" example, but the structure you'd have written
yourself.

```
my-dashboard/
├── app.py              # layout + callback, exposes server for deployment
├── assets/
│   └── custom.css      # custom styling
├── requirements.txt    # dependencies
├── pyproject.toml      # project metadata and dependencies
├── README.md           # how to run and deploy it
└── .gitignore
```

Every generated project includes a README with steps to deploy it (Plotly
Cloud, any Python host, or Docker with `--docker`).

Generated projects target **Python 3.11+** and pin current versions:
`dash>=4.4.1`, `pandas>=3.0.5`, `dash-bootstrap-components>=2.0.4` (bootstrap
template). The `dash-app` tool itself runs on Python 3.9+ and has no
dependencies.

## Usage

```
dash-app create <name>                      create a project from the default (minimal) template
dash-app create <name> -t <template>        choose a built-in or hub template
dash-app create <name> -t gh:owner/repo/sub/dir[@ref]
                                            pull any directory on GitHub as a template
dash-app create <name> --docker             also generate a Dockerfile + .dockerignore (alias: --dockerfile)
dash-app templates                          list everything available
dash-app --version
```

`create` refuses to overwrite a non-empty directory and never installs
anything. It writes files and prints the next steps.

## Built-in templates

| Name        | What you get                                                      |
| ----------- | ----------------------------------------------------------------- |
| `minimal`   | Single-file app with one callback (default)                       |
| `multipage` | Dash Pages app: `app.py` shell + auto-routed `pages/` directory  |
| `bootstrap` | Sidebar + KPI cards layout with dash-bootstrap-components         |
| `csv`       | Charts `data/sample.csv`; swap in your own file                  |

These ship inside the package and need no network. Every one is generated
and smoke-run in CI against current Dash.

Add `--docker` to any of them for a ready-to-build `Dockerfile` +
`.dockerignore` (`docker build -t my-dashboard . && docker run -p 8050:8050 my-dashboard`).

## Templates from dash-templates-hub

Full admin dashboards from
[budescode/dash-templates-hub](https://github.com/budescode/dash-templates-hub)
are available by name and downloaded when you run `create`:

| Name              | What you get                                              |
| ----------------- | --------------------------------------------------------- |
| `admin-dashboard` | General-purpose admin dashboard (light, modern)           |
| `kiaalap`         | Education-management dashboard, 50+ pages (light, indigo) |
| `nalika`          | Analytics-focused dashboard (dark, professional)          |
| `purity-ui`       | Purity UI admin dashboard port                            |

```bash
dash-app create school -t kiaalap
```

What happens:

- Only that template's files are fetched: no git clone, no full-repo
  tarball. Repo clutter (screenshots, notebooks, caches, lockfiles) is dropped.
- The project name is set in `pyproject.toml`; a `pyproject.toml` (from
  `requirements.txt`) and a `.gitignore` are generated if the template lacks
  them.
- The hub is pinned to a specific commit in `src/dash_app/registry.json`, and
  CI fetches and checks every entry, so a change in the hub cannot silently
  break `create`.
- A failed download leaves nothing behind. Errors say whether you're offline,
  the path doesn't exist, or you hit GitHub's rate limit (set `GITHUB_TOKEN`
  to raise it).

Any GitHub directory works the same way, un-curated:

```bash
dash-app create demo -t gh:someone/repo/examples/my-app@v2.1
```

## Why trust it

- **Tested against current Dash.** Every template is generated and booted in
  CI, weekly, so if Dash breaks something you see a red build here, not in
  your terminal.
- **Never touches your environment.** It writes files and tells you what to
  run. No `pip install` on your behalf.
- **Zero dependencies.** Pure standard library, so installing it can't
  conflict with anything.

## Roadmap

- `deploy` subcommand
- `--dir` option to create the project outside the current directory
- Turn an existing app into a template (`dash-app create --from-project`)
- More templates 

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- [Report a bug](.github/ISSUE_TEMPLATE/bug_report.md)
- [Request a feature](.github/ISSUE_TEMPLATE/feature_request.md)

## Connect

- PyPI: https://pypi.org/project/dash-app
- LinkedIn: https://www.linkedin.com/in/budescode
- PayPal: https://www.paypal.com/paypalme/omonbudeemma

## Prior art & credit

The template-directory approach follows the archived
[dash-tools](https://github.com/andrew-hossack/dash-tools) by Andrew Hossack
(MIT). No code was reused, but the idea that a template should be a plain
folder anyone can contribute to comes from there.

## License

MIT
