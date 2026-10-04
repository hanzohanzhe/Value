param(
    [string]$InstallRoot = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
if (-not $InstallRoot) {
    $InstallRoot = Join-Path $env:LOCALAPPDATA "VALUE-101"
}
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$appRoot = Join-Path $InstallRoot "app"
$stateRoot = Join-Path $InstallRoot "state"
$checks = @()

function Add-Check {
    param([string]$Id, [string]$Label, [bool]$Passed, [string]$Detail)
    $script:checks += [pscustomobject][ordered]@{
        id = $Id
        label = $Label
        status = if ($Passed) { "pass" } else { "fail" }
        detail = $Detail
    }
}

$python = Join-Path $appRoot "runtime\python\python.exe"
$node = Join-Path $appRoot "runtime\node\node.exe"
$frontend = Join-Path $appRoot "dist\server\index.js"
$guide = Join-Path $appRoot "START-HERE-VALUE-101-Guide.pdf"
Add-Check "python" "Private Python 3.10" (Test-Path -LiteralPath $python -PathType Leaf) $python
Add-Check "node" "Private Node runtime" (Test-Path -LiteralPath $node -PathType Leaf) $node
Add-Check "frontend" "Built website" (Test-Path -LiteralPath $frontend -PathType Leaf) $frontend
Add-Check "guide" "English guide" (Test-Path -LiteralPath $guide -PathType Leaf) $guide

$packIds = @(
    "value-101-baseline-v1",
    "value-101-network-v1"
)
foreach ($packId in $packIds) {
    $manifestPath = Join-Path $stateRoot "data-packs\$packId\manifest.json"
    $valid = $false
    $detail = "missing pack: $packId"
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try {
            $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
            $roles = @($manifest.bindings.psobject.Properties)
            $minimumRoles = if ($packId -eq "value-101-network-v1") { 33 } else { 25 }
            $valid = $manifest.id -eq $packId -and $roles.Count -eq $minimumRoles
            $detail = "$packId has $($roles.Count) declared roles."
        } catch {
            $detail = "$packId manifest cannot be read."
        }
    }
    Add-Check "pack_$packId" $packId $valid $detail
}

foreach ($port in 8766, 8800) {
    $netstat = Get-Command netstat.exe -ErrorAction SilentlyContinue
    $inspectionWorked = $false
    $listeners = @()
    if ($netstat) {
        $netstatRows = @(& $netstat.Source -ano -p tcp)
        if ($LASTEXITCODE -eq 0) {
            $inspectionWorked = $true
            $listeners = @(
                $netstatRows | Where-Object {
                    $_ -match "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+\d+\s*$"
                }
            )
        }
    } else {
        try {
            $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)
            $inspectionWorked = $true
        } catch {
            $inspectionWorked = $false
        }
    }
    $passed = $inspectionWorked -and $listeners.Count -eq 0
    if (-not $inspectionWorked) {
        $detail = "Could not inspect local port $port."
    } elseif ($listeners.Count -eq 0) {
        $detail = "Port $port is free."
    } else {
        $detail = "occupied port: $port is already in use."
    }
    Add-Check "port_$port" "Local port $port" $passed $detail
}

$ready = @($checks | Where-Object { $_.status -eq "fail" }).Count -eq 0
$report = [pscustomobject][ordered]@{
    schema_version = "value.101-pilot-check/v1"
    install_root = $InstallRoot
    ready = $ready
    action = if ($ready) { $null } else { "Reinstall VALUE-101-Setup.exe or close the application using an occupied port." }
    checks = $checks
}

if ($Json) {
    $report | ConvertTo-Json -Depth 5 -Compress
} else {
    Write-Host "VALUE 101 pilot check"
    foreach ($check in $checks) {
        $marker = if ($check.status -eq "pass") { "PASS" } else { "FAIL" }
        Write-Host "[$marker] $($check.label): $($check.detail)"
    }
    if ($ready) {
        Write-Host "READY: VALUE 101 can start offline."
    } else {
        Write-Host "NOT READY: reinstall VALUE-101-Setup.exe or close the application using an occupied port."
    }
}

if ($ready) { exit 0 } else { exit 1 }
