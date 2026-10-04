param(
    [ValidateSet("value-native", "doctoral-reproduction", "open-core", "solver", "full")]
    [string]$Capability = "value-native",
    [string]$DataHome = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $DataHome) {
    $legacyState = Join-Path $projectRoot ".gridform"
    $DataHome = if (Test-Path -LiteralPath $legacyState) { $legacyState } else { Join-Path $env:LOCALAPPDATA "VALUE" }
}
$env:VALUE_DATA_HOME = [System.IO.Path]::GetFullPath($DataHome)
New-Item -ItemType Directory -Force -Path $env:VALUE_DATA_HOME | Out-Null

$nodeVersion = (& node.exe --version 2>$null)
if (-not $nodeVersion -or [int]($nodeVersion.TrimStart('v').Split('.')[0]) -lt 22) {
    throw "Install Node.js 22 LTS or later, then run this installer again."
}
$launcher = Get-Command py.exe -ErrorAction Stop
& $launcher.Source -3.10 -c "import sys; assert sys.version_info[:2] == (3, 10), sys.version"
if ($LASTEXITCODE -ne 0) { throw "Install 64-bit CPython 3.10, then run this installer again." }

$venv = Join-Path $projectRoot ".venv"
if (-not (Test-Path -LiteralPath (Join-Path $venv "Scripts\python.exe"))) {
    & $launcher.Source -3.10 -m venv $venv
}
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade "pip==25.1.1"
$lock = switch ($Capability) {
    "open-core" { "value-open-core-py310.lock" }
    "value-native" { "value-native-py310.lock" }
    "doctoral-reproduction" { "value-doctoral-reproduction-py310.lock" }
    "solver" { "value-perfect-foresight-py310.lock" }
    default { "value-all-py310.lock" }
}
& $python -m pip install -r (Join-Path $projectRoot "requirements\$lock")
if ($LASTEXITCODE -ne 0) { throw "The locked Python environment could not be installed." }

Push-Location $projectRoot
try {
    & $python scripts\verify_install_scripts.py
    if ($LASTEXITCODE -ne 0) { throw "The npm lock contains an unreviewed dependency install script." }
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "The locked frontend environment could not be installed." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "The VALUE website did not build." }
    & $python scripts\verify_locks.py (Join-Path $projectRoot "requirements\$lock")
    # Installs the contract fixture and all three VALUE 101 teaching packs without replacing local revisions.
    & $python scripts\install_synthetic_pack.py --state-root $env:VALUE_DATA_HOME
    $doctorCapability = if ($Capability -eq "doctoral-reproduction" -or $Capability -eq "full") { "doctoral-reproduction" } else { "value-native" }
    & $python scripts\doctor.py --state-root $env:VALUE_DATA_HOME --capability $doctorCapability
} finally {
    Pop-Location
}

Write-Host "VALUE is installed. Double-click start-value.cmd."
Write-Host "Research data directory: $env:VALUE_DATA_HOME"
Write-Host "Installed runtime capability: $Capability"
