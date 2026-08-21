$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    python -m simops_studio demo --force
    Write-Host ""
    Write-Host "Report: $repo\outputs\demo\report.html"
    Write-Host "Dashboard: python -m simops_studio dashboard examples\project.yaml"
}
finally {
    Pop-Location
}

