$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $env:VALUE_DATA_HOME) {
    $legacyState = Join-Path $projectRoot ".value"
    if (Test-Path -LiteralPath $legacyState) {
        $env:VALUE_DATA_HOME = $legacyState
    } else {
        $env:VALUE_DATA_HOME = Join-Path $env:LOCALAPPDATA "VALUE"
    }
}
$stateDir = [System.IO.Path]::GetFullPath($env:VALUE_DATA_HOME)
$pidFile = Join-Path $stateDir "local-services.json"
$frontendLog = Join-Path $stateDir "frontend.log"
$frontendErrorLog = Join-Path $stateDir "frontend-error.log"

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

# A stale backend can keep port 8766 open and make a newly launched Python 3.10
# process appear healthy even though requests still reach an older service.
# Stop only the PIDs recorded by this VALUE workspace first.
$stopScript = Join-Path $PSScriptRoot "stop-local.ps1"
if (Test-Path -LiteralPath $pidFile) {
    & $stopScript
}

function Stop-StaleVALUEListener {
    param(
        [int]$Port,
        [string]$ExpectedCommandPattern
    )
    $listeners = @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    foreach ($listenerPid in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid" -ErrorAction SilentlyContinue
        $command = [string]$process.CommandLine
        $kind = if ($command -match $ExpectedCommandPattern) { "an unrecorded VALUE process" } else { "an unrelated process" }
        throw "Port $Port is occupied by $kind (PID $listenerPid). VALUE did not terminate it. Run stop-value.cmd or close the owning application, then try again."
    }
}

# A launcher interrupted before writing local-services.json can leave a
# listener behind. Refuse to kill an unrecorded process, even when its command
# line looks like VALUE; the presenter can resolve it deliberately.
Stop-StaleVALUEListener -Port 8766 -ExpectedCommandPattern 'backend\.server.*--port\s+8766'
Stop-StaleVALUEListener -Port 8800 -ExpectedCommandPattern 'serve-value-ui\.mjs.*--port\s+8800'

if (-not (Test-Path (Join-Path $projectRoot "node_modules"))) {
    throw "VALUE is not installed yet. Double-click install-value.cmd once, then launch again."
}

function Get-ValueClientAsset {
    $clientRoot = Join-Path $projectRoot "dist\client"
    if (-not (Test-Path -LiteralPath $clientRoot -PathType Container)) { return $null }
    return Get-ChildItem -LiteralPath $clientRoot -Filter "*.js" -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

# The production launcher serves Vinext's SSR build, not the development
# server. A cleaned workspace can retain node_modules while losing dist/. In
# that case rebuild automatically so double-clicking the launcher remains the
# complete non-programmer startup path.
$serverEntry = Join-Path $projectRoot "dist\server\index.js"
$probeAsset = Get-ValueClientAsset
if (-not (Test-Path -LiteralPath $serverEntry) -or $null -eq $probeAsset) {
    Write-Host "The VALUE website build is missing. Rebuilding it now..."
    $npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
    Push-Location $projectRoot
    try {
        & $npmPath run build
        if ($LASTEXITCODE -ne 0) { throw "The VALUE website did not build." }
    } finally {
        Pop-Location
    }
    $probeAsset = Get-ValueClientAsset
}
if (-not (Test-Path -LiteralPath $serverEntry) -or $null -eq $probeAsset) {
    throw "The VALUE website build is incomplete: the server entry or JavaScript client bundle is missing."
}

$value101ManifestPath = Join-Path $stateDir "data-packs\value-101-baseline-v1\manifest.json"
if (-not (Test-Path -LiteralPath $value101ManifestPath -PathType Leaf)) {
    throw "VALUE 101 is not installed in $stateDir. Double-click install-value.cmd; the idempotent installer will not replace user data."
}
try {
    $value101Manifest = Get-Content -LiteralPath $value101ManifestPath -Raw | ConvertFrom-Json
    $value101Bindings = @($value101Manifest.bindings.psobject.Properties)
    $value101Missing = @(
        foreach ($binding in $value101Bindings) {
            $boundPath = Join-Path (Split-Path -Parent $value101ManifestPath) ([string]$binding.Value.uri)
            if (-not (Test-Path -LiteralPath $boundPath -PathType Leaf)) { $binding.Name }
        }
    )
} catch {
    throw "VALUE 101 is installed but its manifest cannot be read. Double-click install-value.cmd to diagnose the local pack."
}
if ($value101Manifest.id -ne "value-101-baseline-v1" -or $value101Bindings.Count -ne 25 -or $value101Missing.Count -gt 0) {
    throw "VALUE 101 is incomplete. Double-click install-value.cmd; the installer will not replace a different data-pack revision."
}

function Test-ValuePythonCandidate {
    param(
        [string]$Executable,
        [string[]]$Prefix
    )
    if (-not $Executable) { return $false }
    if ([System.IO.Path]::IsPathRooted($Executable) -and -not (Test-Path -LiteralPath $Executable)) { return $false }
    $arguments = @($Prefix) + @(
        "-c",
        "import sys; assert sys.version_info[:2] == (3, 10); from gridform_core.runtime_capabilities import require_runtime_capability; require_runtime_capability('value-native', selected_module_ids=('value-bid-at-cost-psm',))"
    )
    Push-Location $projectRoot
    try {
        $probe = (& $Executable @arguments 2>&1 | Out-String)
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        Pop-Location
    }
}

$pythonCandidates = @(
    [pscustomobject]@{ executable = (Join-Path $projectRoot ".venv\Scripts\python.exe"); prefix = @() },
    [pscustomobject]@{ executable = (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"); prefix = @() }
)
$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($launcher) {
    $pythonCandidates += [pscustomobject]@{ executable = $launcher.Source; prefix = @("-3.10") }
}
$selectedPython = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-ValuePythonCandidate -Executable $candidate.executable -Prefix @($candidate.prefix)) {
        $selectedPython = $candidate
        break
    }
}
if (-not $selectedPython) {
    throw "No working Python 3.10 value-native runtime was found. Run check-value-101.cmd, install 64-bit CPython 3.10 if requested, then run install-value.cmd."
}
$pythonPath = $selectedPython.executable
$pythonPrefix = @($selectedPython.prefix)
$pythonArgs = @($pythonPrefix) + @("-m", "backend.server", "--host", "127.0.0.1", "--port", "8766")

function Stop-CurrentValueLaunch {
    param($BackendProcess, $FrontendProcess)
    foreach ($startedProcess in @($BackendProcess, $FrontendProcess)) {
        if ($startedProcess -and -not $startedProcess.HasExited) {
            Stop-Process -Id $startedProcess.Id -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
}

$backend = Start-Process -FilePath $pythonPath -ArgumentList $pythonArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

$frontendPort = 8800
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$uiServer = Join-Path $projectRoot "scripts\serve-value-ui.mjs"
try {
    $frontend = Start-Process -FilePath $nodePath `
        -ArgumentList @($uiServer, "--host", "127.0.0.1", "--port", $frontendPort) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog
} catch {
    Stop-CurrentValueLaunch -BackendProcess $backend -FrontendProcess $null
    throw
}

@{ backend_pid = $backend.Id; frontend_pid = $frontend.Id; started_at = (Get-Date).ToString("o") } |
    ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

$apiReady = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    try {
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/health" -TimeoutSec 1
        if ($apiHealth.service -ne "value-modular-local") { throw "Unexpected local API" }
        if (-not $apiHealth.authoritative_runtime_compatible) {
            throw "The local API started on Python $($apiHealth.python), not Python 3.10."
        }
        $apiReady = $true
        break
    } catch {
        if ($backend.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
}

if (-not $apiReady) {
    Stop-CurrentValueLaunch -BackendProcess $backend -FrontendProcess $frontend
    throw "The VALUE API did not start with $pythonPath. Run check-value-101.cmd for a plain-language diagnosis."
}

$frontendReady = $false
$clientRoot = Join-Path $projectRoot "dist\client"
$relativeAsset = $probeAsset.FullName.Substring($clientRoot.Length)
while ($relativeAsset.StartsWith("\")) { $relativeAsset = $relativeAsset.Substring(1) }
$relativeAsset = $relativeAsset.Replace("\", "/")
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/" -TimeoutSec 2 | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/$relativeAsset" -TimeoutSec 2 | Out-Null
        $frontendReady = $true
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $frontendReady) {
    Stop-CurrentValueLaunch -BackendProcess $backend -FrontendProcess $frontend
    throw "The API started, but the web page did not start. See $frontendLog"
}

Start-Process "http://127.0.0.1:$frontendPort"
Write-Host "VALUE started: http://127.0.0.1:$frontendPort"
Write-Host "Double-click stop-value.cmd to stop local services."
