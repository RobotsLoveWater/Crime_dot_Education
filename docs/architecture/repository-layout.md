# Repository layout

The repository separates application code, authored content, durable documentation,
tests, operational scripts, browser assets, and runtime state.

```text
run.ps1                         local Flask development-server launcher
content/lessons/                 authored lesson JSON and its schema
docs/                            architecture, design, research, archived plans
src/mn_sentencing_explorer/
  analysis/                      dataframe, cache, geography, history, offense codes
  services/                      accounts, classes, lessons, attempt analytics
  resources/                     codebook and legacy plotting settings
  web/application.py             Flask composition, routes, view-model builders
scripts/                         cache-build, history-key, and instance-reset utilities
tests/regression/                data, map/filter, route, and response contracts
tests/scripts/                   isolated PowerShell utility fixtures
perf/                            request profiling and benchmark harness
deploy/                          provisioning and lesson-deployment scripts
static/                          nginx/Flask-served browser assets
templates/                       Jinja templates and partials
cache/, user/, classes/          git-ignored legacy runtime state
```

## Compatibility entry points

The small Python modules at the repository root intentionally alias packaged modules.
They preserve established commands and imports while implementation code lives under
`src/`:

- `flask --app app` and `gunicorn app:app`
- `python cache.py`
- imports such as `import cache`, `import account`, and `from data import Data`
- the historical root regression-test commands

Do not add new implementation logic to a root compatibility module.

For local development, `run.ps1` is the preferred server entry point. It invokes
`flask --app app` through uv from the repository root and accepts `-Debug`, `-Port`,
and `-BindAddress` options.

## Runtime state

Runtime paths remain `cache/`, `user/`, and `classes/` for deployment compatibility.
They are centralized in `src/mn_sentencing_explorer/paths.py`, so a future move to a
single `instance/` directory has one application boundary. Use
`scripts/reset-instance.ps1` to archive users and classes and create clean stores;
the script never moves or modifies the cache.

The root `static/` and `templates/` directories also remain deliberate: Flask points
to them explicitly, and nginx serves `static/` directly in production.
