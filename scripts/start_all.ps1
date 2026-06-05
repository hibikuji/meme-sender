$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $ProjectRoot "logs"
$WebScript = Join-Path $PSScriptRoot "start_web.ps1"
$BotScript = Join-Path $PSScriptRoot "start_bot.ps1"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$WebOutLog = Join-Path $LogDir "web.out.log"
$WebErrLog = Join-Path $LogDir "web.err.log"
$BotOutLog = Join-Path $LogDir "bot.out.log"
$BotErrLog = Join-Path $LogDir "bot.err.log"

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $WebScript
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $WebOutLog -RedirectStandardError $WebErrLog

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $BotScript
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $BotOutLog -RedirectStandardError $BotErrLog

Write-Host "Started web server and Discord bot."
Write-Host "Web: http://127.0.0.1:8000/"
Write-Host "Logs: $LogDir"
