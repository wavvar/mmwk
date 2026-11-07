[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$invokePwd = (Get-Location).ProviderPath
$scriptDir = [System.IO.Path]::GetFullPath($PSScriptRoot)
$pathSeparator = [System.IO.Path]::PathSeparator
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $scriptDir
} elseif (($env:PYTHONPATH -split [regex]::Escape([string]$pathSeparator)) -notcontains $scriptDir) {
    $env:PYTHONPATH = "$scriptDir$pathSeparator$env:PYTHONPATH"
}

$python = $null
$pythonCandidates = @(
    (Get-Command python -ErrorAction SilentlyContinue),
    (Get-Command py -ErrorAction SilentlyContinue)
)

foreach ($c in $pythonCandidates) {
    if ($null -eq $c) { continue }
    try {
        $ver = & $c.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($ver -match '^(\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
                $python = $c.Source
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $python) {
    Write-Error 'Python 3.10+ not found.'
    exit 1
}

$runner = $python
Set-Location -LiteralPath $invokePwd
& $runner -m mmwk @Args
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) { exit $exitCode }
