# Builds Job Pilot for Windows: the React UI, then the Python backend + window bundled with PyInstaller
# into dist\Job Pilot\Job Pilot.exe, then (if Inno Setup is installed) the installer dist\JobPilot-Setup-<version>.exe.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Push-Location frontend
npm run build
if ($LASTEXITCODE) { throw "npm run build failed" }
Pop-Location

Push-Location backend
uv run pyinstaller --noconfirm --clean --distpath ../dist --workpath ../build ../packaging/jobpilot.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Pop-Location

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) { $iscc = Get-Item "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" -ErrorAction SilentlyContinue }
if ($iscc) {
  & $iscc.Source packaging\windows\installer.iss
  if ($LASTEXITCODE) { throw "Inno Setup failed" }
  Write-Host "`nBuilt: dist\Job Pilot\Job Pilot.exe and the installer in dist\"
} else {
  Write-Host "`nBuilt: dist\Job Pilot\Job Pilot.exe (install Inno Setup 6 to also make the installer)"
}
