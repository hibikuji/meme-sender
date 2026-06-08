$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$EnvNames = @(
    "DISCORD_WEBHOOK_URL",
    "MEME_ADMIN_PASSWORD",
    "MEME_ADMIN_TOKEN_DAYS",
    "MEME_STORE_BACKEND",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_BUCKET"
)

foreach ($Name in $EnvNames) {
    $Value = [Environment]::GetEnvironmentVariable($Name, "User")
    if ($Value) {
        Set-Item -Path "Env:$Name" -Value $Value
    }
}

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not found: $Python"
}

Set-Location $ProjectRoot

& $Python -m uvicorn main:app --host 0.0.0.0 --port 8000
