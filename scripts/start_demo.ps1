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

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(300)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-PortOpen {
    param(
        [int]$Port,
        [string]$Name,
        [int]$TimeoutSeconds = 30,
        [string]$LogPath = ""
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    $message = "Timed out waiting for $Name on port $Port."
    if ($LogPath) {
        $message = "$message Check log: $LogPath"
    }
    throw $message
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

function Quote-CmdValue {
    param([string]$Value)
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Start-DemoCommandFile {
    param(
        [string]$ScriptPath,
        [string[]]$Lines,
        [string]$WorkingDirectory
    )

    $content = @("@echo off", "cd /d $(Quote-CmdValue $WorkingDirectory)") + $Lines
    [System.IO.File]::WriteAllLines($ScriptPath, $content, [System.Text.Encoding]::Default)

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = "cmd.exe"
    $startInfo.Arguments = "/d /c start ""OpenAgent Demo"" /min cmd.exe /d /c $(Quote-CmdValue $ScriptPath)"
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $process = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -eq $process) {
        throw "Failed to start command file: $ScriptPath"
    }
    return $process
}

function Open-DemoBrowser {
    param([string]$Url)

    $candidates = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
            $startInfo.FileName = $candidate
            [void]$startInfo.ArgumentList.Add("--new-window")
            [void]$startInfo.ArgumentList.Add($Url)
            $startInfo.UseShellExecute = $true
            [void][System.Diagnostics.Process]::Start($startInfo)
            return
        }
    }

    Write-Host "Chrome/Edge was not found. Open this URL manually in an external browser: $Url"
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $repoRoot "frontend"
$resolvedHarnessRoot = Resolve-HarnessRoot -Provided $HarnessRoot
$demoArtifactsRoot = Join-Path $repoRoot "artifacts"
$demoDbPath = Join-Path $demoArtifactsRoot "interview_demo.db"
$demoRunsRoot = Join-Path $demoArtifactsRoot "interview_demo_runs"
$demoLogsRoot = Join-Path $demoArtifactsRoot "demo_logs"
$apiUrl = "http://127.0.0.1:$ApiPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

$summary = [pscustomobject]@{
    RepoRoot = $repoRoot
    FrontendRoot = $frontendRoot
    HarnessRoot = $resolvedHarnessRoot
    DemoDatabase = $demoDbPath
    DemoRunsRoot = $demoRunsRoot
    DemoLogsRoot = $demoLogsRoot
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
New-Item -ItemType Directory -Force -Path $demoLogsRoot | Out-Null

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

    $apiOutLogPath = Join-Path $demoLogsRoot "api.out.log"
    $apiErrLogPath = Join-Path $demoLogsRoot "api.err.log"
    $apiScriptPath = Join-Path $demoLogsRoot "start_api.cmd"
    $apiLines = @(
        'set "DATABASE_URL=sqlite:///./artifacts/interview_demo.db"',
        "set ""HARNESS_ROOT=$resolvedHarnessRoot""",
        'set "HARNESS_PYTHON=python"',
        'set "HARNESS_PYTHONPATH=src"',
        'set "HARNESS_RUNS_ROOT=artifacts\interview_demo_runs"',
        'set "HARNESS_EXECUTOR=local"',
        'set "ALLOW_REAL_LLM_CALLS=true"',
        'set "REAL_API_BUDGET_LIMIT_CNY=1.0"',
        'set "AUTO_START_RUNS=true"',
        'set "ENABLE_REDIS=false"',
        'set "QUEUE_BACKEND=db"',
        'set "RUN_QUEUE_BACKEND=db"',
        "python -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort 1>>$(Quote-CmdValue $apiOutLogPath) 2>>$(Quote-CmdValue $apiErrLogPath)"
    )

    Start-DemoCommandFile -ScriptPath $apiScriptPath -Lines $apiLines -WorkingDirectory $repoRoot | Out-Null
    Wait-PortOpen -Port $ApiPort -Name "API" -TimeoutSeconds 30 -LogPath $apiErrLogPath
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

    $frontendOutLogPath = Join-Path $demoLogsRoot "frontend.out.log"
    $frontendErrLogPath = Join-Path $demoLogsRoot "frontend.err.log"
    $frontendScriptPath = Join-Path $demoLogsRoot "start_frontend.cmd"
    $frontendLines = @(
        "npm.cmd run dev -- --host 127.0.0.1 --port $FrontendPort 1>>$(Quote-CmdValue $frontendOutLogPath) 2>>$(Quote-CmdValue $frontendErrLogPath)"
    )

    Start-DemoCommandFile -ScriptPath $frontendScriptPath -Lines $frontendLines -WorkingDirectory $frontendRoot | Out-Null
    Wait-PortOpen -Port $FrontendPort -Name "frontend" -TimeoutSeconds 30 -LogPath $frontendErrLogPath
}

Write-Host ""
Write-Host "OpenAgent demo is starting."
Write-Host "API:      $apiUrl"
Write-Host "Frontend: $frontendUrl"
Write-Host "Harness:  $resolvedHarnessRoot"
Write-Host "Demo DB:  $demoDbPath"
Write-Host "Runs:     $demoRunsRoot"
Write-Host "Logs:     $demoLogsRoot"
Write-Host "Executor: HARNESS_EXECUTOR=local, QUEUE_BACKEND=db, ENABLE_REDIS=false"
Write-Host "Real-call mode: ALLOW_REAL_LLM_CALLS=true"
Write-Host "Budget:   REAL_API_BUDGET_LIMIT_CNY=1.0"
Write-Host ""
Write-Host "In the page: Evaluation -> Refresh dashboard, then Run Control -> scripted baseline -> Start evaluation."

if (-not $NoBrowser) {
    Open-DemoBrowser -Url $frontendUrl
}
