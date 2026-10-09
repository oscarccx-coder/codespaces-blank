# Creates shortcuts only for the current user's Desktop.
# Called after explicit confirmation in Setup/01_INSTALL_APOLLO.bat.
$ErrorActionPreference = "Stop"
$folder = Split-Path -Parent $MyInvocation.MyCommand.Path
$base = (Resolve-Path (Join-Path $folder "..")).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @(
    @{Name="Apollo.lnk"; Target="02_START_APOLLO.bat"; Info="Start Apollo"},
    @{Name="Apollo Setup.lnk"; Target="10_SETUP_WIZARD.bat"; Info="Apollo Setup & Recovery"}
)) {
    $link = $shell.CreateShortcut((Join-Path $desktop $item.Name))
    $link.TargetPath = Join-Path $folder $item.Target
    $link.WorkingDirectory = $base
    $link.Description = $item.Info
    $icon = Join-Path $base "apollo_logo.ico"
    if (Test-Path $icon) { $link.IconLocation = $icon }
    $link.Save()
}
Write-Output "Apollo desktop shortcuts created for the current user."
