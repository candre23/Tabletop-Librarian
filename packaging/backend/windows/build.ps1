$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\ai_backend")).Path
$BuildRoot = Join-Path $PSScriptRoot "build-env"
$Dist = Join-Path $PSScriptRoot "dist"

if (Test-Path $BuildRoot) { Remove-Item -Recurse -Force $BuildRoot }
py -3.12 -m venv $BuildRoot
$Python = Join-Path $BuildRoot "Scripts\python.exe"
& $Python -m pip install --upgrade pip setuptools wheel pyinstaller
& $Python -m pip install $Root

if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
& $Python -m PyInstaller `
  --noconfirm --clean --onefile --windowed `
  --name "TTL-AI-Backend" `
  --distpath $Dist `
  --workpath (Join-Path $PSScriptRoot "work") `
  --specpath (Join-Path $PSScriptRoot "work") `
  (Join-Path $Root "run_manager.py")

Write-Host "Built: $(Join-Path $Dist 'TTL-AI-Backend.exe')"
