$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

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
