param(
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Out = Join-Path $Root "dist\windows"
$ServerVersion = "1.0.0"
$BackendVersion = "1.0.0"

function Find-InnoCompiler {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) { return $Candidate }
    }
    $Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    return $null
}

if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw "Python Launcher (py.exe) is required. Install Python $PythonVersion x64 from python.org."
}

$Inno = Find-InnoCompiler
if (-not $Inno) {
    throw @"
Inno Setup 7 is required to create the final installer EXEs.
Install it, then rerun this script. Current winget command:
  winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
"@
}

Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Out | Out-Null

Write-Host "Building Windows TTL Server payload..."
& (Join-Path $Root "packaging\server\windows\build.ps1") -PythonVersion $PythonVersion
if ($LASTEXITCODE -ne 0) { throw "TTL Server payload build failed." }

Write-Host "Building Windows AI Backend payload..."
& (Join-Path $Root "packaging\backend\windows\build.ps1") -PythonVersion $PythonVersion
if ($LASTEXITCODE -ne 0) { throw "TTL AI Backend payload build failed." }

$ServerSource = Join-Path $Root "packaging\server\windows\dist\Tabletop-Librarian-Server"
$BackendExe = Join-Path $Root "packaging\backend\windows\dist\TTL-AI-Backend.exe"
$Icon = Join-Path $Root "packaging\windows\ttl.ico"

Write-Host "Compiling Windows TTL Server installer..."
& $Inno `
  "--define=AppVersion=$ServerVersion" `
  "--define=SourceDir=$ServerSource" `
  "--define=OutputDir=$Out" `
  "--define=IconFile=$Icon" `
  "--define=RepoRoot=$Root" `
  (Join-Path $Root "packaging\server\windows\installer.iss")
if ($LASTEXITCODE -ne 0) { throw "TTL Server installer compilation failed." }

Write-Host "Compiling Windows AI Backend installer..."
& $Inno `
  "--define=AppVersion=$BackendVersion" `
  "--define=SourceExe=$BackendExe" `
  "--define=OutputDir=$Out" `
  "--define=IconFile=$Icon" `
  "--define=RepoRoot=$Root" `
  (Join-Path $Root "packaging\backend\windows\installer.iss")
if ($LASTEXITCODE -ne 0) { throw "TTL AI Backend installer compilation failed." }

$Artifacts = @(
    (Join-Path $Out "TTL-Server-Windows-x64-$ServerVersion.exe"),
    (Join-Path $Out "TTL-AI-Windows-x64-$BackendVersion.exe")
)
foreach ($Artifact in $Artifacts) {
    if (-not (Test-Path $Artifact)) { throw "Expected release artifact was not created: $Artifact" }
}

$HashLines = foreach ($Artifact in $Artifacts) {
    $Hash = (Get-FileHash -Algorithm SHA256 $Artifact).Hash.ToLowerInvariant()
    "$Hash  $([IO.Path]::GetFileName($Artifact))"
}
$HashLines | Set-Content -Encoding ascii (Join-Path $Out "SHA256SUMS.txt")

@"
Tabletop Librarian Windows Release
=================================

Server: TTL-Server-Windows-x64-$ServerVersion.exe
AI Backend: TTL-AI-Windows-x64-$BackendVersion.exe

Architecture: Windows x64
Packaging: PyInstaller 6.20.0 + Inno Setup

The Server and AI Backend are independent products. Installing one does not
install or require the other.

Windows release validation should cover clean install, upgrade, uninstall with
settings/data preserved, custom ports, LAN access, and the AI hardware paths
available on the test machines.
"@ | Set-Content -Encoding utf8 (Join-Path $Out "WINDOWS_RELEASE_MANIFEST.txt")

Write-Host ""
Write-Host "Windows release artifacts created in: $Out"
Get-ChildItem $Out | Select-Object Name,Length
