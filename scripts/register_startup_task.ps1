$ErrorActionPreference = "Stop"

$TaskName = "MemeSenderAutoStart"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartAllScript = Join-Path $PSScriptRoot "start_all.ps1"

if (-not (Test-Path $StartAllScript)) {
    throw "start_all.ps1 was not found: $StartAllScript"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartAllScript`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$UserId = "$env:USERDOMAIN\$env:USERNAME"
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Description "Start Meme Sender web server and Discord bot at Windows logon." `
        -Force `
        -ErrorAction Stop | Out-Null
}
catch {
    Write-Error "Could not register startup task. Try running PowerShell as administrator, or use scripts\install_startup_shortcut.ps1 instead."
    throw
}

Write-Host "Registered startup task: $TaskName"
Write-Host "It will run when this Windows user logs in."
