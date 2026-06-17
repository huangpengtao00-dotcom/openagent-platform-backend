param(
    [string]$HarnessRoot = "",
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Resolve-HarnessRoot {
    param([string]$Provided)

    if ($Provided -and (Test-Path -LiteralPath $Provided)) {
        return (Resolve-Path -LiteralPath $Provided).Path
    }

    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $repoRoot "..")).Path
    $candidates = @(
        (Join-Path $workspaceRoot "02_OpenAgent_Harness"),
        (Join-Path $workspaceRoot "Interview-Project-Bundle-20260617-233344\02_OpenAgent_Harness"),
        (Join-Path $workspaceRoot "简历项目整理_20260617\01_OpenAgent_Harness"),
        (Join-Path $workspaceRoot "OpenAgent-Harness-v1-final"),
        (Join-Path $workspaceRoot "OpenAgent-Harness")
    )

    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath (Join-Path $candidate "pyproject.toml")) -and
            (Test-Path -LiteralPath (Join-Path $candidate "src\openagent_harness\cli.py"))) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "Could not find OpenAgent Harness. Pass -HarnessRoot with the path to the Harness checkout."
}

function Test-PortOpen {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" } |
        Select-Object -First 1
    return $null -ne $connection
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$resolvedHarnessRoot = Resolve-HarnessRoot -Provided $HarnessRoot
$apiUrl = "http://127.0.0.1:$ApiPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

$summary = [pscustomobject]@{
    RepoRoot = $repoRoot
    FrontendRoot = $frontendRoot
    HarnessRoot = $resolvedHarnessRoot
    ApiUrl = $apiUrl
    FrontendUrl = $frontendUrl
    AllowRealLlmCalls = "false"
}

if ($DryRun) {
    $summary | ConvertTo-Json
    exit 0
}

if (Test-PortOpen -Port $ApiPort) {
    Write-Host "API port $ApiPort is already in use. Reusing existing backend if it is OpenAgent."
} else {
    $backendCommand = @"
cd /d "$repoRoot"
set HARNESS_ROOT=$resolvedHarnessRoot
set HARNESS_PYTHON=python
set HARNESS_PYTHONPATH=src
set HARNESS_RUNS_ROOT=artifacts\interview_demo_runs
set ALLOW_REAL_LLM_CALLS=false
set AUTO_START_RUNS=true
set ENABLE_REDIS=false
python -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort
"@
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", "cmd /c `"$backendCommand`"") -WorkingDirectory $repoRoot
}

if (Test-PortOpen -Port $FrontendPort) {
    Write-Host "Frontend port $FrontendPort is already in use. Reusing existing frontend server."
} else {
    $frontendCommand = @"
cd /d "$frontendRoot"
if not exist node_modules npm install
npm run dev -- --host 127.0.0.1 --port $FrontendPort
"@
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", "cmd /c `"$frontendCommand`"") -WorkingDirectory $frontendRoot
}

Write-Host ""
Write-Host "OpenAgent demo is starting."
Write-Host "API:      $apiUrl"
Write-Host "Frontend: $frontendUrl"
Write-Host "Harness:  $resolvedHarnessRoot"
Write-Host "Safe mode: ALLOW_REAL_LLM_CALLS=false"
Write-Host ""
Write-Host "In the page: Runs -> Safe scripted retry-429 -> Start selected evaluation -> Refresh status."

if (-not $NoBrowser) {
    Start-Process $frontendUrl
}
