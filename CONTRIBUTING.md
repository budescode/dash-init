# Contributing to dash-app

Contributions are welcome. Bug reports, feature requests, new templates, documentation improvements, and code changes.

---

## Reporting a bug

1. Check the [existing issues](https://github.com/budescode/dash-app/issues) first to avoid duplicates.
2. Open a new issue and include:
   - A clear title describing the problem
   - The exact `dash-app` command you ran
   - What you expected vs what actually happened
   - Your Python version, dash-app version, and OS
   - Any relevant error messages or tracebacks

---

## Requesting a feature

Open an issue with the label `enhancement`. Describe:
- What you want to do that you currently can't
- Why it would be useful
- Any ideas on how it could work

---

## Submitting a pull request

**1. Fork the repo and create a branch**

```bash
git checkout -b fix/your-fix-name
# or
git checkout -b feat/your-feature-name
```

**2. Set up the dev environment**

```bash
pip install -e . pytest dash pandas dash-bootstrap-components
```

**3. Make your changes and run the tests**

```bash
pytest                             # built-in templates and offline remote tests
DASH_APP_NETWORK_TESTS=1 pytest    # also fetches every hub template
```

The test suite generates every built-in template and boots the resulting app. If `pytest` is green, your change works.

- Keep changes focused. One fix or feature per PR
- Don't change unrelated code
- Don't add runtime dependencies. dash-app is standard library only

**4. Open the pull request**

- Write a clear title and description explaining what changed and why
- Reference any related issue (e.g. `Closes #12`)

---

## Adding a built-in template

Templates are plain folders under `src/dash_app/templates/<name>/`. No Python needed:

1. Create the folder and add your files, suffixed with `.template` (`app.py.template`, `README.md.template`)
2. Prefix dotfiles with `dot_` (`dot_gitignore.template` becomes `.gitignore`)
3. Use `{{app_name}}`, `{{app_title}}` and `{{create_date}}` where the project name or date should go
4. Include `requirements.txt.template` and `pyproject.toml.template` with the same dependencies
5. Run `pytest`. The parametrized tests pick the new template up automatically and boot it
6. Add it to the templates table in `README.md`

---

## Adding a hub template

Hub templates live in [dash-templates-hub](https://github.com/budescode/dash-templates-hub) and are listed in `src/dash_app/registry.json`.

1. Make sure the template runs from a clean checkout with `python app.py` (no missing data files, no external services)
2. Add an entry to `registry.json` with its folder name and a one-line description
3. Run `DASH_APP_NETWORK_TESTS=1 pytest` to confirm it fetches and configures
4. Add it to the hub table in `README.md`

Bump the pinned `ref` in `registry.json` only after re-running the network tests.

---

## Questions

For general questions, open a [GitHub Discussion](https://github.com/budescode/dash-app/discussions) rather than an issue.

---

## Code of conduct

Be respectful and constructive. We're here to build something useful together.
