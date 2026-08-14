param(
    [int]$Port = 8080,
    [string]$HostAddress = "0.0.0.0"
)
$ErrorActionPreference = "Stop"
$ProgramDataRoot = Join-Path $env:ProgramData "Tabletop Librarian"
$env:TTL_DATA_DIR = Join-Path $ProgramDataRoot "data"
$env:TTL_CACHE_DIR = Join-Path $ProgramDataRoot "cache"
$env:TTL_LOG_DIR = Join-Path $ProgramDataRoot "logs"
$env:TTL_HOST = $HostAddress
$env:TTL_PORT = "$Port"
$Exe = Join-Path $PSScriptRoot "Tabletop-Librarian-Server.exe"
if (-not (Test-Path $Exe)) { throw "Server executable not found: $Exe" }
& $Exe
