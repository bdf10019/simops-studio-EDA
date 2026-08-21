$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    python -m pip check
    & "$PSScriptRoot\privacy-check.ps1"
    python -m compileall -q src tests
    python -m unittest discover -s tests -v
    python -m simops_studio validate examples/project.yaml
    python -m simops_studio pcb-check examples/project.yaml
    python -m simops_studio simulate examples/project.yaml --case-index 0
}
finally {
    Pop-Location
}
