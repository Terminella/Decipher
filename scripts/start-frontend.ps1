$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendPath = Join-Path $ProjectRoot "frontend"

Set-Location $FrontendPath

if (-not (Test-Path "node_modules")) {
    npm install
}

npm run dev