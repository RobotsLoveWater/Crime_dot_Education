<#
.SYNOPSIS
Archives the development instance state and starts with empty user and class stores.

.DESCRIPTION
Moves the complete user/ and classes/ directories into a timestamped archive, then
recreates them as empty directories.  The cache, dataset, and authored lessons are
never moved or deleted.  By default this script supports the repository's current
legacy layout, where user/, classes/, and cache/ live at the repository root.

Use -InstanceRoot when those three state directories have moved to a future
instance directory.  All paths are resolved from this script's location rather
than from the current PowerShell working directory.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter()]
    [string]$InstanceRoot = (Join-Path $PSScriptRoot '..'),

    [Parameter()]
    [string]$ArchiveRoot = (Join-Path (Join-Path $PSScriptRoot '..') 'instance-archives'),

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$scriptProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Resolve-FullPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [switch]$MustExist
    )

    # Relative parameters deliberately resolve from the repository containing this
    # script, never from the caller's current working directory.
    $candidatePath = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $scriptProjectRoot $Path }
    $fullPath = [System.IO.Path]::GetFullPath($candidatePath)
    if ($MustExist -and -not (Test-Path -LiteralPath $fullPath)) {
        throw "$Name does not exist: $fullPath"
    }
    return $fullPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
}

function Test-ChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Parent,

        [Parameter(Mandatory = $true)]
        [string]$Child
    )

    $parentWithSeparator = $Parent.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    return $Child.StartsWith($parentWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) {
        throw "$Name must be a directory: $Path"
    }
}

function Get-TreeCounts {
    param([Parameter(Mandatory = $true)][string]$Path)

    $items = @(Get-ChildItem -LiteralPath $Path -Force -Recurse)
    return [ordered]@{
        files = @($items | Where-Object { -not $_.PSIsContainer }).Count
        directories = @($items | Where-Object { $_.PSIsContainer }).Count
    }
}

function Get-GitCommit {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    try {
        $commit = & git -C $ProjectRoot rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0) {
            return ($commit | Select-Object -First 1).Trim()
        }
    }
    catch {
        # A source archive need not be a Git checkout for the reset itself to be safe.
    }
    return $null
}

function Remove-EmptyDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        $remaining = @(Get-ChildItem -LiteralPath $Path -Force)
        if ($remaining.Count -ne 0) {
            throw "Refusing to remove non-empty rollback directory: $Path"
        }
        Remove-Item -LiteralPath $Path -Force
    }
}

$projectRoot = Resolve-FullPath -Path (Join-Path $PSScriptRoot '..') -Name 'Project root' -MustExist
$instanceRootPath = Resolve-FullPath -Path $InstanceRoot -Name 'Instance root' -MustExist
$archiveRootPath = Resolve-FullPath -Path $ArchiveRoot -Name 'Archive root'

Assert-Directory -Path $projectRoot -Name 'Project root'
Assert-Directory -Path $instanceRootPath -Name 'Instance root'

# The legacy layout deliberately uses the project root as its instance root.  Any
# other location must be beneath this checkout, which keeps a typo from moving an
# unrelated directory elsewhere on the machine.
if (-not $instanceRootPath.Equals($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not (Test-ChildPath -Parent $projectRoot -Child $instanceRootPath)) {
    throw "Instance root must be this project root or a directory beneath it: $instanceRootPath"
}
if (-not (Test-ChildPath -Parent $projectRoot -Child $archiveRootPath)) {
    throw "Archive root must be a directory beneath this project: $archiveRootPath"
}

# Refuse drive roots and source locations that do not have the expected state shape.
$filesystemRoot = [System.IO.Path]::GetPathRoot($instanceRootPath).TrimEnd([char]'\', [char]'/' )
$trimmedInstanceRoot = $instanceRootPath.TrimEnd([char]'\', [char]'/' )
if ($filesystemRoot -eq $trimmedInstanceRoot) {
    throw "Instance root must not be a filesystem root: $instanceRootPath"
}

$userPath = Join-Path $instanceRootPath 'user'
$classesPath = Join-Path $instanceRootPath 'classes'
$cachePath = Join-Path $instanceRootPath 'cache'

foreach ($statePath in @($userPath, $classesPath, $cachePath)) {
    if (-not (Test-ChildPath -Parent $instanceRootPath -Child $statePath)) {
        throw "Refusing an unsafe state path outside the instance root: $statePath"
    }
    if (-not (Test-Path -LiteralPath $statePath)) {
        throw "Expected state directory does not exist: $statePath"
    }
    Assert-Directory -Path $statePath -Name 'State directory'
}

# Archives must never be placed inside the trees this script moves, nor may they be a
# source directory themselves.  This protects against accidental self-archiving.
foreach ($sourcePath in @($userPath, $classesPath, $cachePath)) {
    if ($archiveRootPath.Equals($sourcePath, [System.StringComparison]::OrdinalIgnoreCase) -or
        (Test-ChildPath -Parent $sourcePath -Child $archiveRootPath)) {
        throw "Archive root must not be inside a state directory: $archiveRootPath"
    }
}

$timestamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
$archivePath = Join-Path $archiveRootPath "instance-$timestamp"
$sequence = 1
while (Test-Path -LiteralPath $archivePath) {
    $archivePath = Join-Path $archiveRootPath ("instance-{0}-{1:d2}" -f $timestamp, $sequence)
    $sequence++
}

$userCounts = Get-TreeCounts -Path $userPath
$classesCounts = Get-TreeCounts -Path $classesPath
$originalConfirmPreference = $ConfirmPreference
if ($Force) {
    # -WhatIf still takes precedence in ShouldProcess; -Force only suppresses a prompt.
    $ConfirmPreference = 'None'
}

$movedUser = $false
$movedClasses = $false
$createdUser = $false
$createdClasses = $false

try {
    $operation = "archive user/ and classes/ to $archivePath, then recreate empty directories (cache excluded)"
    if (-not $PSCmdlet.ShouldProcess($instanceRootPath, $operation)) {
        return
    }

    New-Item -ItemType Directory -Path $archiveRootPath -Force | Out-Null
    New-Item -ItemType Directory -Path $archivePath -ErrorAction Stop | Out-Null

    Move-Item -LiteralPath $userPath -Destination (Join-Path $archivePath 'user') -ErrorAction Stop
    $movedUser = $true

    Move-Item -LiteralPath $classesPath -Destination (Join-Path $archivePath 'classes') -ErrorAction Stop
    $movedClasses = $true

    New-Item -ItemType Directory -Path $userPath -ErrorAction Stop | Out-Null
    $createdUser = $true
    New-Item -ItemType Directory -Path $classesPath -ErrorAction Stop | Out-Null
    $createdClasses = $true

    $manifest = [ordered]@{
        timestamp = (Get-Date).ToString('o')
        archive_path = $archivePath
        instance_root = $instanceRootPath
        sources = [ordered]@{
            user = $userPath
            classes = $classesPath
        }
        archived = [ordered]@{
            user = $userCounts
            classes = $classesCounts
        }
        git_commit = Get-GitCommit -ProjectRoot $projectRoot
        cache = [ordered]@{
            excluded = $true
            path = $cachePath
        }
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $archivePath 'manifest.json') -Encoding utf8 -NoNewline

    [pscustomobject]@{
        ArchivePath = $archivePath
        UserFiles = $userCounts.files
        UserDirectories = $userCounts.directories
        ClassFiles = $classesCounts.files
        ClassDirectories = $classesCounts.directories
        CacheExcluded = $true
    }
}
catch {
    $originalError = $_
    $rollbackErrors = [System.Collections.Generic.List[string]]::new()

    # A provider can report an error after completing a move. Detect that state
    # from the filesystem as well as from the flags set after each successful call.
    $archivedUserPath = Join-Path $archivePath 'user'
    $archivedClassesPath = Join-Path $archivePath 'classes'
    if (-not $movedUser -and (Test-Path -LiteralPath $archivedUserPath) -and -not (Test-Path -LiteralPath $userPath)) {
        $movedUser = $true
    }
    if (-not $movedClasses -and (Test-Path -LiteralPath $archivedClassesPath) -and -not (Test-Path -LiteralPath $classesPath)) {
        $movedClasses = $true
    }

    try {
        if ($createdClasses) { Remove-EmptyDirectory -Path $classesPath }
        if ($createdUser) { Remove-EmptyDirectory -Path $userPath }
        if ($movedClasses) { Move-Item -LiteralPath $archivedClassesPath -Destination $classesPath -ErrorAction Stop }
        if ($movedUser) { Move-Item -LiteralPath $archivedUserPath -Destination $userPath -ErrorAction Stop }
    }
    catch {
        $rollbackErrors.Add($_.Exception.Message)
    }

    if ($rollbackErrors.Count -gt 0) {
        throw "Reset failed: $($originalError.Exception.Message) Rollback also failed: $($rollbackErrors -join '; ')"
    }
    throw $originalError
}
finally {
    $ConfirmPreference = $originalConfirmPreference
}
