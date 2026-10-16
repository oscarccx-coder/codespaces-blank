# Apollo Foundry Docker setup helper. Windows PowerShell 5.1 compatible.
# Explicit user consent is required for installation, downloaded installers,
# starting Docker Desktop, and building the trusted image.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('InstallDocker','BuildImage')]
    [string] $Action
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:TranscriptStarted = $false
$script:LogDir = Join-Path $env:LOCALAPPDATA 'Apollo\setup_logs'
$script:LogFile = Join-Path $script:LogDir ('foundry_' + $Action.ToLowerInvariant() + '.log')

function Say([string] $Message) { Write-Host $Message }
function Confirm-Action([string] $Prompt) {
    $answer = Read-Host ($Prompt + ' [Y/N]')
    return $answer -match '^(?i:y|yes)$'
}
function Find-DockerCli {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Docker Desktop\resources\bin\docker.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')
    )) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    }
    return $null
}
function Find-DockerDesktop {
    foreach ($path in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Docker Desktop\Docker Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
    )) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    }
    return $null
}
function Docker-Engine-Ready([string] $Cli) {
    if (-not $Cli) { return $false }
    try {
        $null = & $Cli info --format '{{.OSType}}' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
function Show-Requirements {
    Say ''
    Say 'Checking Windows, WSL, virtualization, and disk space...'
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        Say ('Windows: ' + $os.Caption + ' (build ' + $os.BuildNumber + ')')
        $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
        Say ('Firmware virtualization enabled: ' + $cpu.VirtualizationFirmwareEnabled)
        if ($cpu.VirtualizationFirmwareEnabled -eq $false) {
            Say '[ACTION] Enable AMD SVM / Intel VT-x in UEFI/BIOS.'
        }
    } catch { Say ('[INFO] Could not inspect system firmware: ' + $_.Exception.Message) }
    try {
        $free = (Get-PSDrive -Name $env:SystemDrive.TrimEnd(':') -ErrorAction Stop).Free
        Say ('Free space on ' + $env:SystemDrive + ': ' + [math]::Round($free / 1GB, 1) + ' GiB')
        if ($free -lt 10GB) {
            Say '[WARNING] Low system-drive space. Docker Desktop and WSL use C: by default.'
            Say 'Free disk space before installing/building an image.'
        }
    } catch { Say '[INFO] Disk-space check unavailable.' }
    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        Say 'WSL version:'
        try { & wsl.exe --version 2>&1 | Out-Host }
        catch { Say ('[WARNING] WSL version could not be read: ' + $_.Exception.Message) }
        Say 'WSL status:'
        try { & wsl.exe --status 2>&1 | Out-Host }
        catch { Say ('[WARNING] WSL status check failed: ' + $_.Exception.Message) }
    } else {
        Say '[WARNING] WSL is not available.'
    }
    Say '[ACTION] If WSL is missing, in an elevated terminal run: wsl --install --no-distribution'
    Say '[ACTION] For an existing WSL installation run: wsl --update'
    Say 'A Windows restart may be required. Nothing is changed by these checks.'
}
function Show-FailureLogs {
    Say ''
    Say 'Recent installer evidence (also captured in the Apollo log):'
    foreach ($path in @(
        (Join-Path $env:LOCALAPPDATA 'Docker\install-log.txt'),
        (Join-Path $env:LOCALAPPDATA 'DockerDesktop\install-log.txt'),
        (Join-Path $env:ProgramData 'DockerDesktop\install-log-admin.txt')
    )) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Say ('--- ' + $path)
            try { Get-Content -LiteralPath $path -Tail 25 -ErrorAction Stop | Out-Host }
            catch { Say ('Unable to read: ' + $_.Exception.Message) }
        }
    }
    try {
        Get-WinEvent -FilterHashtable @{ LogName = 'Application'; StartTime = (Get-Date).AddMinutes(-45) } -ErrorAction Stop |
            Where-Object { $_.Message -match 'Docker|Docker Desktop Installer' } |
            Select-Object -First 3 TimeCreated, Id, ProviderName, Message |
            Format-List | Out-Host
    } catch { Say '[INFO] No accessible Docker crash events found.' }
    Say ('Local diagnostic log: ' + $script:LogFile)
}
function Start-Docker-If-Approved([string] $Cli) {
    if (Docker-Engine-Ready $Cli) { return $true }
    $desktop = Find-DockerDesktop
    if (-not $desktop) {
        Say '[ERROR] Docker Desktop application not found in standard install locations.'
        return $false
    }
    if (-not (Confirm-Action 'Start Docker Desktop and check the Linux engine?')) {
        Say '[INFO] Start Docker Desktop yourself and retry when it reports Engine running.'
        return $false
    }
    Say ('Starting: ' + $desktop)
    Start-Process -FilePath $desktop | Out-Null
    Say 'Waiting up to 90 seconds for Docker engine initialization...'
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 3
        $Cli = Find-DockerCli
        if (Docker-Engine-Ready $Cli) { return $true }
    }
    Say '[ERROR] Docker Desktop did not expose a ready engine.'
    Say 'Check Docker Desktop for first-run terms, WSL update/restart, or Linux container mode.'
    return $false
}
function Install-Desktop {
    Show-Requirements
    $cli = Find-DockerCli
    if (Docker-Engine-Ready $cli) {
        Say '[OK] Docker Desktop engine is already running.'
        Say 'Next: run Setup\09_SETUP_FOUNDRY_SANDBOX.bat to build the Foundry image.'
        return 0
    }
    if (Find-DockerDesktop) {
        Say '[INFO] Docker Desktop is installed, but its engine is not responding.'
        if (Start-Docker-If-Approved $cli) {
            Say '[OK] Docker Desktop is now running. Next: Setup\09_SETUP_FOUNDRY_SANDBOX.bat.'
            return 0
        }
        Show-FailureLogs
        return 1
    }
    Say ''
    Say 'Docker Desktop is not found in its standard install locations.'
    Say 'Official downloads: https://docs.docker.com/desktop/setup/install/windows-install/'
    if (-not (Confirm-Action 'Install Docker Desktop using winget (per-user default)?')) {
        Say '[INFO] Installation cancelled. No changes made.'
        return 0
    }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        Say ('Running winget from: ' + $winget.Source)
        & $winget.Source install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements 2>&1 | Out-Host
        $code = $LASTEXITCODE
        Say ('WinGet installer exit code: ' + $code)
    } else {
        Say '[ERROR] WinGet is missing. Use the official download link above.'
        Show-FailureLogs
        return 1
    }
    if ($code -ne 0) {
        Say '[ERROR] Docker Desktop installation returned an error.'
        Show-FailureLogs
        return 1
    }
    if (-not (Find-DockerDesktop) -and -not (Find-DockerCli)) {
        Say '[WARNING] Installer returned success but Docker binaries were not detected.'
        Show-FailureLogs
        return 1
    }
    Say '[OK] Docker Desktop installer completed.'
    Say 'Start Docker Desktop from the Start menu and complete its first-run setup.'
    Say 'A Windows restart or WSL update may be needed before the engine starts.'
    Say 'Then run Setup\09_SETUP_FOUNDRY_SANDBOX.bat.'
    return 0
}
function Build-FoundryImage {
    $docker = Find-DockerCli
    if (-not $docker) {
        Say '[ERROR] Docker CLI not found in PATH or standard Docker Desktop folders.'
        Say 'Run Setup\14_INSTALL_DOCKER_DESKTOP.bat first.'
        Show-Requirements
        return 1
    }
    if (-not (Docker-Engine-Ready $docker)) {
        Say '[WARNING] Docker CLI found, but its engine is not running.'
        if (-not (Start-Docker-If-Approved $docker)) {
            Show-FailureLogs
            return 1
        }
    }
    $docker = Find-DockerCli
    $type = (& $docker info --format '{{.OSType}}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $type -ne 'linux') {
        Say ('[ERROR] Foundry requires the Linux Docker engine; detected: ' + $type)
        Say 'Open Docker Desktop and switch to Linux containers / WSL 2.'
        return 1
    }
    $root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $context = Join-Path $root 'foundry_sandbox'
    $dockerfile = Join-Path $context 'Dockerfile'
    if (-not (Test-Path -LiteralPath $dockerfile -PathType Leaf)) {
        Say ('[ERROR] Foundry Dockerfile is missing: ' + $dockerfile)
        return 1
    }
    Say ('Docker CLI: ' + $docker)
    Say ('Dockerfile: ' + $dockerfile)
    Say 'Build downloads trusted dependencies. Runtime tests will have no network.'
    if (-not (Confirm-Action 'Build the trusted Apollo Foundry sandbox image now?')) {
        Say '[INFO] Build cancelled. No changes made.'
        return 0
    }
    & $docker build --pull --progress=plain -t 'apollo-foundry-qt:phase1' -f $dockerfile $context 2>&1 | Out-Host
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Say ('[ERROR] Docker image build failed, exit code ' + $code)
        return 1
    }
    & $docker image inspect 'apollo-foundry-qt:phase1' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Say '[ERROR] Docker image inspection failed after build.'
        return 1
    }
    Say 'Running read-only, offline smoke test inside the new container...'
    & $docker run --rm --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges:true --pids-limit=64 --cpus=1 --memory=768m --pull=never --tmpfs '/tmp:rw,nosuid,nodev,size=64m' -e MPLCONFIGDIR=/tmp/matplotlib 'apollo-foundry-qt:phase1' python -c 'import PySide6, numpy, sympy, matplotlib; print("APOLLO_SANDBOX_READY")' 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Say '[ERROR] Offline image smoke test failed. Image is NOT verified.'
        return 1
    }
    Say '[OK] Verified image: apollo-foundry-qt:phase1'
    Say 'The Foundry can now run unit, GUI and UI interaction tests in Docker.'
    return 0
}
$result = 1
try {
    New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
    Start-Transcript -Path $script:LogFile -Append -ErrorAction Stop | Out-Null
    $script:TranscriptStarted = $true
    Say ('Apollo Docker/Foundry setup - ' + $Action + ' - ' + (Get-Date).ToString('u'))
    Say ('Log file: ' + $script:LogFile)
    if ($Action -eq 'InstallDocker') { $result = Install-Desktop }
    else { $result = Build-FoundryImage }
} catch {
    Say ('[FATAL] ' + $_.Exception.Message)
    Say ('Location: ' + $_.InvocationInfo.PositionMessage)
    Show-FailureLogs
    $result = 1
} finally {
    if ($script:TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { Write-Warning $_.Exception.Message }
    }
}
exit $result
