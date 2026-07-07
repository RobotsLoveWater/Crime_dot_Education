<#
.SYNOPSIS
    Deploy the MN Sentencing Explorer to a remote Linux server over SSH.

.DESCRIPTION
    Uploads setup.sh (the idempotent server-side provisioner) and, optionally,
    your local dataset.sav to the target server, then runs setup.sh as root.
    setup.sh clones the repo from GitHub, builds the venv with uv, generates the
    runtime base (cache/raw.parquet + cache/raw.csv) from dataset.sav, and
    installs a systemd service (gunicorn --preload, so workers share one
    copy-on-write base DataFrame) + nginx site so the app auto-starts on boot.

    Requires the OpenSSH client (ssh.exe / scp.exe), which ships with Windows 11.
    The SSH user must be able to run sudo on the server.

.EXAMPLE
    # First deploy - push code + data, provision everything:
    .\deploy.ps1 -Server ubuntu@203.0.113.10 -DatasetPath ..\dataset.sav `
                 -ServerName explorer.example.edu

.EXAMPLE
    # Redeploy latest code (data already on the server):
    .\deploy.ps1 -Server ubuntu@203.0.113.10

.EXAMPLE
    # Use a specific SSH key and warm the per-column cache:
    .\deploy.ps1 -Server ubuntu@203.0.113.10 -SshKey ~\.ssh\id_ed25519 -WarmCache
#>
[CmdletBinding()]
param(
    # user@host (or just host) of the target server.
    [Parameter(Mandatory = $true)]
    [string]$Server,

    # Path to your local dataset.sav. Uploaded only if provided and the server
    # doesn't already have data. Omit on redeploys.
    [string]$DatasetPath,

    # Path to an SSH private key (passed to ssh/scp -i). Optional.
    [string]$SshKey,

    # nginx server_name (your domain). Defaults to catch-all on the server.
    [string]$ServerName = "_",

    # Git branch/tag to deploy.
    [string]$GitRef = "main",

    # Override the repo URL if you fork it.
    [string]$RepoUrl = "https://github.com/RobotsLoveWater/Crime_dot_Education.git",

    # Unprivileged service user created on the server.
    [string]$AppUser = "crimeedu",

    # Pre-warm per-column stats during deploy (slow; regenerates on demand anyway).
    [switch]$WarmCache
)

$ErrorActionPreference = "Stop"

# --- locate ssh/scp and the setup script -----------------------------------
foreach ($tool in "ssh", "scp") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "'$tool' not found. Install the Windows OpenSSH client (Settings > Optional Features)."
    }
}

$scriptDir = $PSScriptRoot
$setupSh   = Join-Path $scriptDir "setup.sh"
if (-not (Test-Path $setupSh)) { throw "Cannot find setup.sh next to this script ($setupSh)." }

# Build the -i key arg (as an array so empty = no arg).
$keyArgs = @()
if ($SshKey) {
    if (-not (Test-Path $SshKey)) { throw "SSH key not found: $SshKey" }
    $keyArgs = @("-i", $SshKey)
}

function Invoke-Scp {
    param([string]$LocalPath, [string]$RemotePath)
    Write-Host "==> Uploading $LocalPath -> ${Server}:$RemotePath" -ForegroundColor Cyan
    & scp @keyArgs $LocalPath "${Server}:$RemotePath"
    if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE)." }
}

function Invoke-Ssh {
    param([string]$Command)
    & ssh @keyArgs -t $Server $Command
    if ($LASTEXITCODE -ne 0) { throw "Remote command failed (exit $LASTEXITCODE)." }
}

# --- 1. upload setup.sh (strip CRLF so bash on Linux is happy) --------------
# Write UTF-8 *without* a BOM: Windows PowerShell 5.1's `Set-Content -Encoding utf8`
# prepends a BOM, which lands on line 1 and breaks the shebang (bash: line 1:
# '<BOM>#!/usr/bin/env': No such file or directory). WriteAllText with an explicit
# no-BOM encoding avoids it.
$tmpSetup = Join-Path $env:TEMP "cde-setup.sh"
$setupBody = (Get-Content -Raw $setupSh) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($tmpSetup, $setupBody, (New-Object System.Text.UTF8Encoding($false)))
Invoke-Scp -LocalPath $tmpSetup -RemotePath "/tmp/cde-setup.sh"
Remove-Item $tmpSetup -Force

# --- 2. upload dataset.sav if provided --------------------------------------
if ($DatasetPath) {
    if (-not (Test-Path $DatasetPath)) { throw "DatasetPath not found: $DatasetPath" }
    $sizeMB = [math]::Round((Get-Item $DatasetPath).Length / 1MB, 1)
    Write-Host "==> dataset.sav is ${sizeMB} MB - upload may take a while." -ForegroundColor Yellow
    Invoke-Scp -LocalPath $DatasetPath -RemotePath "/tmp/dataset.sav"
}

# --- 3. run the provisioner as root -----------------------------------------
# Pass config as environment assignments to sudo (sudoers env_reset preserves
# variables set on the command line). Single-quote values for the remote shell.
$warm = if ($WarmCache) { "yes" } else { "no" }
$envAssignments = @(
    "REPO_URL='$RepoUrl'"
    "GIT_REF='$GitRef'"
    "APP_USER='$AppUser'"
    "SERVER_NAME='$ServerName'"
    "WARM_CACHE='$warm'"
) -join " "

$remoteCmd = "sudo $envAssignments bash /tmp/cde-setup.sh"
Write-Host "==> Running provisioner on $Server" -ForegroundColor Cyan
Write-Host "    $remoteCmd" -ForegroundColor DarkGray
Invoke-Ssh -Command $remoteCmd

Write-Host "`n==> Done. Check the service with:  ssh $Server 'systemctl status crime-education'" -ForegroundColor Green
