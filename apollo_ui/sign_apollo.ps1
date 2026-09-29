param(
    [string]$Thumbprint = $env:APOLLO_CERT_THUMBPRINT
)
$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "dist\Apollo\Apollo.exe"
if (!(Test-Path $exe)) { throw "Build dist\Apollo\Apollo.exe first." }
if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
    throw "No signing certificate thumbprint supplied. Set APOLLO_CERT_THUMBPRINT to a real code-signing certificate in your Windows certificate store."
}
$signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
if (!$signtool) { throw "signtool.exe was not found. Install the Windows SDK signing tools." }
& $signtool sign /sha1 $Thumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $exe
if ($LASTEXITCODE -ne 0) { throw "signtool failed with exit code $LASTEXITCODE" }
& $signtool verify /pa /v $exe
