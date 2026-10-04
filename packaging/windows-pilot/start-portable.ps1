param([switch]$Stop, [switch]$NoDialog)

$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "VALUE"
$projectRoot = Join-Path $installRoot "app"
$stateRoot = Join-Path $installRoot "state"
$diagnostics = Join-Path $installRoot "diagnostics"
$python = Join-Path $projectRoot "runtime\python\python.exe"
$node = Join-Path $projectRoot "runtime\node\node.exe"
$env:VALUE_DATA_HOME = $stateRoot
$env:VALUE_PORTABLE_PYTHON = $python
$env:VALUE_PORTABLE_NODE = $node
New-Item -ItemType Directory -Force -Path $diagnostics, $stateRoot | Out-Null

try {
    if ($Stop) {
        & (Join-Path $projectRoot "scripts\stop-local.ps1")
        exit $LASTEXITCODE
    }
    if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $node)) {
        throw "The private VALUE runtime is incomplete. Re-run VALUE-Setup.exe."
    }
    & $python (Join-Path $projectRoot "scripts\install_synthetic_pack.py") --state-root $stateRoot --value-101-only
    if ($LASTEXITCODE -ne 0) { throw "VALUE data installation failed." }
    & (Join-Path $projectRoot "scripts\start-portable-local.ps1") -Python $python -Node $node -StateRoot $stateRoot
} catch {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $report = Join-Path $diagnostics "startup-$stamp.txt"
    $_ | Out-String | Set-Content -LiteralPath $report -Encoding UTF8
    if (-not $NoDialog) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "VALUE could not start. A diagnostic report was saved to:`n$report",
            "VALUE",
            "OK",
            "Error"
        ) | Out-Null
    }
    exit 1
}
