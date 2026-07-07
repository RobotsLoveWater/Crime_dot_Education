# Deployment

Deploy the MN Sentencing Explorer (Crime[dot]Education) to a **Linux server**
(Ubuntu/Debian). The app is served by **gunicorn** behind **nginx** and
**auto-starts on boot** via a **systemd** service that also restarts it on crash.

Two files do the work:

| File | Runs on | Role |
|------|---------|------|
| [`setup.sh`](setup.sh) | the **server** (as root) | Idempotent provisioner: installs packages + uv, clones the repo, builds the venv, generates the runtime base (`cache/raw.parquet` + `cache/raw.csv`) from `dataset.sav`, writes the systemd unit + nginx site, enables and starts everything. |
| [`deploy.ps1`](deploy.ps1) | your **Windows** machine | Convenience driver: uploads `setup.sh` (+ `dataset.sav`) over SSH and runs the provisioner for you. |

## Prerequisites

- A Linux server (Ubuntu 22.04/24.04 or Debian) with an SSH user that can `sudo`.
- The Windows **OpenSSH client** (`ssh.exe` / `scp.exe`) — bundled with Windows 11.
- Your `dataset.sav` (the ~141 MB SPSS source, **not** in git). The server builds
  the runtime base (`cache/raw.parquet` + `cache/raw.csv`) from it on first deploy.

## Quick start (from this Windows machine)

```powershell
cd deploy
# First deploy: push code + data and provision everything.
.\deploy.ps1 -Server ubuntu@YOUR.SERVER.IP -DatasetPath ..\dataset.sav -ServerName explorer.example.edu
```

Redeploy the latest code later (data already on the server — omit `-DatasetPath`):

```powershell
.\deploy.ps1 -Server ubuntu@YOUR.SERVER.IP
```

Useful `deploy.ps1` switches:

| Switch | Default | Meaning |
|--------|---------|---------|
| `-Server` | *(required)* | `user@host` of the target. |
| `-DatasetPath` | — | Local `dataset.sav` to upload (first deploy only). |
| `-SshKey` | — | Path to an SSH private key (`-i`). |
| `-ServerName` | `_` (catch-all) | nginx `server_name` / your domain. |
| `-GitRef` | `main` | Branch or tag to deploy. |
| `-RepoUrl` | the public GitHub repo | Override if you forked it. |
| `-AppUser` | `crimeedu` | Unprivileged service user on the server. |
| `-WarmCache` | off | Pre-warm per-column stats (slow; regenerates on demand anyway). |

## Manual path (run directly on the server)

If you'd rather not use the Windows driver, copy `setup.sh` to the server, put
`dataset.sav` at `/tmp/dataset.sav`, and run:

```bash
sudo SERVER_NAME=explorer.example.edu bash setup.sh
```

Every setting is an overridable env var (`REPO_URL`, `GIT_REF`, `APP_USER`,
`APP_DIR`, `BIND_ADDR`, `WORKERS`, `TIMEOUT`, `SERVER_NAME`, `WARM_CACHE`, …) —
see the top of [`setup.sh`](setup.sh).

## What ends up on the server

- Code: `/home/crimeedu/crime-education` (owned by the `crimeedu` service user).
- Service: `crime-education.service` — `systemctl status crime-education`,
  logs via `journalctl -u crime-education -f`.
- gunicorn binds `127.0.0.1:8000`; nginx serves `/static/` directly and proxies
  the rest on port 80.
- `SECRET_KEY`: generated once and stored at `/etc/crime-education/env`
  (mode 640, root:crimeedu). It is **preserved** across redeploys so sessions
  stay valid. Keep it; never commit it.

## After the first deploy

```bash
# Open the firewall for HTTP (if ufw is active):
sudo ufw allow 'Nginx HTTP'

# Add HTTPS with a real domain (DNS must point at the server first):
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d explorer.example.edu
```

## Notes & gotchas

- **Idempotent:** re-running `setup.sh` (or `deploy.ps1`) fetches the latest
  code, re-syncs deps, and restarts the service. It won't clobber the runtime base
  (`cache/raw.parquet`/`cache/raw.csv`), the `SECRET_KEY`, or user data (`user/`,
  `classes/`). Upgrading an older CSV-only deploy is automatic: with `cache/raw.parquet`
  missing, the next run rebuilds the base from `dataset.sav` (both files), or — if only
  `cache/raw.csv` is on the box — builds the Parquet base directly from it (byte-identical
  either way, since the Parquet is always derived from the CSV).
- **gunicorn** is installed into the project venv (`uv pip install gunicorn`)
  rather than added to `pyproject.toml`/`uv.lock`, so the pinned dependency set
  is untouched.
- **Data is not in git.** Without `dataset.sav` the service still starts but
  can't serve data. Upload `dataset.sav` to `~crimeedu/crime-education/` and
  re-run `setup.sh` to build the base (`cache/raw.parquet` + `cache/raw.csv`).
- **Storage dirs** (`user/`, `classes/`, `cache/`) are created and owned by the
  service user; they hold private data and must never be committed.
- **Multiple workers** share the filesystem cache safely (no in-memory session
  state — every request replays history). Cold requests replay filters over
  ~294k rows, so the timeout is generous (120s); tune `WORKERS`/`TIMEOUT` for
  your box.
- **Shared base DataFrame (`--preload`).** gunicorn runs with `--preload`, so the
  ~294k-row base is loaded **once in the master** (at `app.py` import time) and all
  `WORKERS` workers inherit it **copy-on-write** instead of parsing their own copy.
  This holds because the string columns are stored as categoricals (numpy code
  arrays, not per-cell Python objects), so worker reads don't churn refcounts and
  dirty the shared pages. Net effect: base RAM ≈ **one** shared copy, not `WORKERS ×`.
  Verify it on the server (PSS ≈ one copy's worth of the base, private RSS small):
  ```bash
  for p in $(pgrep -f 'gunicorn.*app:app'); do
    printf '%s ' "$p"; grep -E '^(Rss|Pss|Private):' /proc/$p/smaps_rollup
  done
  ```
  **Tradeoff:** with `--preload`, a code change needs a full service restart (workers
  no longer re-import independently). If CoW sharing ever underperforms on your box,
  drop `--preload` from the unit's `ExecStart` — each worker then loads the base once
  on its own (still fast: the ~23 MB Parquet parses in a fraction of a second).
