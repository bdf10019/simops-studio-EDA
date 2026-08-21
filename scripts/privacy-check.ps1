$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$self = "scripts/privacy-check.ps1"
$tracked = @(git -C $repo ls-files)

if ($LASTEXITCODE -ne 0) {
    throw "Unable to enumerate tracked files."
}

$blockedExtensions = @(".db", ".sqlite", ".sqlite3", ".joblib", ".pkl", ".raw", ".log")
$patterns = @(
    @{ Name = "private key material"; Value = "-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----" },
    @{ Name = "known token prefix"; Value = "(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,})" },
    @{ Name = "credential assignment"; Value = "(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[`"']?[A-Za-z0-9_./+=-]{8,}" },
    @{ Name = "Windows user-home path"; Value = "(?i)[A-Z]:\\Users\\[^\\/\s]+" }
)

$findings = [System.Collections.Generic.List[string]]::new()
foreach ($relative in $tracked) {
    $path = Join-Path $repo $relative
    $info = Get-Item -LiteralPath $path
    if ($info.Length -gt 1MB) {
        $findings.Add("tracked file exceeds 1 MiB: $relative")
    }
    if ($blockedExtensions -contains $info.Extension.ToLowerInvariant()) {
        $findings.Add("generated or sensitive extension is tracked: $relative")
    }
    if ($relative -eq $self) {
        continue
    }
    $content = [System.IO.File]::ReadAllText($path)
    foreach ($pattern in $patterns) {
        if ([regex]::IsMatch($content, $pattern.Value)) {
            $findings.Add("$($pattern.Name): $relative")
        }
    }
}

if ($findings.Count -gt 0) {
    $findings | ForEach-Object { Write-Error $_ }
    throw "Privacy check failed with $($findings.Count) finding(s)."
}

Write-Host "Privacy checks passed for $($tracked.Count) tracked files."
