# Scarica i binari di pdfium per Windows x64 (https://github.com/bblanchon/pdfium-binaries)
# in third_party\pdfium. Uso: powershell -ExecutionPolicy Bypass -File scarica_pdfium.ps1 [-Tag chromium/8152]
param([string]$Tag = "chromium/8152")

$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "third_party\pdfium"
$url = "https://github.com/bblanchon/pdfium-binaries/releases/download/$Tag/pdfium-win-x64.tgz"
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "pdfium-win-x64.tgz"

Write-Host "Scarico $url"
Invoke-WebRequest $url -OutFile $tmp -Headers @{ "User-Agent" = "pdf-layout-measure" }
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
New-Item -ItemType Directory -Force $dest | Out-Null
tar -xzf $tmp -C $dest
Remove-Item $tmp
Write-Host "pdfium in $dest\bin\pdfium.dll"
Get-Content (Join-Path $dest "VERSION")
