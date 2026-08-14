$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$BuildRoot = Join-Path $PSScriptRoot "build-env"
$Dist = Join-Path $PSScriptRoot "dist"

if (Test-Path $BuildRoot) { Remove-Item -Recurse -Force $BuildRoot }
py -3.12 -m venv $BuildRoot
$Python = Join-Path $BuildRoot "Scripts\python.exe"
& $Python -m pip install --upgrade pip setuptools wheel pyinstaller
& $Python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
& $Python -m pip install $Root

if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
$Sep = ";"
& $Python -m PyInstaller `
  --noconfirm --clean --onedir --console `
  --name "Tabletop-Librarian-Server" `
  --distpath $Dist `
  --workpath (Join-Path $PSScriptRoot "work") `
  --specpath (Join-Path $PSScriptRoot "work") `
  --add-data "$(Join-Path $Root 'app\templates')${Sep}app\templates" `
  --add-data "$(Join-Path $Root 'app\static')${Sep}app\static" `
  --add-data "$(Join-Path $Root 'pipelines')${Sep}pipelines" `
  --add-data "$(Join-Path $Root 'data\system_packs')${Sep}data\system_packs" `
  --collect-all sentence_transformers `
  --collect-all transformers `
  --collect-all openvino `
  (Join-Path $Root "run.py")

Write-Host "Built server directory: $(Join-Path $Dist 'Tabletop-Librarian-Server')"
