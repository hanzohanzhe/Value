param([switch]$RemoveResearchData)

$ErrorActionPreference = "Stop"
$projectRoot = (Split-Path -Parent $PSScriptRoot)
& (Join-Path $PSScriptRoot "stop-local.ps1")
foreach ($name in @(".venv", "node_modules", "dist", ".next")) {
    $target = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $name))
    if (-not $target.StartsWith([System.IO.Path]::GetFullPath($projectRoot), [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the VALUE installation: $target"
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
if ($RemoveResearchData) {
    if (-not $env:VALUE_DATA_HOME) { throw "Set VALUE_DATA_HOME explicitly before requesting research-data removal." }
    $dataTarget = [System.IO.Path]::GetFullPath($env:VALUE_DATA_HOME)
    $confirmation = Read-Host "Type the exact research-data path to remove: $dataTarget"
    if ($confirmation -ne $dataTarget) { throw "Exact path confirmation did not match. Research data was preserved." }
    Remove-Item -LiteralPath $dataTarget -Recurse -Force
} else {
    Write-Host "Application dependencies removed. Research data was preserved."
}
