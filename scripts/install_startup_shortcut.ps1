$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartAllScript = Join-Path $PSScriptRoot "start_all.ps1"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "Meme Sender.lnk"

if (-not (Test-Path $StartAllScript)) {
    throw "start_all.ps1 was not found: $StartAllScript"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$StartAllScript`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.WindowStyle = 7
$Shortcut.Save()

Write-Host "Installed startup shortcut:"
Write-Host $ShortcutPath
Write-Host "It will run when this Windows user logs in."
