$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not found: $Python"
}

Set-Location $ProjectRoot

& $Python -m uvicorn main:app --host 0.0.0.0 --port 8000
