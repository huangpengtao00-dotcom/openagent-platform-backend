param(
    [string]$HarnessRoot = "",
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser,
    [switch]$KeepDemoData,
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

function Stop-PortListeners {
    param(
        [int]$Port,
        [string]$Name
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" }
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }

        Write-Host "Stopping existing $Name process on port $Port (PID $processId)."
        Stop-Process -Id $processId -Force
    }

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Test-PortOpen -Port $Port)) {
            return
        }
        Start-Sleep -Milliseconds 250
    }

    throw "Could not free $Name port $Port. Stop the process manually or rerun with another port."
}

function Get-DemoStatus {
    param([string]$ApiUrl)

    $client = [System.Net.WebClient]::new()
    $client.Encoding = [System.Text.Encoding]::UTF8
    try {
        return ($client.DownloadString("$ApiUrl/demo/status") | ConvertFrom-Json)
    } finally {
        $client.Dispose()
    }
}

function Assert-CompatibleBackend {
    param(
        [string]$ApiUrl,
        [string]$ExpectedHarnessRoot
    )

    try {
        $status = Get-DemoStatus -ApiUrl $ApiUrl
    } catch {
        throw "API port is already in use, but it is not this OpenAgent demo backend. Stop the process on the port or rerun with another -ApiPort."
    }

    try {
        $actual = (Resolve-Path -LiteralPath $status.harness_root -ErrorAction Stop).Path
    } catch {
        throw "API port is already running an incompatible OpenAgent demo backend with an unreadable HARNESS_ROOT: '$($status.harness_root)'. Stop the old backend before reusing demo data."
    }

    $expected = (Resolve-Path -LiteralPath $ExpectedHarnessRoot -ErrorAction Stop).Path
    if ($actual -ne $expected) {
        throw "API port is already running with a different HARNESS_ROOT. Expected '$expected' but got '$actual'. Stop the old backend before starting the demo."
    }

    if ($status.allow_real_llm_calls -ne $true) {
        throw "API port is already running with the backend LLM gate disabled. Stop it before starting the real-call demo."
    }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$resolvedHarnessRoot = Resolve-HarnessRoot -Provided $HarnessRoot
$demoArtifactsRoot = Join-Path $repoRoot "artifacts"
$demoDbPath = Join-Path $demoArtifactsRoot "interview_demo.db"
$demoRunsRoot = Join-Path $demoArtifactsRoot "interview_demo_runs"
$apiUrl = "http://127.0.0.1:$ApiPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

$summary = [pscustomobject]@{
    RepoRoot = $repoRoot
    FrontendRoot = $frontendRoot
    HarnessRoot = $resolvedHarnessRoot
    DemoDatabase = $demoDbPath
    DemoRunsRoot = $demoRunsRoot
    ApiUrl = $apiUrl
    FrontendUrl = $frontendUrl
    AllowRealLlmCalls = "true"
    RealApiBudgetLimitCny = "1.0"
    KeepDemoData = [bool]$KeepDemoData
}

if ($DryRun) {
    $summary | ConvertTo-Json
    exit 0
}

New-Item -ItemType Directory -Force -Path $demoArtifactsRoot | Out-Null

if (Test-PortOpen -Port $ApiPort) {
    if ($KeepDemoData) {
        Assert-CompatibleBackend -ApiUrl $apiUrl -ExpectedHarnessRoot $resolvedHarnessRoot
        Write-Host "API port $ApiPort is already running a compatible OpenAgent backend with real-call mode enabled. Reusing it because -KeepDemoData was set."
    } else {
        Stop-PortListeners -Port $ApiPort -Name "API"
    }
}

if (-not (Test-PortOpen -Port $ApiPort)) {
    if (-not $KeepDemoData) {
        Remove-Item -LiteralPath $demoDbPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $demoRunsRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $demoRunsRoot | Out-Null

    $previousEnv = @{
        DATABASE_URL = $env:DATABASE_URL
        HARNESS_ROOT = $env:HARNESS_ROOT
        HARNESS_PYTHON = $env:HARNESS_PYTHON
        HARNESS_PYTHONPATH = $env:HARNESS_PYTHONPATH
        HARNESS_RUNS_ROOT = $env:HARNESS_RUNS_ROOT
        ALLOW_REAL_LLM_CALLS = $env:ALLOW_REAL_LLM_CALLS
        REAL_API_BUDGET_LIMIT_CNY = $env:REAL_API_BUDGET_LIMIT_CNY
        AUTO_START_RUNS = $env:AUTO_START_RUNS
        ENABLE_REDIS = $env:ENABLE_REDIS
    }

    try {
        $env:DATABASE_URL = "sqlite:///./artifacts/interview_demo.db"
        $env:HARNESS_ROOT = $resolvedHarnessRoot
        $env:HARNESS_PYTHON = "python"
        $env:HARNESS_PYTHONPATH = "src"
        $env:HARNESS_RUNS_ROOT = "artifacts\interview_demo_runs"
        $env:ALLOW_REAL_LLM_CALLS = "true"
        $env:REAL_API_BUDGET_LIMIT_CNY = "1.0"
        $env:AUTO_START_RUNS = "true"
        $env:ENABLE_REDIS = "false"

        Start-Process `
            -FilePath "python" `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden
    } finally {
        foreach ($name in $previousEnv.Keys) {
            if ($null -eq $previousEnv[$name]) {
                Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
            } else {
                Set-Item -LiteralPath "Env:$name" -Value $previousEnv[$name]
            }
        }
    }
}

if (Test-PortOpen -Port $FrontendPort) {
    if ($KeepDemoData) {
        Write-Host "Frontend port $FrontendPort is already in use. Reusing existing frontend server because -KeepDemoData was set."
    } else {
        Stop-PortListeners -Port $FrontendPort -Name "frontend"
    }
}

if (-not (Test-PortOpen -Port $FrontendPort)) {
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
        Write-Host "Installing frontend dependencies..."
        Push-Location $frontendRoot
        try {
            & npm.cmd install
        } finally {
            Pop-Location
        }
    }
    $frontendCommand = "npm.cmd run dev -- --host 127.0.0.1 --port $FrontendPort"
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $frontendCommand) -WorkingDirectory $frontendRoot -WindowStyle Hidden
}

Write-Host ""
Write-Host "OpenAgent demo is starting."
Write-Host "API:      $apiUrl"
Write-Host "Frontend: $frontendUrl"
Write-Host "Harness:  $resolvedHarnessRoot"
Write-Host "Demo DB:  $demoDbPath"
Write-Host "Runs:     $demoRunsRoot"
Write-Host "Real-call mode: ALLOW_REAL_LLM_CALLS=true"
Write-Host "Budget:   REAL_API_BUDGET_LIMIT_CNY=1.0"
Write-Host ""
Write-Host "In the page: Evaluation -> Refresh dashboard, then Run Control -> scripted baseline -> Start evaluation."

if (-not $NoBrowser) {
    Start-Process $frontendUrl
}
