param(
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$BuildRoot = Join-Path $PSScriptRoot "build-env"
$Dist = Join-Path $PSScriptRoot "dist"
$Work = Join-Path $PSScriptRoot "work"
$Icon = Join-Path $Root "packaging\windows\ttl.ico"
$Entry = Join-Path $PSScriptRoot "server_entry.py"
$ManagerEntry = Join-Path $PSScriptRoot "server_manager.py"
$OcrEntry = Join-Path $PSScriptRoot "ocr_entry.py"

function Find-7ZipDirectory {
    $Candidates = @(
        (Join-Path $env:ProgramFiles "7-Zip"),
        (Join-Path ${env:ProgramFiles(x86)} "7-Zip")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and
            (Test-Path (Join-Path $Candidate "7z.exe")) -and
            (Test-Path (Join-Path $Candidate "7z.dll"))) {
            return $Candidate
        }
    }
    return $null
}

function Find-TesseractDirectory {
    $Candidates = @(
        (Join-Path $env:ProgramFiles "Tesseract-OCR"),
        (Join-Path $env:LOCALAPPDATA "Programs\Tesseract-OCR"),
        (Join-Path $env:LOCALAPPDATA "Tesseract-OCR")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path (Join-Path $Candidate "tesseract.exe"))) {
            return $Candidate
        }
    }
    return $null
}

$SevenZipDir = Find-7ZipDirectory
if (-not $SevenZipDir) {
    throw "7-Zip x64 is required on the Windows build machine so CBR support can be bundled. Install 7-Zip from 7-zip.org and rerun the build."
}

$TesseractDir = Find-TesseractDirectory
if (-not $TesseractDir) {
    throw "Tesseract OCR x64 is required on the Windows build machine so OCR support can be bundled. Install the Windows Tesseract build recommended by OCRmyPDF, then rerun the build."
}

function Invoke-PythonLauncher {
    param([string[]]$Arguments)
    & py "-$PythonVersion" @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python $PythonVersion command failed." }
}

try {
    Invoke-PythonLauncher -Arguments @("-c", "import sys; print(sys.version)")
} catch {
    throw "Python $PythonVersion x64 is required to build the Windows Server package. Install it from python.org, then rerun this script."
}

Remove-Item -Recurse -Force $BuildRoot,$Dist,$Work -ErrorAction SilentlyContinue
Invoke-PythonLauncher -Arguments @("-m", "venv", $BuildRoot)
$Python = Join-Path $BuildRoot "Scripts\python.exe"

& $Python -m pip install --upgrade "pip>=26,<27" "setuptools>=80,<85" wheel "pyinstaller==6.20.0"
if ($LASTEXITCODE -ne 0) { throw "Unable to install Windows build tools." }

# TTL's embeddings are CPU/OpenVINO work. Local LLM acceleration belongs to the
# separate AI Backend product, so never pull CUDA/NCCL into the Server build.
& $Python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw "Unable to install CPU-only PyTorch." }

& $Python -m pip install $Root
if ($LASTEXITCODE -ne 0) { throw "Unable to install Tabletop Librarian into the build environment." }

& $Python -m pip install "ocrmypdf==17.10.0"
if ($LASTEXITCODE -ne 0) { throw "Unable to install OCRmyPDF into the Windows build environment." }

$ReleasePacks = Join-Path $PSScriptRoot "release-system-packs"
Remove-Item -Recurse -Force $ReleasePacks -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force (Join-Path $Root "data\system_packs") $ReleasePacks

$Sep = ";"
$Args = @(
    "--noconfirm", "--clean", "--onedir", "--windowed",
    "--name", "Tabletop-Librarian-Server",
    "--icon", $Icon,
    "--distpath", $Dist,
    "--workpath", $Work,
    "--specpath", $Work,
    "--add-data", "$(Join-Path $Root 'app\templates')${Sep}app\templates",
    "--add-data", "$(Join-Path $Root 'app\static')${Sep}app\static",
    "--add-data", "$(Join-Path $Root 'pipelines')${Sep}pipelines",
    "--add-data", "${ReleasePacks}${Sep}data\system_packs",
    "--collect-all", "sentence_transformers",
    "--collect-all", "transformers",
    "--collect-all", "openvino",
    "--collect-all", "openvino_tokenizers",
    "--collect-all", "optimum",
    "--collect-all", "scipy",
    "--collect-all", "sklearn",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan.on",
    $Entry
)

& $Python -m PyInstaller @Args
if ($LASTEXITCODE -ne 0) { throw "PyInstaller Server build failed." }

$Exe = Join-Path $Dist "Tabletop-Librarian-Server\Tabletop-Librarian-Server.exe"
if (-not (Test-Path $Exe)) { throw "Server executable was not created: $Exe" }

$ServerPayload = Join-Path $Dist "Tabletop-Librarian-Server"

$SevenZipVendor = Join-Path $ServerPayload "vendor\7zip"
New-Item -ItemType Directory -Force -Path $SevenZipVendor | Out-Null
Copy-Item -Force (Join-Path $SevenZipDir "7z.exe") $SevenZipVendor
Copy-Item -Force (Join-Path $SevenZipDir "7z.dll") $SevenZipVendor
$SevenZipLicense = Join-Path $SevenZipDir "License.txt"
if (Test-Path $SevenZipLicense) {
    Copy-Item -Force $SevenZipLicense $SevenZipVendor
} else {
    throw "7-Zip License.txt was not found under $SevenZipDir; refusing to create a redistributable Server build."
}

$TesseractVendor = Join-Path $ServerPayload "vendor\tesseract"
Remove-Item -Recurse -Force $TesseractVendor -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force $TesseractDir $TesseractVendor

$OcrDist = Join-Path $PSScriptRoot "ocr-dist"
$OcrWork = Join-Path $PSScriptRoot "ocr-work"
Remove-Item -Recurse -Force $OcrDist,$OcrWork -ErrorAction SilentlyContinue
$OcrArgs = @(
    "--noconfirm", "--clean", "--onefile", "--console",
    "--name", "TTL-OCRmyPDF",
    "--distpath", $OcrDist,
    "--workpath", $OcrWork,
    "--specpath", $OcrWork,
    "--collect-all", "ocrmypdf",
    "--collect-all", "pikepdf",
    "--collect-all", "pypdfium2",
    "--copy-metadata", "ocrmypdf",
    $OcrEntry
)
& $Python -m PyInstaller @OcrArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller OCRmyPDF helper build failed." }

$OcrExe = Join-Path $OcrDist "TTL-OCRmyPDF.exe"
if (-not (Test-Path $OcrExe)) { throw "OCRmyPDF helper executable was not created: $OcrExe" }
$OcrVendor = Join-Path $ServerPayload "vendor\ocr"
New-Item -ItemType Directory -Force -Path $OcrVendor | Out-Null
Copy-Item -Force $OcrExe $OcrVendor
Copy-Item -Force (Join-Path $Root "app\ocr_progress_plugin.py") $OcrVendor

$ManagerDist = Join-Path $PSScriptRoot "manager-dist"
$ManagerWork = Join-Path $PSScriptRoot "manager-work"
Remove-Item -Recurse -Force $ManagerDist,$ManagerWork -ErrorAction SilentlyContinue

$ManagerArgs = @(
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "TTL-Server-Manager",
    "--icon", $Icon,
    "--distpath", $ManagerDist,
    "--workpath", $ManagerWork,
    "--specpath", $ManagerWork,
    $ManagerEntry
)

& $Python -m PyInstaller @ManagerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller Server Manager build failed." }

$ManagerExe = Join-Path $ManagerDist "TTL-Server-Manager.exe"
if (-not (Test-Path $ManagerExe)) { throw "Server Manager executable was not created: $ManagerExe" }

Copy-Item -Force $ManagerExe (Join-Path $Dist "Tabletop-Librarian-Server\TTL-Server-Manager.exe")

Write-Host "Built TTL Server payload: $Exe"
Write-Host "Built TTL Server Manager: $(Join-Path $Dist 'Tabletop-Librarian-Server\TTL-Server-Manager.exe')"
