# Apollo 8 manual code-only patch installer; not the Ed25519-signed updater.
param([string]$ApolloPath = "F:\Apollo\apollo 1\apollo_ui")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $packageRoot "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Missing manifest.json. Extract the entire ZIP before running this installer."
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.version -ne "8.0.0.0" -or @($manifest.files).Count -lt 1) {
    throw "Not an Apollo 8.0.0.0 manual code patch."
}
Write-Host ""
Write-Host "APOLLO 8 MANUAL CODE PATCH" -ForegroundColor Cyan
Write-Host "Only source code is replaced. Models, voices, memory, storage and Python environments are preserved."
Write-Host "This package is NOT Ed25519-signed and is NOT accepted by Apollo's signed in-app updater." -ForegroundColor Yellow
Write-Host "Close Apollo before proceeding."
Write-Host ""
$typedPath = Read-Host "Installation directory [$ApolloPath]"
if (-not [string]::IsNullOrWhiteSpace($typedPath)) { $ApolloPath = $typedPath.Trim('"') }
if (-not (Test-Path -LiteralPath $ApolloPath -PathType Container)) {
    throw "Apollo installation directory not found: $ApolloPath"
}
$targetRoot = (Resolve-Path -LiteralPath $ApolloPath).Path
foreach ($name in @("main.py", "config.json", "modules\reasoning_director\module.py")) {
    if (-not (Test-Path -LiteralPath (Join-Path $targetRoot $name) -PathType Leaf)) {
        throw "This does not look like the Apollo app directory. Missing $name"
    }
}
$installedConfig = Get-Content -LiteralPath (Join-Path $targetRoot "config.json") -Raw | ConvertFrom-Json
if ($installedConfig.version -ne "7.5.13.10" -and $installedConfig.version -ne "8.0.0.0") {
    throw "Expected Apollo 7.5.13.10 or 8.0.0.0. Found $($installedConfig.version). Update to the baseline first."
}
$checks = New-Object System.Collections.ArrayList
$seen = @{}
foreach ($entry in @($manifest.files)) {
    $rel = [string]$entry.path
    if ($rel -notmatch '^[A-Za-z0-9_./-]+$' -or $rel.StartsWith("/") -or $rel.Contains("..") -or $seen.ContainsKey($rel.ToLowerInvariant())) {
        throw "Invalid or duplicate patch path: $rel"
    }
    if ($rel -match '(^|/)(storage|workspace|\.venv|models|Audio)(/|$)') {
        throw "Refusing to modify private/runtime data: $rel"
    }
    $seen[$rel.ToLowerInvariant()] = $true
    $relativeFile = $rel.Replace("/", "\")
    $sourceFile = Join-Path (Join-Path $packageRoot "payload") $relativeFile
    $targetFile = Join-Path $targetRoot $relativeFile
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Missing package file: $rel"
    }
    $expectedSha = ([string]$entry.sha256).ToLowerInvariant()
    $actualSha = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) {
        throw "Package checksum failed for $rel. Download it again."
    }
    $oldSha = if ($null -eq $entry.old_sha256) { "" } else { ([string]$entry.old_sha256).ToLowerInvariant() }
    $exists = Test-Path -LiteralPath $targetFile -PathType Leaf
    $currentSha = if ($exists) {
        (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { "" }
    if ($currentSha -ne $expectedSha -and $currentSha -ne $oldSha) {
        if ($exists -or $oldSha -ne "") {
            throw "Local edits or different baseline in $rel. No files changed."
        }
    }
    [void]$checks.Add([PSCustomObject]@{
        Relative = $relativeFile
        Source = $sourceFile
        Destination = $targetFile
        NeedsUpdate = ($currentSha -ne $expectedSha)
        Existed = $exists
        ExpectedSha = $expectedSha
    })
}
$toUpdate = @($checks | Where-Object { $_.NeedsUpdate })
if ($toUpdate.Count -eq 0) {
    Write-Host "Apollo 8 code is already installed. Nothing changed." -ForegroundColor Green
    exit 0
}
Write-Host ("Preflight passed. {0} files need updating." -f $toUpdate.Count) -ForegroundColor Green
Write-Host "A backup will be written to Apollo's storage/backups directory."
$answer = Read-Host "Type UPDATE to back up and install Apollo 8"
if ($answer -cne "UPDATE") {
    Write-Host "Cancelled. No files changed."
    exit 2
}
$backupRoot = Join-Path $targetRoot ("storage\backups\manual_v8_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$applied = New-Object System.Collections.ArrayList
try {
    foreach ($file in $toUpdate) {
        if ($file.Existed) {
            $savedFile = Join-Path $backupRoot $file.Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $savedFile) | Out-Null
            Copy-Item -LiteralPath $file.Destination -Destination $savedFile -Force
        }
    }
    foreach ($file in $toUpdate) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file.Destination) | Out-Null
        $tempFile = "$($file.Destination).apollo_v8_tmp"
        try {
            Copy-Item -LiteralPath $file.Source -Destination $tempFile -Force
            Move-Item -LiteralPath $tempFile -Destination $file.Destination -Force
            [void]$applied.Add($file)
        } finally {
            if (Test-Path -LiteralPath $tempFile -PathType Leaf) {
                Remove-Item -LiteralPath $tempFile -Force
            }
        }
        $writtenSha = (Get-FileHash -LiteralPath $file.Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($writtenSha -ne $file.ExpectedSha) {
            throw "Post-install checksum mismatch for $($file.Relative)."
        }
    }
    $pythonPath = Join-Path $targetRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $pythonPath -PathType Leaf) {
        $pyFiles = @(
            (Join-Path $targetRoot "main.py"),
            (Join-Path $targetRoot "apollo_learning_v8.py"),
            (Join-Path $targetRoot "modules\reasoning_director\module.py"),
            (Join-Path $targetRoot "modules\self_improvement_lab\module.py")
        )
        & $pythonPath -m py_compile @pyFiles
        if ($LASTEXITCODE -ne 0) { throw "Python syntax validation failed; rolling back." }
    }
    Write-Host ""
    Write-Host "APOLLO 8 CODE PATCH INSTALLED SUCCESSFULLY" -ForegroundColor Green
    Write-Host "Backup folder: $backupRoot"
    Write-Host "Restart Apollo to load the new modules."
    exit 0
} catch {
    Write-Warning ("Install failed: " + $_.Exception.Message)
    Write-Warning "Restoring modified files from backup."
    foreach ($file in @($applied)) {
        $savedFile = Join-Path $backupRoot $file.Relative
        if ($file.Existed -and (Test-Path -LiteralPath $savedFile -PathType Leaf)) {
            Copy-Item -LiteralPath $savedFile -Destination $file.Destination -Force
        } elseif (-not $file.Existed -and (Test-Path -LiteralPath $file.Destination -PathType Leaf)) {
            Remove-Item -LiteralPath $file.Destination -Force
        }
    }
    throw
}
