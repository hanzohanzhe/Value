$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $env:VALUE_DATA_HOME) {
    $legacyState = Join-Path $projectRoot ".value"
    $env:VALUE_DATA_HOME = if (Test-Path -LiteralPath $legacyState) { $legacyState } else { Join-Path $env:LOCALAPPDATA "VALUE" }
}
$pidFile = Join-Path ([System.IO.Path]::GetFullPath($env:VALUE_DATA_HOME)) "local-services.json"

function Test-PortOwnedByProcess {
    param([int]$Port, [int]$ProcessId)
    $netstat = Get-Command netstat.exe -ErrorAction SilentlyContinue
    if ($netstat) {
        $rows = @(& $netstat.Source -ano -p tcp)
        if ($LASTEXITCODE -eq 0) {
            return @(
                $rows | Where-Object {
                    $_ -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+$ProcessId\s*$"
                }
            ).Count -gt 0
        }
    }
    $tcpInspector = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($tcpInspector) {
        return @(
            Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
                Where-Object { $_.OwningProcess -eq $ProcessId }
        ).Count -gt 0
    }
    return $false
}

function Test-PrivateRuntimeProcess {
    param($Managed, [int]$ProcessId)
    try {
        $cimProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($cimProcess -and ([string]$cimProcess.CommandLine) -match $Managed.pattern) {
            return $true
        }
    } catch {
        Write-Verbose "CIM command-line inspection is unavailable; checking the private runtime path."
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    try {
        $actualPath = [System.IO.Path]::GetFullPath([string]$process.Path)
        $expectedPath = [System.IO.Path]::GetFullPath([string]$Managed.executable)
        $pathMatches = $actualPath.Equals($expectedPath, [System.StringComparison]::OrdinalIgnoreCase)
        if ($pathMatches) {
            # Port ownership is recorded for diagnosis, but an app-owned private runtime
            # may still hold files after its listening socket has already closed.
            [void](Test-PortOwnedByProcess -Port $Managed.port -ProcessId $ProcessId)
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

if (Test-Path $pidFile) {
    try {
        $services = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        $managedProcesses = @(
            @{ pid = $services.backend_pid; pattern = 'backend\.server.*--port\s+8766'; label = 'backend'; port = 8766; executable = (Join-Path $projectRoot 'runtime\python\python.exe') },
            @{ pid = $services.frontend_pid; pattern = 'serve-value-ui\.mjs.*--port\s+8800'; label = 'frontend'; port = 8800; executable = (Join-Path $projectRoot 'runtime\node\node.exe') }
        )
        $failures = @()
        foreach ($managed in $managedProcesses) {
            $valuePid = [int]$managed.pid
            if (-not $valuePid) { continue }
            $process = Get-Process -Id $valuePid -ErrorAction SilentlyContinue
            if (-not $process) { continue }
            if (Test-PrivateRuntimeProcess -Managed $managed -ProcessId $valuePid) {
                & taskkill.exe /PID $valuePid /T /F | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    $failures += "$($managed.label) PID $valuePid could not be terminated"
                    continue
                }
                $exited = $false
                try {
                    $exited = $process.WaitForExit(30000)
                } catch {
                    try { $exited = $process.HasExited } catch { $exited = $false }
                }
                if (-not $exited) {
                    $failures += "$($managed.label) PID $valuePid is still running"
                }
                $process.Dispose()
            } else {
                Write-Warning "Ignoring stale VALUE $($managed.label) PID $valuePid because it now belongs to another process."
            }
        }
        if ($failures.Count -gt 0) {
            throw "VALUE local services did not stop cleanly: $($failures -join '; ')."
        }
        Remove-Item -LiteralPath $pidFile -Force
    } catch {
        Write-Error $_
        exit 1
    }
}

Write-Host "VALUE local services stopped."
