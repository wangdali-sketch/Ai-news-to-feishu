param(
    [string]$Time = "08:00",
    [string]$TaskName = "AiNewsToFeishuDaily"
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunScript = Join-Path $ProjectDir "run_daily.bat"

if (-not (Test-Path $RunScript)) {
    throw "Run script not found: $RunScript"
}

$arguments = @(
    "/Create",
    "/TN", $TaskName,
    "/TR", $RunScript,
    "/SC", "DAILY",
    "/ST", $Time,
    "/F"
)

& schtasks.exe @arguments

if ($LASTEXITCODE -ne 0) {
    throw "Failed to create scheduled task. Use HH:mm time format, for example 08:00."
}

try {
    $task = Get-ScheduledTask -TaskName $TaskName
    $task.Settings.StartWhenAvailable = $true
    $task.Settings.DisallowStartIfOnBatteries = $false
    $task.Settings.StopIfGoingOnBatteries = $false
    Set-ScheduledTask -InputObject $task | Out-Null
}
catch {
    Write-Host "Task was created, but advanced settings were not updated."
    Write-Host $_
}

Write-Host "Task created or updated: $TaskName"
Write-Host "Daily time: $Time"
Write-Host "Run script: $RunScript"
Write-Host "Query task: schtasks /Query /TN `"$TaskName`""
Write-Host "Logs folder: $ProjectDir\logs"
