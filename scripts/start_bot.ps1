$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$EnvNames = @(
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "MEME_ADMIN_DISCORD_USER_IDS",
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

if (-not $env:DISCORD_BOT_TOKEN) {
    throw "DISCORD_BOT_TOKEN is not set. Set it with: setx DISCORD_BOT_TOKEN `"your_token`""
}

if (-not $env:DISCORD_GUILD_ID) {
    throw "DISCORD_GUILD_ID is not set. Set it with: setx DISCORD_GUILD_ID `"your_server_id`""
}

Set-Location $ProjectRoot

& $Python bot.py
