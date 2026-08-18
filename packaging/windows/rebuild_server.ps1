$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ServerBuild = Join-Path $Root "packaging\server\windows\build.ps1"
$ServerVersion = "1.0.0"
$Out = Join-Path $Root "dist\windows"

Write-Host "Rebuilding TTL Server PyInstaller payload..."
powershell -ExecutionPolicy Bypass -File $ServerBuild
if ($LASTEXITCODE -ne 0) {
    throw "TTL Server PyInstaller rebuild failed."
}

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
    throw "Inno Setup 6 or 7 is required."
}

$ServerSource = Join-Path $Root "packaging\server\windows\dist\Tabletop-Librarian-Server"
$Icon = Join-Path $Root "packaging\windows\ttl.ico"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

Write-Host "Recompiling TTL Server installer..."
& $Inno `
  "--define=AppVersion=$ServerVersion" `
  "--define=SourceDir=$ServerSource" `
  "--define=OutputDir=$Out" `
  "--define=IconFile=$Icon" `
  "--define=RepoRoot=$Root" `
  (Join-Path $Root "packaging\server\windows\installer.iss")
if ($LASTEXITCODE -ne 0) {
    throw "TTL Server installer compilation failed."
}

$Artifact = Join-Path $Out "TTL-Server-Windows-x64-$ServerVersion.exe"
$Hash = (Get-FileHash -Algorithm SHA256 $Artifact).Hash.ToLowerInvariant()
Write-Host ""
Write-Host "Server installer rebuilt:"
Write-Host "  $Artifact"
Write-Host "SHA256:"
Write-Host "  $Hash"
