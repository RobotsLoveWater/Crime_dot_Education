#!/usr/bin/env bash
#
# setup.sh — provision & deploy the MN Sentencing Explorer (Crime[dot]Education)
# on a Linux server (Ubuntu/Debian), serving it with gunicorn behind nginx and
# auto-starting it on boot via systemd.
#
# This script is IDEMPOTENT: run it again to update the code and restart cleanly.
#
# Run it AS ROOT on the target server:
#     sudo bash setup.sh
#
# Everything below can be overridden by exporting the variable before you run,
# e.g.:  sudo SERVER_NAME=explorer.example.edu WARM_CACHE=yes bash setup.sh
#
# The companion driver (deploy.ps1) uploads this file + dataset.sav and runs it
# for you over SSH — but this script stands on its own.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment)
# ---------------------------------------------------------------------------
REPO_URL="${REPO_URL:-https://github.com/RobotsLoveWater/Crime_dot_Education.git}"
GIT_REF="${GIT_REF:-main}"                 # branch or tag to deploy

APP_NAME="${APP_NAME:-crime-education}"    # systemd unit + nginx site name
APP_USER="${APP_USER:-crimeedu}"           # dedicated, unprivileged service user
APP_HOME="/home/${APP_USER}"
APP_DIR="${APP_DIR:-${APP_HOME}/${APP_NAME}}"

BIND_ADDR="${BIND_ADDR:-127.0.0.1:8000}"   # gunicorn listen addr (behind nginx)
WORKERS="${WORKERS:-3}"                     # gunicorn worker processes
TIMEOUT="${TIMEOUT:-120}"                   # gunicorn/nginx timeout (secs); cold
                                            # cache replays over ~294k rows are slow
SERVER_NAME="${SERVER_NAME:-_}"            # nginx server_name ('_' = catch-all)

DATASET_STAGING="${DATASET_STAGING:-/tmp/dataset.sav}"  # uploaded .sav lands here
WARM_CACHE="${WARM_CACHE:-no}"             # 'yes' pre-warms per-column stats
                                            # (much slower deploy; regenerates on
                                            # demand anyway) — see cache.py

ENV_DIR="/etc/${APP_NAME}"
ENV_FILE="${ENV_DIR}/env"                   # holds the stable SECRET_KEY
UV_BIN="${APP_HOME}/.local/bin/uv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[error] %s\033[0m\n' "$*" >&2; exit 1; }

# Run a command as the unprivileged app user, with uv on PATH.
run_as_app() {
    sudo -u "$APP_USER" -H env \
        "PATH=${APP_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin" \
        "HOME=${APP_HOME}" \
        bash -lc "$1"
}

[ "$(id -u)" -eq 0 ] || die "This script must run as root (use: sudo bash setup.sh)."

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
log "Installing system packages (git, curl, nginx, openssl)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl git nginx openssl

# ---------------------------------------------------------------------------
# 2. Dedicated service user
# ---------------------------------------------------------------------------
if id "$APP_USER" &>/dev/null; then
    log "Service user '$APP_USER' already exists"
else
    log "Creating service user '$APP_USER'"
    useradd --create-home --shell /bin/bash "$APP_USER"
fi

# ---------------------------------------------------------------------------
# 3. uv (Python/dependency manager) for the service user
# ---------------------------------------------------------------------------
if [ -x "$UV_BIN" ]; then
    log "uv already installed at $UV_BIN"
else
    log "Installing uv for '$APP_USER'"
    run_as_app 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi
[ -x "$UV_BIN" ] || die "uv install failed (expected $UV_BIN)."

# ---------------------------------------------------------------------------
# 4. Fetch / update the application code
# ---------------------------------------------------------------------------
if [ -d "${APP_DIR}/.git" ]; then
    log "Updating existing checkout in ${APP_DIR} (ref: ${GIT_REF})"
    run_as_app "git -C '${APP_DIR}' fetch --prune origin"
    run_as_app "git -C '${APP_DIR}' checkout -f '${GIT_REF}'"
    run_as_app "git -C '${APP_DIR}' reset --hard 'origin/${GIT_REF}' 2>/dev/null || git -C '${APP_DIR}' reset --hard '${GIT_REF}'"
else
    log "Cloning ${REPO_URL} (ref: ${GIT_REF}) into ${APP_DIR}"
    run_as_app "git clone --branch '${GIT_REF}' '${REPO_URL}' '${APP_DIR}'"
fi

# ---------------------------------------------------------------------------
# 5. Writable storage dirs (git-ignored, created on demand by the app)
#    account.create uses os.mkdir (not makedirs), so user/ MUST already exist.
# ---------------------------------------------------------------------------
log "Ensuring writable storage directories exist"
# matplotlib/seaborn (imported by data.py) build a font cache under $HOME on first
# import; the unit makes home read-only, so give it a writable cache dir in-tree.
run_as_app "mkdir -p '${APP_DIR}/user' '${APP_DIR}/classes' '${APP_DIR}/cache/data' '${APP_DIR}/.cache/matplotlib'"

# ---------------------------------------------------------------------------
# 6. dataset.sav — place the uploaded staging copy if we don't have data yet
# ---------------------------------------------------------------------------
if [ -f "$DATASET_STAGING" ] && [ ! -f "${APP_DIR}/dataset.sav" ]; then
    log "Installing uploaded dataset.sav from ${DATASET_STAGING}"
    mv "$DATASET_STAGING" "${APP_DIR}/dataset.sav"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/dataset.sav"
fi

# ---------------------------------------------------------------------------
# 7. Python environment + gunicorn
# ---------------------------------------------------------------------------
log "Syncing the Python environment (uv sync — installs Python 3.13 + deps)"
run_as_app "cd '${APP_DIR}' && '${UV_BIN}' sync"

log "Installing gunicorn into the project venv"
# gunicorn is not a project dependency (kept out of pyproject/uv.lock on purpose);
# install it into the synced .venv so systemd can call it directly, with no
# per-boot dependency resolution or network access required.
run_as_app "cd '${APP_DIR}' && '${UV_BIN}' pip install gunicorn"
[ -x "${APP_DIR}/.venv/bin/gunicorn" ] || die "gunicorn not found in ${APP_DIR}/.venv/bin."

# ---------------------------------------------------------------------------
# 8. Build the runtime datafile from dataset.sav if missing.
#    The runtime prefers the typed Parquet base (cache/raw.parquet — ~10x smaller,
#    ~20x faster to load) and falls back to cache/raw.csv. cache.py __main__ now
#    prompts three times: create raw csv? / create raw parquet? / cache info?
#    (Parquet is built from raw.csv, so both are produced.)
# ---------------------------------------------------------------------------
if [ -f "${APP_DIR}/cache/raw.parquet" ]; then
    log "cache/raw.parquet already present — skipping build"
elif [ -f "${APP_DIR}/dataset.sav" ]; then
    if [ "$WARM_CACHE" = "yes" ]; then
        log "Building cache/raw.{csv,parquet} AND warming per-column stats (this is slow)"
        answers='y\ny\ny\n'
    else
        log "Building cache/raw.{csv,parquet} from dataset.sav (per-column warming skipped)"
        answers='y\ny\nn\n'
    fi
    run_as_app "cd '${APP_DIR}' && printf '${answers}' | '${UV_BIN}' run python cache.py"
    [ -f "${APP_DIR}/cache/raw.parquet" ] || die "cache/raw.parquet was not created — check cache.py output above."
elif [ -f "${APP_DIR}/cache/raw.csv" ]; then
    # Upgrade path from a CSV-only deploy without dataset.sav on the box: the Parquet
    # base is built FROM raw.csv (that's also how cache.py builds it), so no SPSS
    # source is needed — mirror-load the CSV and write the typed Parquet beside it.
    log "Upgrading CSV-only deploy: building cache/raw.parquet from cache/raw.csv"
    run_as_app "cd '${APP_DIR}' && '${UV_BIN}' run python -c 'from data import Data; d = Data(); d.load(\"cache/raw.csv\"); d.save_parquet(\"cache/raw\")'"
    [ -f "${APP_DIR}/cache/raw.parquet" ] || die "cache/raw.parquet was not created from raw.csv — check the output above."
else
    warn "No dataset.sav and no cache/raw.parquet — the app will start but cannot serve"
    warn "data until you upload dataset.sav to ${APP_DIR}/ and re-run this script."
fi

# ---------------------------------------------------------------------------
# 9. SECRET_KEY — generate once, keep stable across restarts/redeploys
# ---------------------------------------------------------------------------
mkdir -p "$ENV_DIR"
if [ -f "$ENV_FILE" ]; then
    log "Reusing existing ${ENV_FILE} (SECRET_KEY preserved)"
else
    log "Generating a stable SECRET_KEY at ${ENV_FILE}"
    SECRET="$(openssl rand -hex 32)"
    printf 'SECRET_KEY=%s\n' "$SECRET" > "$ENV_FILE"
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

# ---------------------------------------------------------------------------
# 10. systemd service (auto-start on boot, restart on failure)
# ---------------------------------------------------------------------------
log "Writing systemd unit /etc/systemd/system/${APP_NAME}.service"
cat > "/etc/systemd/system/${APP_NAME}.service" <<EOF
[Unit]
Description=Crime[dot]Education / MN Sentencing Explorer (Flask + gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
Environment=HOME=${APP_HOME}
Environment=MPLCONFIGDIR=${APP_DIR}/.cache/matplotlib
# --preload (Lever D): load the WSGI app — and, via app.py's import-time warm, the base
# DataFrame — ONCE in the master before forking workers, so the ~294k-row base is shared
# copy-on-write across all ${WORKERS} workers instead of parsed per worker. This holds
# because the string columns are categoricals (numpy code-arrays, not per-cell Python
# objects), so worker reads don't churn refcounts and dirty the shared pages. Tradeoff:
# code changes need a full restart (workers no longer re-import independently). If CoW
# sharing ever underperforms, drop --preload to fall back to per-worker load-once.
ExecStart=${APP_DIR}/.venv/bin/gunicorn --preload --chdir ${APP_DIR} --workers ${WORKERS} --timeout ${TIMEOUT} --bind ${BIND_ADDR} app:app
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
EOF

log "Enabling + (re)starting ${APP_NAME}.service"
systemctl daemon-reload
systemctl enable "$APP_NAME" >/dev/null
systemctl restart "$APP_NAME"

# ---------------------------------------------------------------------------
# 11. nginx reverse proxy (terminates HTTP, serves /static, proxies the rest)
# ---------------------------------------------------------------------------
log "Writing nginx site /etc/nginx/sites-available/${APP_NAME}"
cat > "/etc/nginx/sites-available/${APP_NAME}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${SERVER_NAME};

    # Static assets are served directly by nginx (fonts, css, js, vendor libs).
    location /static/ {
        alias ${APP_DIR}/static/;
        expires 30d;
        access_log off;
    }

    location / {
        proxy_pass http://${BIND_ADDR};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout ${TIMEOUT}s;
        proxy_connect_timeout ${TIMEOUT}s;
    }
}
EOF

ln -sf "/etc/nginx/sites-available/${APP_NAME}" "/etc/nginx/sites-enabled/${APP_NAME}"
rm -f /etc/nginx/sites-enabled/default

log "Testing + reloading nginx"
nginx -t
systemctl enable nginx >/dev/null
systemctl restart nginx

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
log "Deployment complete."
cat <<EOF

  Service : ${APP_NAME}.service   (systemctl status ${APP_NAME})
  Logs    : journalctl -u ${APP_NAME} -f
  App URL : http://${SERVER_NAME/_/<server-ip-or-hostname>}/
  gunicorn: ${BIND_ADDR}  ($WORKERS workers, ${TIMEOUT}s timeout)
  Code    : ${APP_DIR}   (redeploy: re-run this script — it pulls & restarts)
  Secret  : ${ENV_FILE}  (SECRET_KEY — keep it; do not commit)

Next steps you may want:
  * Open the firewall for HTTP:            ufw allow 'Nginx HTTP'
  * Add HTTPS with a real domain + certbot: apt install certbot python3-certbot-nginx
                                            certbot --nginx -d ${SERVER_NAME}
EOF
