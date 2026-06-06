$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Launcher = Join-Path $Root "windows\Launch_HTML_Dashboard.bat"
$IconPath = Join-Path $Root "src\peripersonal_space_toolkit\assets\pps_toolkit_icon.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Peripersonal Space Toolkit.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Launcher
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 1
$Shortcut.Description = "Launch the Peripersonal Space Toolkit local dashboard"
if (Test-Path $IconPath) {
  $Shortcut.IconLocation = "$IconPath,0"
}
$Shortcut.Save()

Write-Host "Created shortcut: $ShortcutPath"
