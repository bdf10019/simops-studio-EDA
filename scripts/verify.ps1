$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    python -m compileall -q src tests
    python -m unittest discover -s tests -v
    python -m simops_studio validate examples/project.yaml
}
finally {
    Pop-Location
}

