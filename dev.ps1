# Runs the backend and the UI together on Windows (dev.sh on macOS).
# Ports can be changed with JOBPILOT_PORT (backend, default 8766; the installed app uses 8765) and JOBPILOT_UI_PORT (UI, default 5173).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not $env:JOBPILOT_PORT) { $env:JOBPILOT_PORT = "8766" }
if (-not $env:JOBPILOT_UI_PORT) { $env:JOBPILOT_UI_PORT = "5173" }

foreach ($port in $env:JOBPILOT_PORT, $env:JOBPILOT_UI_PORT) {
  $holder = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($holder) {
    $name = (Get-Process -Id $holder.OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Write-Host "Port $port is already used by: $name"
    Write-Host 'Stop that process, or pick other ports, e.g.: $env:JOBPILOT_UI_PORT=5180; $env:JOBPILOT_PORT=8770; .\dev.ps1'
    exit 1
  }
}

$backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory backend uv -ArgumentList "run", "jobpilot"
$ui = Start-Process -PassThru -NoNewWindow -WorkingDirectory frontend npm.cmd -ArgumentList "run", "dev"
Write-Host "Job Pilot: http://127.0.0.1:$env:JOBPILOT_UI_PORT  (Ctrl+C stops both)"
try { Wait-Process -Id $backend.Id, $ui.Id } finally {
  Stop-Process -Id $backend.Id, $ui.Id -ErrorAction SilentlyContinue
}
