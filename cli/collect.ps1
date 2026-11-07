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

function Resolve-Python {
    foreach ($candidate in @(
        (Get-Command python -ErrorAction SilentlyContinue),
        (Get-Command py -ErrorAction SilentlyContinue)
    )) {
        if ($null -eq $candidate) { continue }
        try {
            $version = & $candidate.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ($version -match '^(\d+)\.(\d+)') {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
                    return $candidate.Source
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

$python = Resolve-Python
if ($null -eq $python) {
    Write-Error 'Python 3.10+ not found.'
    exit 1
}

$directMode = $false
$localEngineMode = $false
$hasBroker = $false
$serverStateDir = ""
$did = ""
$duration = ""
$working = ""
$reboot = $false
$mode = "host"
$attach = $false

for ($i = 0; $i -lt $Args.Length; $i++) {
    $arg = $Args[$i]
    if ($arg -eq "--trigger" -or $arg.StartsWith("--trigger=")) {
        $directMode = $true
        continue
    }
    if ($arg -eq "--broker" -or $arg.StartsWith("--broker=")) {
        $hasBroker = $true
    }
    if ($arg -eq "--transport" -or $arg.StartsWith("--transport=") -or
        $arg -eq "--port" -or $arg.StartsWith("--port=") -or
        $arg -eq "-p" -or $arg.StartsWith("-p=") -or
        $arg -eq "--baudrate" -or $arg.StartsWith("--baudrate=") -or
        $arg -eq "-b" -or $arg.StartsWith("-b=") -or
        $arg -eq "--raw-baud" -or $arg.StartsWith("--raw-baud=") -or
        $arg -eq "--escape" -or $arg.StartsWith("--escape=") -or
        $arg -eq "--ctrl-transport" -or $arg.StartsWith("--ctrl-transport=") -or
        $arg -eq "--data-transport" -or $arg.StartsWith("--data-transport=") -or
        $arg -eq "--data-topic" -or $arg.StartsWith("--data-topic=") -or
        $arg -eq "--resp-topic" -or $arg.StartsWith("--resp-topic=") -or
        $arg -eq "--prod" -or $arg.StartsWith("--prod=") -or
        $arg -eq "--oid" -or $arg.StartsWith("--oid=") -or
        $arg -eq "--cid" -or $arg.StartsWith("--cid=") -or
        $arg -eq "--protocol" -or $arg.StartsWith("--protocol=") -or
        $arg -eq "--reset" -or $arg -eq "--timeout" -or $arg.StartsWith("--timeout=") -or
        $arg -eq "--data-ready-timeout" -or $arg.StartsWith("--data-ready-timeout=") -or
        $arg -eq "--resp-optional" -or $arg -eq "--verbose" -or $arg -eq "-v") {
        $localEngineMode = $true
        continue
    }
    if ($arg -eq "--broker" -or $arg.StartsWith("--broker=") -or
        $arg -eq "--mqtt-port" -or $arg.StartsWith("--mqtt-port=") -or
        $arg -eq "--mqtt-user" -or $arg.StartsWith("--mqtt-user=") -or
        $arg -eq "--mqtt-password" -or $arg.StartsWith("--mqtt-password=") -or
        $arg -eq "--mqtt-ca" -or $arg.StartsWith("--mqtt-ca=") -or
        $arg -eq "--cfg" -or $arg.StartsWith("--cfg=") -or
        $arg -eq "--data-output" -or $arg.StartsWith("--data-output=") -or
        $arg -eq "--resp-output" -or $arg.StartsWith("--resp-output=") -or
        $arg -eq "--wire-output" -or $arg.StartsWith("--wire-output=") -or
        $arg -eq "--summary-output" -or $arg.StartsWith("--summary-output=") -or
        $arg -eq "--events-output" -or $arg.StartsWith("--events-output=") -or
        $arg -eq "--allow-lossy" -or $arg -eq "--overwrite") {
        $localEngineMode = $true
        continue
    }
    if ($arg -eq "--broker" -or $arg.StartsWith("--broker=")) {
        $hasBroker = $true
        continue
    }
    if ($arg -eq "--server-state-dir") {
        if ($i + 1 -ge $Args.Length) { Write-Error "Missing value for --server-state-dir"; exit 1 }
        $serverStateDir = $Args[$i + 1]
        $i++
        continue
    }
}

# The main collection surface is the same Python engine used by run.ps1. The
# trigger helper remains an explicit advanced MQTT entrypoint, and both paths
# run directly under Python without requiring Git Bash.
if ($directMode) {
    if (-not $hasBroker -and [string]::IsNullOrWhiteSpace($env:MMWK_SERVER_MQTT_URI)) {
        if ([string]::IsNullOrWhiteSpace($serverStateDir)) {
            $serverStateDir = Join-Path $invokePwd "build_output/local_server"
        } elseif (-not [System.IO.Path]::IsPathRooted($serverStateDir)) {
            $serverStateDir = Join-Path $invokePwd $serverStateDir
        }
        $serverEnvFile = Join-Path ([System.IO.Path]::GetFullPath($serverStateDir)) "server.env"
        if (Test-Path $serverEnvFile) {
            foreach ($line in Get-Content $serverEnvFile) {
                if ($line -match '^MMWK_SERVER_MQTT_URI=(.*)$') {
                    $env:MMWK_SERVER_MQTT_URI = $Matches[1]
                    break
                }
            }
        }
    }
    Set-Location -LiteralPath $invokePwd
    & $python -m mmwk.tools.collect_raw @Args
    exit $LASTEXITCODE
}

if ($localEngineMode -or (($Args -contains "--help") -or ($Args -contains "-h"))) {
    Set-Location -LiteralPath $invokePwd
    & $python -m mmwk collect @Args
    exit $LASTEXITCODE
}

# Preserve the registry-backed helper mode without a Bash dependency.
for ($i = 0; $i -lt $Args.Length; $i++) {
    switch ($Args[$i]) {
        "--did" {
            if ($i + 1 -ge $Args.Length) { Write-Error "Missing value for --did"; exit 1 }
            $did = $Args[$i + 1]; $i++
        }
        "--duration" {
            if ($i + 1 -ge $Args.Length) { Write-Error "Missing value for --duration"; exit 1 }
            $duration = $Args[$i + 1]; $i++
        }
        "--working" {
            if ($i + 1 -ge $Args.Length) { Write-Error "Missing value for --working"; exit 1 }
            $working = $Args[$i + 1]; $i++
        }
        "--reboot" { $reboot = $true }
        "--mode" {
            if ($i + 1 -ge $Args.Length) { Write-Error "Missing value for --mode"; exit 1 }
            $mode = $Args[$i + 1]; $i++
        }
        "--attach" { $attach = $true }
        default { Write-Error "Unsupported argument in registry mode: $($Args[$i])"; exit 1 }
    }
}

if ([string]::IsNullOrWhiteSpace($did)) {
    Write-Error "--did is required for registry-backed collection"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($working)) {
    $workingDir = Join-Path $invokePwd "collect"
} elseif ([System.IO.Path]::IsPathRooted($working)) {
    $workingDir = $working
} else {
    $workingDir = Join-Path $invokePwd $working
}
$workingDir = [System.IO.Path]::GetFullPath($workingDir)
New-Item -ItemType Directory -Force -Path $workingDir | Out-Null
$registryPath = Join-Path $workingDir "device.yml"
if (-not (Test-Path $registryPath)) { Write-Error "device registry not found: $registryPath"; exit 1 }

try {
    $registry = Get-Content $registryPath -Raw | ConvertFrom-Json
    $deviceRecord = $registry.devices.$did
} catch {
    Write-Error "invalid device registry JSON: $registryPath"
    exit 1
}
if ($null -eq $deviceRecord) { Write-Error "DID not found in registry: $did"; exit 1 }
$mqttServer = [string]$deviceRecord.mqtt_server
$mqttPort = [string]$deviceRecord.mqtt_port
if ([string]::IsNullOrWhiteSpace($mqttServer) -or [string]::IsNullOrWhiteSpace($mqttPort)) {
    Write-Error "Device record missing mqtt_server or mqtt_port: $did"
    exit 1
}

$timestamp = if ([string]::IsNullOrWhiteSpace($env:MMWK_TEST_COLLECT_TIMESTAMP)) {
    (Get-Date).ToString("yyyyMMdd-HHmmss")
} else { $env:MMWK_TEST_COLLECT_TIMESTAMP }
$outputDir = Join-Path (Join-Path $workingDir "data") $did
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$liveArgs = @(
    "--did", $did,
    "--mqtt-server", $mqttServer,
    "--mqtt-port", $mqttPort,
    "--output-dir", $outputDir,
    "--output-prefix", "${timestamp}_"
)
if (-not [string]::IsNullOrWhiteSpace($duration)) { $liveArgs += @("--duration", $duration) }
if ($reboot) { $liveArgs += @("--reboot") }
if ($mode -ne "host") { $liveArgs += @("--mode", $mode) }
if ($attach) { $liveArgs += @("--attach") }

Set-Location -LiteralPath $invokePwd
& $python -m mmwk.tools.collect_live @liveArgs
exit $LASTEXITCODE
