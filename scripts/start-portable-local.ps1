param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Node,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:VALUE_DATA_HOME = [System.IO.Path]::GetFullPath($StateRoot)
$pidFile = Join-Path $env:VALUE_DATA_HOME "local-services.json"
$frontendLog = Join-Path $env:VALUE_DATA_HOME "frontend.log"
$frontendErrorLog = Join-Path $env:VALUE_DATA_HOME "frontend-error.log"
$backendLog = Join-Path $env:VALUE_DATA_HOME "backend.log"
$backendErrorLog = Join-Path $env:VALUE_DATA_HOME "backend-error.log"
New-Item -ItemType Directory -Force -Path $env:VALUE_DATA_HOME | Out-Null

if (Test-Path -LiteralPath $pidFile) { & (Join-Path $PSScriptRoot "stop-local.ps1") }

function Test-PortInUse {
    param([int]$Port)
    $netstat = Get-Command netstat.exe -ErrorAction SilentlyContinue
    if ($netstat) {
        $netstatLines = @(& $netstat.Source -ano -p tcp)
        if ($LASTEXITCODE -eq 0) {
            foreach ($line in $netstatLines) {
                if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+\d+\s*$") {
                    return $true
                }
            }
            return $false
        }
    }
    $tcpInspector = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($tcpInspector) {
        return @(
            Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        ).Count -gt 0
    }
    throw "VALUE cannot inspect local ports because neither netstat nor Get-NetTCPConnection is available."
}

foreach ($port in 8766, 8800) {
    if (Test-PortInUse -Port $port) {
        throw "Port $port is already in use. VALUE did not terminate that process."
    }
}

function Stop-PortableProcesses {
    param($Backend, $Frontend)
    foreach ($process in @($Backend, $Frontend)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

try {
    $backend = Start-Process -FilePath $Python -ArgumentList @("-m", "backend.server", "--host", "127.0.0.1", "--port", "8766") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrorLog
    $frontendScript = Join-Path $PSScriptRoot "serve-value-ui.mjs"
    $frontendArguments = @("`"$frontendScript`"", "--host", "127.0.0.1", "--port", "8800")
    $frontend = Start-Process -FilePath $Node -ArgumentList $frontendArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog
    @{ backend_pid=$backend.Id; frontend_pid=$frontend.Id; started_at=(Get-Date).ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

    for ($attempt=0; $attempt -lt 60; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/health" -TimeoutSec 1
            if ($health.service -eq "value-modular-local") { break }
        } catch { Start-Sleep -Milliseconds 500 }
        if ($attempt -eq 59) { throw "The VALUE model service did not start." }
    }
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8800/" -TimeoutSec 1 | Out-Null; break }
        catch { Start-Sleep -Milliseconds 500 }
        if ($attempt -eq 59) { throw "The VALUE website did not start." }
    }
} catch {
    Stop-PortableProcesses -Backend $backend -Frontend $frontend
    throw
}
if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:8800/"
}
