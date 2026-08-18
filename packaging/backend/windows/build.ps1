param(
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\ai_backend")).Path
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$BuildRoot = Join-Path $PSScriptRoot "build-env"
$Dist = Join-Path $PSScriptRoot "dist"
$Work = Join-Path $PSScriptRoot "work"
$Icon = Join-Path $RepoRoot "packaging\windows\ttl.ico"

function Invoke-PythonLauncher {
    param([string[]]$Arguments)
    & py "-$PythonVersion" @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python $PythonVersion command failed." }
}

try {
    Invoke-PythonLauncher -Arguments @("-c", "import sys; print(sys.version)")
} catch {
    throw "Python $PythonVersion x64 is required to build the Windows AI Backend package."
}

Remove-Item -Recurse -Force $BuildRoot,$Dist,$Work -ErrorAction SilentlyContinue
Invoke-PythonLauncher -Arguments @("-m", "venv", $BuildRoot)
$Python = Join-Path $BuildRoot "Scripts\python.exe"

& $Python -m pip install --upgrade "pip>=26,<27" "setuptools>=80,<85" wheel "pyinstaller==6.20.0"
if ($LASTEXITCODE -ne 0) { throw "Unable to install Windows build tools." }
& $Python -m pip install $Root
if ($LASTEXITCODE -ne 0) { throw "Unable to install TTL AI Backend into the build environment." }

& $Python -m PyInstaller `
  --noconfirm --clean --onefile --windowed `
  --name "TTL-AI-Backend" `
  --icon $Icon `
  --distpath $Dist `
  --workpath $Work `
  --specpath $Work `
  (Join-Path $Root "run_manager.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller AI Backend build failed." }

$Exe = Join-Path $Dist "TTL-AI-Backend.exe"
if (-not (Test-Path $Exe)) { throw "Backend executable was not created: $Exe" }
Write-Host "Built TTL AI Backend payload: $Exe"
