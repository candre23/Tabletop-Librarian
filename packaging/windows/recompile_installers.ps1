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

$Inno = Find-InnoCompiler
if (-not $Inno) {
    throw "Inno Setup 6 or 7 is required. Install Inno Setup and rerun this script."
}

$ServerSource = Join-Path $Root "packaging\server\windows\dist\Tabletop-Librarian-Server"
$BackendExe = Join-Path $Root "packaging\backend\windows\dist\TTL-AI-Backend.exe"
$Icon = Join-Path $Root "packaging\windows\ttl.ico"

if (-not (Test-Path (Join-Path $ServerSource "Tabletop-Librarian-Server.exe"))) {
    throw "Existing PyInstaller Server payload not found. Run build_releases.ps1 once first."
}
if (-not (Test-Path $BackendExe)) {
    throw "Existing PyInstaller Backend payload not found. Run build_releases.ps1 once first."
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null

Write-Host "Recompiling TTL Server installer..."
& $Inno `
  "--define=AppVersion=$ServerVersion" `
  "--define=SourceDir=$ServerSource" `
  "--define=OutputDir=$Out" `
  "--define=IconFile=$Icon" `
  "--define=RepoRoot=$Root" `
  (Join-Path $Root "packaging\server\windows\installer.iss")
if ($LASTEXITCODE -ne 0) { throw "TTL Server installer compilation failed." }

Write-Host "Recompiling TTL AI Backend installer..."
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

$HashLines = foreach ($Artifact in $Artifacts) {
    $Hash = (Get-FileHash -Algorithm SHA256 $Artifact).Hash.ToLowerInvariant()
    "$Hash  $([IO.Path]::GetFileName($Artifact))"
}
$HashLines | Set-Content -Encoding ascii (Join-Path $Out "SHA256SUMS.txt")

Write-Host ""
Write-Host "Installers rebuilt in: $Out"
Get-ChildItem $Out | Select-Object Name,Length
