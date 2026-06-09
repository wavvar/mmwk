[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$configSh = Join-Path $scriptDir "config.sh"

if (-not (Test-Path -Path $configSh -PathType Leaf)) {
    Write-Error "Config wrapper not found: $configSh"
    exit 1
}

$bashCandidates = @(
    (Get-Command bash.exe -ErrorAction SilentlyContinue),
    (Get-Command bash -ErrorAction SilentlyContinue)
)
foreach ($bash in $bashCandidates) {
    if ($null -eq $bash) { continue }
    & $bash.Source $configSh @Args
    exit $LASTEXITCODE
}

Write-Error @"
config.ps1 requires bash in this environment for full registry-task parity.
Please install a POSIX shell (e.g., Git Bash) and retry, or run:
  bash $configSh [args]
"@
exit 1
