<#
Self-contained tests for scripts/reset-instance.ps1.  Run with:
  powershell -ExecutionPolicy Bypass -File tests/scripts/reset-instance.Tests.ps1

This deliberately does not require Pester, so a clean checkout can validate the
utility without installing another PowerShell module.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot '..\..\scripts\reset-instance.ps1'
$scriptPath = [System.IO.Path]::GetFullPath($scriptPath)
$testRoot = Join-Path $PSScriptRoot (".reset-instance-fixture-{0}" -f [guid]::NewGuid().ToString('N'))

function Assert-True {
    param([Parameter(Mandatory = $true)][bool]$Condition, [Parameter(Mandatory = $true)][string]$Message)
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

function New-Fixture {
    param([Parameter(Mandatory = $true)][string]$Root)

    $instanceRoot = Join-Path $Root 'instance'
    $archiveRoot = Join-Path $Root 'archives'
    New-Item -ItemType Directory -Path (Join-Path $instanceRoot 'user\student-a') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $instanceRoot 'classes') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $instanceRoot 'cache\data') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $instanceRoot 'user\student-a\student-a.pkl') -Value 'account'
    Set-Content -LiteralPath (Join-Path $instanceRoot 'user\student-a\student-a.attempts.jsonl') -Value '{"attempt":1}'
    Set-Content -LiteralPath (Join-Path $instanceRoot 'classes\class-a.json') -Value '{"class_id":"class-a"}'
    Set-Content -LiteralPath (Join-Path $instanceRoot 'cache\data\_data.bin') -Value 'cache survives'
    return [pscustomobject]@{ InstanceRoot = $instanceRoot; ArchiveRoot = $archiveRoot }
}

try {
    $fixture = New-Fixture -Root $testRoot
    $cacheFile = Join-Path $fixture.InstanceRoot 'cache\data\_data.bin'
    $cacheBefore = Get-FileHash -LiteralPath $cacheFile -Algorithm SHA256

    & $scriptPath -InstanceRoot $fixture.InstanceRoot -ArchiveRoot $fixture.ArchiveRoot -WhatIf
    Assert-True (Test-Path -LiteralPath (Join-Path $fixture.InstanceRoot 'user\student-a\student-a.pkl')) 'WhatIf must not move user data.'
    Assert-True (-not (Test-Path -LiteralPath $fixture.ArchiveRoot)) 'WhatIf must not create an archive root.'

    $result = & $scriptPath -InstanceRoot $fixture.InstanceRoot -ArchiveRoot $fixture.ArchiveRoot -Force
    Assert-True (Test-Path -LiteralPath $result.ArchivePath) 'The archive directory must be created.'
    Assert-True (Test-Path -LiteralPath (Join-Path $result.ArchivePath 'user\student-a\student-a.attempts.jsonl')) 'Attempt logs must be archived with user data.'
    Assert-True (Test-Path -LiteralPath (Join-Path $result.ArchivePath 'classes\class-a.json')) 'Class files must be archived.'
    Assert-True (Test-Path -LiteralPath (Join-Path $result.ArchivePath 'manifest.json')) 'A manifest must be written.'
    Assert-True (@(Get-ChildItem -LiteralPath (Join-Path $fixture.InstanceRoot 'user') -Force).Count -eq 0) 'The new user directory must be empty.'
    Assert-True (@(Get-ChildItem -LiteralPath (Join-Path $fixture.InstanceRoot 'classes') -Force).Count -eq 0) 'The new classes directory must be empty.'
    $cacheAfter = Get-FileHash -LiteralPath $cacheFile -Algorithm SHA256
    Assert-True ($cacheBefore.Hash -eq $cacheAfter.Hash) 'The cache must be unchanged.'

    $manifest = Get-Content -LiteralPath (Join-Path $result.ArchivePath 'manifest.json') -Raw | ConvertFrom-Json
    Assert-True ($manifest.cache.excluded -eq $true) 'The manifest must state that cache was excluded.'
    Assert-True ($manifest.archived.user.files -eq 2) 'The manifest must count user files.'
    Assert-True ($manifest.archived.classes.files -eq 1) 'The manifest must count class files.'

    # A second reset in the same second must make a separate archive rather than
    # overwriting the first one.
    $secondResult = & $scriptPath -InstanceRoot $fixture.InstanceRoot -ArchiveRoot $fixture.ArchiveRoot -Force
    Assert-True ($secondResult.ArchivePath -ne $result.ArchivePath) 'Repeated resets must never overwrite an archive.'
    Assert-True (Test-Path -LiteralPath $result.ArchivePath) 'The first archive must remain intact.'

    # Inject a failure in the second move through PowerShell command resolution.
    # The production script has no test-only switch; its catch block must restore
    # the first moved tree before surfacing the failure.
    $rollbackFixture = New-Fixture -Root (Join-Path $testRoot 'rollback')
    $script:moveInvocation = 0
    function global:Move-Item {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory = $true)][string]$LiteralPath,
            [Parameter(Mandatory = $true)][string]$Destination
        )
        $script:moveInvocation++
        if ($script:moveInvocation -eq 2) { throw 'simulated classes move failure' }
        Microsoft.PowerShell.Management\Move-Item @PSBoundParameters
    }
    $rollbackFailed = $false
    try { & $scriptPath -InstanceRoot $rollbackFixture.InstanceRoot -ArchiveRoot $rollbackFixture.ArchiveRoot -Force } catch { $rollbackFailed = $true }
    Remove-Item -LiteralPath Function:\global:Move-Item -Force
    Assert-True $rollbackFailed 'A simulated move failure must surface as an error.'
    Assert-True (Test-Path -LiteralPath (Join-Path $rollbackFixture.InstanceRoot 'user\student-a\student-a.pkl')) 'Rollback must restore user data.'
    Assert-True (Test-Path -LiteralPath (Join-Path $rollbackFixture.InstanceRoot 'classes\class-a.json')) 'Rollback must retain class data.'

    $badRoot = Join-Path $testRoot 'bad-root'
    New-Item -ItemType Directory -Path $badRoot | Out-Null
    $badExit = $false
    try { & $scriptPath -InstanceRoot $badRoot -ArchiveRoot (Join-Path $testRoot 'bad-archives') -Force } catch { $badExit = $true }
    Assert-True $badExit 'A root without the expected state layout must be rejected.'

    Write-Output 'reset-instance tests passed.'
}
finally {
    if (Test-Path -LiteralPath Function:\global:Move-Item) {
        Remove-Item -LiteralPath Function:\global:Move-Item -Force
    }
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
