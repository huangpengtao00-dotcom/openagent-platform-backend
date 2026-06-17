param(
    [string]$Server = "http://127.0.0.1:8000",
    [string]$TaskPath = "../OpenAgent-Harness-v1-final/examples/deepseek_real_task.json",
    [string]$Model = "deepseek-v4-flash",
    [int]$TimeoutSeconds = 180,
    [switch]$Live,
    [switch]$ConfirmSpend
)

$ErrorActionPreference = "Stop"

if (-not $Live -or -not $ConfirmSpend) {
    throw "Refusing to run a real DeepSeek call. Re-run with -Live -ConfirmSpend after confirming the demo budget."
}

if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    throw "DEEPSEEK_API_KEY is not set in this shell. Set it locally; never commit it."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceDir = Join-Path (Get-Location) "evidence/deepseek-$timestamp"
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null

$health = Invoke-RestMethod -Method Get -Uri "$Server/health"
$health | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $evidenceDir "01-health.json")

$taskBody = @{
    name = "deepseek-real-evidence-$timestamp"
    description = "Manual low-cost DeepSeek evidence run"
    harness_task_path = $TaskPath
} | ConvertTo-Json

$task = Invoke-RestMethod -Method Post -Uri "$Server/tasks" -ContentType "application/json" -Body $taskBody
$task | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $evidenceDir "02-task.json")

$runBody = @{
    task_id = $task.task_id
    mode = "api"
    model = $Model
    allow_llm_calls = $true
    timeout_seconds = $TimeoutSeconds
} | ConvertTo-Json

$run = Invoke-RestMethod `
    -Method Post `
    -Uri "$Server/runs" `
    -Headers @{"Idempotency-Key"="deepseek-$timestamp"; "X-User-ID"="manual-demo"} `
    -ContentType "application/json" `
    -Body $runBody
$run | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $evidenceDir "03-run-created.json")

$deadline = (Get-Date).AddSeconds($TimeoutSeconds + 30)
do {
    Start-Sleep -Seconds 2
    $current = Invoke-RestMethod -Method Get -Uri "$Server/runs/$($run.run_id)"
    $current | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $evidenceDir "04-run-latest.json")
    if ($current.status -in @("pass", "fail", "timeout", "cancelled")) {
        break
    }
} while ((Get-Date) -lt $deadline)

$metrics = Invoke-RestMethod -Method Get -Uri "$Server/metrics/cost"
$metrics | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $evidenceDir "05-cost-metrics.json")

"Evidence saved to $evidenceDir"
"Run status: $($current.status)"
"Estimated USD: $($metrics.estimated_cost_usd)"
"Open report in browser: $Server/runs/$($run.run_id)/report"
