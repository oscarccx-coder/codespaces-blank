$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "dist\Apollo\Apollo.exe"
if (!(Test-Path $exe)) { throw "Apollo.exe was not found. Build it first." }
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash
"SHA256  $hash  Apollo.exe" | Set-Content (Join-Path $PSScriptRoot "dist\Apollo\SHA256.txt") -Encoding ASCII
Write-Host "SHA256: $hash"
