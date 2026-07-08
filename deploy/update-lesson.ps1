<#
.SYNOPSIS
    Push a single updated lesson JSON to the running server (targeted bugfix update).

.DESCRIPTION
    Uploads one lessons/<id>.json file to the deployed app and drops it into place,
    owned by the service user. Lessons are read fresh from disk on every request
    (lessons.get_module), so the change is live immediately - NO redeploy, rebuild,
    or service restart is required.

    Safety: a malformed lesson breaks the whole catalog (get_module AND list_modules
    validate on load), so this script validates the file locally before upload and
    then again on the server (with the deployed app's own lessons.validate) BEFORE
    moving it into place. If validation fails, the live file is left untouched.

    Requires the OpenSSH client (ssh.exe / scp.exe, bundled with Windows 11) and an
    SSH user that can sudo on the server.

.EXAMPLE
    # Ship the fixed intro-descriptive-stats lesson:
    .\update-lesson.ps1 -Server ubuntu@203.0.113.10

.EXAMPLE
    # A different lesson file, with an explicit key:
    .\update-lesson.ps1 -Server ubuntu@203.0.113.10 -SshKey ~\.ssh\id_ed25519 `
                        -LessonFile ..\lessons\intro-explorer-basics.json
#>
[CmdletBinding()]
param(
    # user@host (or just host) of the target server.
    [Parameter(Mandatory = $true)]
    [string]$Server,

    # Path to an SSH private key (passed to ssh/scp -i). Optional.
    [string]$SshKey,

    # The lesson JSON to upload. Defaults to the one this update fixes.
    [string]$LessonFile = (Join-Path $PSScriptRoot "..\lessons\intro-descriptive-stats.json"),

    # Service user + app name on the server (must match your setup.sh deploy).
    [string]$AppUser = "crimeedu",
    [string]$AppName = "crime-education",

    # Full app dir override (defaults to /home/<AppUser>/<AppName>).
    [string]$AppDir
)

$ErrorActionPreference = "Stop"

if (-not $AppDir) { $AppDir = "/home/$AppUser/$AppName" }

# --- tools ------------------------------------------------------------------
foreach ($tool in "ssh", "scp") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "'$tool' not found. Install the Windows OpenSSH client (Settings > Optional Features)."
    }
}

# --- resolve + locally validate the lesson file -----------------------------
if (-not (Test-Path $LessonFile)) { throw "Lesson file not found: $LessonFile" }
$LessonFile = (Resolve-Path $LessonFile).Path
$fileName = Split-Path -Leaf $LessonFile
if ($fileName -notmatch '\.json$') { throw "Expected a .json lesson file, got: $fileName" }
$stem = $fileName -replace '\.json$', ''

# Parseable JSON + id must equal the filename stem, or list_modules/get_module reject it.
try {
    $json = Get-Content -Raw -LiteralPath $LessonFile | ConvertFrom-Json
}
catch {
    throw "Local JSON is invalid ($fileName): $($_.Exception.Message)"
}
if ($json.id -ne $stem) {
    throw "Lesson 'id' ('$($json.id)') must equal the filename stem ('$stem'), or the catalog will fail to load."
}
Write-Host "==> Local check OK: $fileName (id=$($json.id))" -ForegroundColor Green

# --- ssh key arg ------------------------------------------------------------
$keyArgs = @()
if ($SshKey) {
    if (-not (Test-Path $SshKey)) { throw "SSH key not found: $SshKey" }
    $keyArgs = @("-i", $SshKey)
}

$stage  = "/tmp/$fileName"
$target = "$AppDir/lessons/$fileName"

# --- 1. upload to a staging path --------------------------------------------
Write-Host "==> Uploading $fileName -> ${Server}:$stage" -ForegroundColor Cyan
& scp @keyArgs $LessonFile "${Server}:$stage"
if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE)." }

# --- 2. validate on the server, then install into place ---------------------
# The remote script is base64-encoded to avoid all shell-quoting pitfalls, then
# run under `sudo bash` (sudo can prompt on the -t tty). It validates the staged
# file with the DEPLOYED app's own validator before overwriting the live file.
$remoteScript = @"
set -euo pipefail
cd '$AppDir'
'$AppDir/.venv/bin/python' -c "import json, lessons; m = json.load(open('$stage')); lessons.validate(m); assert m['id'] == '$stem', 'lesson id must equal $stem'; print('server validation OK: ' + str(m['id']))"
install -o '$AppUser' -g '$AppUser' -m 644 '$stage' '$target'
rm -f '$stage'
echo 'installed: $target'
"@
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($remoteScript -replace "`r`n", "`n")))

Write-Host "==> Validating on server and installing into place" -ForegroundColor Cyan
& ssh @keyArgs -t $Server "echo $b64 | base64 -d | sudo bash"
if ($LASTEXITCODE -ne 0) {
    throw "Remote update failed (exit $LASTEXITCODE). The live lesson was NOT changed; staged copy may remain at $stage."
}

Write-Host "`n==> Done. $fileName is live. Lessons are read per-request, so no restart is needed." -ForegroundColor Green
