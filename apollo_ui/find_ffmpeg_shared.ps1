$ErrorActionPreference = "SilentlyContinue"

$roots = New-Object System.Collections.Generic.List[string]

function Add-Root([string]$p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return }
    try {
        $expanded = [Environment]::ExpandEnvironmentVariables($p)
        if (-not [string]::IsNullOrWhiteSpace($expanded) -and -not $roots.Contains($expanded)) {
            $roots.Add($expanded)
        }
    } catch {}
}

# WinGet portable package roots.
Add-Root "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
Add-Root "$env:ProgramFiles\WinGet\Packages"
if (${env:ProgramFiles(x86)}) {
    Add-Root "${env:ProgramFiles(x86)}\WinGet\Packages"
}

# Common alternate locations.
Add-Root "$env:LOCALAPPDATA\Programs"
Add-Root "$env:USERPROFILE\scoop\apps\ffmpeg-shared"
Add-Root "$env:USERPROFILE\scoop\apps\ffmpeg"
Add-Root "C:\ffmpeg"
Add-Root "$env:ProgramFiles\ffmpeg"

# Current PATH entries may already point directly at the correct DLL folder.
($env:PATH -split ';') | ForEach-Object { Add-Root $_ }

function Is-SharedBin([string]$dir) {
    if ([string]::IsNullOrWhiteSpace($dir)) { return $false }
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { return $false }

    $codec = Get-ChildItem -LiteralPath $dir -Filter 'avcodec-*.dll' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    $format = Get-ChildItem -LiteralPath $dir -Filter 'avformat-*.dll' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    $util = Get-ChildItem -LiteralPath $dir -Filter 'avutil-*.dll' -File -ErrorAction SilentlyContinue | Select-Object -First 1

    return ($null -ne $codec -and $null -ne $format -and $null -ne $util)
}

# Fast path.
foreach ($root in $roots) {
    if (Is-SharedBin $root) {
        [Console]::Out.WriteLine((Resolve-Path -LiteralPath $root).Path)
        exit 0
    }
}

# Recursive search, narrowed to Gyan shared package folders in WinGet roots.
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }

    $searchRoots = @($root)
    if ($root -like '*WinGet\Packages*') {
        $gyanDirs = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like 'Gyan.FFmpeg.Shared*' }
        if ($gyanDirs) {
            $searchRoots = @($gyanDirs.FullName)
        }
    }

    foreach ($searchRoot in $searchRoots) {
        $matches = Get-ChildItem -LiteralPath $searchRoot -Filter 'avcodec-*.dll' -File -Recurse -ErrorAction SilentlyContinue
        foreach ($match in $matches) {
            $candidate = $match.Directory.FullName
            if (Is-SharedBin $candidate) {
                [Console]::Out.WriteLine((Resolve-Path -LiteralPath $candidate).Path)
                exit 0
            }
        }
    }
}

exit 1
