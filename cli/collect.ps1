[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$invokePwd = (Get-Location).Path
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$collectSh = Join-Path $scriptDir "collect.sh"

function Resolve-Python {
    param()
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
                    return $c.Source
                }
            }
        } catch {
            continue
        }
    }

    return $null
}

function Resolve-Bash {
    param()
    $bashCandidates = @(
        (Get-Command bash.exe -ErrorAction SilentlyContinue),
        (Get-Command bash -ErrorAction SilentlyContinue)
    )
    foreach ($candidate in $bashCandidates) {
        if ($null -eq $candidate) { continue }
        return $candidate.Source
    }
    return $null
}

function Resolve-AbsPath {
    param([string]$Path, [string]$Base)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Base $Path))
}

function Resolve-WorkingDir {
    param([string]$Requested)
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        $candidate = Resolve-AbsPath -Path $Requested -Base $invokePwd
        New-Item -ItemType Directory -Force -Path $candidate | Out-Null
        return $candidate
    }

    $collectInPwd = Resolve-AbsPath -Path "./collect" -Base $invokePwd
    if (Test-Path $collectInPwd) {
        return $collectInPwd
    }

    if (-not [string]::IsNullOrWhiteSpace($env:HOME)) {
        $collectInHome = Resolve-AbsPath -Path ".mmwk/collect" -Base $env:HOME
        if (Test-Path $collectInHome) {
            return $collectInHome
        }
    }

    New-Item -ItemType Directory -Force -Path $collectInPwd | Out-Null
    return $collectInPwd
}

function Extract-EnvValue {
    param([string]$FilePath, [string]$Key)
    if (-not (Test-Path $FilePath)) {
        return ""
    }
    foreach ($line in Get-Content $FilePath) {
        if (-not $line.Contains("=")) { continue }
        $parts = $line.Split("=", 2)
        if ($parts[0] -eq $Key) {
            return $parts[1]
        }
    }
    return ""
}

$directMode = $false
$hasBroker = $false
$serverStateDir = ""
for ($i = 0; $i -lt $Args.Length; $i++) {
    $arg = $Args[$i]
    if ($arg -eq "--trigger" -or $arg.StartsWith("--trigger=")) {
        $directMode = $true
        continue
    }

    if ($arg -eq "--broker" -or $arg.StartsWith("--broker=")) {
        $hasBroker = $true
        continue
    }

    if ($arg -eq "--server-state-dir") {
        if ($i + 1 -ge $Args.Length) {
            Write-Error "Missing value for --server-state-dir"
            exit 1
        }
        $serverStateDir = $Args[$i + 1]
        $i++
        continue
    }
}

if ($directMode) {
    $python = Resolve-Python
    if ($null -eq $python) {
        Write-Error 'Python 3.10+ not found.'
        exit 1
    }

    if (-not $hasBroker -and [string]::IsNullOrWhiteSpace($env:MMWK_SERVER_MQTT_URI)) {
        $defaultStateDir = Resolve-AbsPath -Path "./build_output/local_server" -Base $invokePwd
        if ([string]::IsNullOrWhiteSpace($serverStateDir)) {
            $serverStateDir = $defaultStateDir
        } else {
            $serverStateDir = Resolve-AbsPath -Path $serverStateDir -Base $invokePwd
        }
        $serverEnvFile = Join-Path $serverStateDir "server.env"
        $mqttUri = Extract-EnvValue -FilePath $serverEnvFile -Key "MMWK_SERVER_MQTT_URI"
        if (-not [string]::IsNullOrWhiteSpace($mqttUri)) {
            $env:MMWK_SERVER_MQTT_URI = $mqttUri
        }
    }

    Set-Location $invokePwd
    & $python -m mmwk.tools.collect_raw @Args
    exit $LASTEXITCODE
}

$bash = Resolve-Bash
if ($null -ne $bash) {
    & $bash $collectSh @Args
    exit $LASTEXITCODE
}

if (($Args -contains "-h") -or ($Args -contains "--help")) {
    Write-Host "collect.ps1 -- registry-backed raw collection helper"
    Write-Host "Usage:"
    Write-Host "  ./collect.ps1 --device-id ID [--duration SEC] [--working DIR] [--reboot]"
    Write-Host "  ./collect.ps1 --trigger none|radar-restart|device-reboot [forward-options]"
    Write-Host "Install Git Bash for full collect.sh compatibility or run with --trigger for pure-MQTT mode."
    exit 0
}

# Minimal Windows fallback for non-trigger mode when bash is unavailable.
$deviceId = ""
$duration = ""
$working = ""
$reboot = $false
for ($i = 0; $i -lt $Args.Length; $i++) {
    switch ($Args[$i]) {
        "--device-id" {
            if ($i + 1 -ge $Args.Length) {
                Write-Error "Missing value for --device-id"
                exit 1
            }
            $deviceId = $Args[$i + 1]
            $i++
        }
        "--duration" {
            if ($i + 1 -ge $Args.Length) {
                Write-Error "Missing value for --duration"
                exit 1
            }
            $duration = $Args[$i + 1]
            $i++
        }
        "--working" {
            if ($i + 1 -ge $Args.Length) {
                Write-Error "Missing value for --working"
                exit 1
            }
            $working = $Args[$i + 1]
            $i++
        }
        "--reboot" {
            $reboot = $true
        }
        default {
            Write-Error "Unsupported argument in non-bash fallback mode: $($Args[$i])"
            exit 1
        }
    }
}

if ([string]::IsNullOrWhiteSpace($deviceId)) {
    Write-Error "--device-id is required"
    exit 1
}

$workingDir = Resolve-WorkingDir -Requested $working
$registryPath = Join-Path $workingDir "device.yml"
if (-not (Test-Path $registryPath)) {
    Write-Error "device registry not found: $registryPath"
    exit 1
}

try {
    $recordRoot = Get-Content $registryPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Error "invalid device registry JSON: $registryPath"
    exit 1
}

if (-not $recordRoot.PSObject.Properties.Name.Contains("devices")) {
    Write-Error "device registry 'devices' missing: $registryPath"
    exit 1
}

$devices = $recordRoot.devices
if (-not $devices.PSObject.Properties.Name.Contains($deviceId)) {
    Write-Error "device id not found in registry: $deviceId"
    exit 1
}

$deviceRecord = $devices.$deviceId
$mqttServer = [string]$deviceRecord.mqtt_server
$mqttPort = [string]$deviceRecord.mqtt_port
if ([string]::IsNullOrWhiteSpace($mqttServer) -or [string]::IsNullOrWhiteSpace($mqttPort)) {
    Write-Error "Device record missing mqtt_server or mqtt_port: $deviceId"
    exit 1
}

$timestamp = if ([string]::IsNullOrWhiteSpace($env:MMWK_TEST_COLLECT_TIMESTAMP)) {
    (Get-Date).ToString("yyyyMMdd-HHmmss")
} else {
    $env:MMWK_TEST_COLLECT_TIMESTAMP
}
$outputPrefix = "${timestamp}_"
$outputDir = Join-Path (Join-Path $workingDir "data") $deviceId
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$python = Resolve-Python
if ($null -eq $python) {
    Write-Error 'Python 3.10+ not found.'
    exit 1
}

$liveArgs = @(
    "--device-id", $deviceId,
    "--mqtt-server", $mqttServer,
    "--mqtt-port", $mqttPort,
    "--output-dir", $outputDir,
    "--output-prefix", $outputPrefix
)

if (-not [string]::IsNullOrWhiteSpace($duration)) {
    $liveArgs += @("--duration", $duration)
}
if ($reboot) {
    $liveArgs += @("--reboot")
}

& $python -m mmwk.tools.collect_live @liveArgs
exit $LASTEXITCODE
