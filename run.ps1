<#
.SYNOPSIS
Runs the Minnesota Sentencing Explorer locally.

.DESCRIPTION
Starts the Flask development server through the repository's pinned uv environment.
The script resolves all paths from its own location, so it can be invoked from any
PowerShell working directory. A repository-local, git-ignored uv cache avoids relying
on machine-specific global cache state.

.EXAMPLE
.\run.ps1

.EXAMPLE
.\run.ps1 -Debug -Port 5050
#>
[CmdletBinding()]
param(
    [Parameter()]
    [ValidateRange(1, 65535)]
    [int]$Port = 5000,

    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string]$BindAddress = '127.0.0.1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$projectFile = Join-Path $projectRoot 'pyproject.toml'
$uvCache = Join-Path $projectRoot '.uv-cache'
# CmdletBinding supplies PowerShell's common -Debug switch. Reuse it instead of
# declaring a second parameter with the same name, then translate it to Flask's flag.
$flaskDebug = $PSBoundParameters.ContainsKey('Debug') -and [bool]$PSBoundParameters['Debug']

if (-not (Test-Path -LiteralPath $projectFile -PathType Leaf)) {
    throw "Could not find pyproject.toml beside run.ps1: $projectFile"
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    throw "uv is required. Install it with 'winget install astral-sh.uv', then run this script again."
}

$uvArguments = @(
    '--cache-dir', $uvCache,
    'run',
    'flask',
    '--app', 'app',
    'run',
    '--host', $BindAddress,
    '--port', $Port.ToString()
)
if ($flaskDebug) {
    $uvArguments += '--debug'
}

$scheme = 'http'
Write-Host "Starting Minnesota Sentencing Explorer at ${scheme}://${BindAddress}:$Port" -ForegroundColor Cyan
if ($flaskDebug) {
    Write-Host 'Flask debug mode is enabled.' -ForegroundColor Yellow
}

$serverExitCode = 0
Push-Location -LiteralPath $projectRoot
try {
    & $uvCommand.Source @uvArguments
    $serverExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $serverExitCode
