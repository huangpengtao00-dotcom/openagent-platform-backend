param(
    [string]$OutputRoot = "",
    [string]$HarnessRoot = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path (Split-Path -Parent $RepoRoot) "OpenAgent-Release-Bundles"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$RunnableRoot = Join-Path $OutputRoot "openagent-platform-runnable"
$CleanRoot = Join-Path $OutputRoot "openagent-platform-interview-clean"

$excludedDirs = @(
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "runs",
    "runs_deepseek",
    "runs_deepseek_real",
    "artifacts",
    "test_artifacts",
    ".codex_tmp"
)

$excludedFiles = @(
    ".env",
    ".env.local",
    ".env.development",
    ".env.test",
    ".env.production",
    "*.pyc",
    "*.pyo",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.zip"
)

function Reset-Directory {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $resolved = (Resolve-Path -LiteralPath $Path).Path
        if (-not $resolved.StartsWith($OutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove path outside output root: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Copy-Project {
    param(
        [string]$Source,
        [string]$Destination
    )
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    robocopy $Source $Destination /E /XD $excludedDirs /XF $excludedFiles /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed for $Source with exit code $LASTEXITCODE"
    }
    $global:LASTEXITCODE = 0
}

function Write-ReleaseReadme {
    param(
        [string]$Path,
        [string]$Title,
        [string]$Mode
    )
    $template = @'
# __TITLE__

Mode: __MODE__

This bundle intentionally excludes `.env`, `.venv`, `node_modules`, `runs`, `artifacts`, `*.db`, `*.sqlite`, `.git`, and other local/runtime files.

## Run Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .[dev]
copy .env.example .env
$env:HARNESS_ROOT="..\harness"
$env:HARNESS_RUNS_ROOT="artifacts\harness_runs"
$env:ALLOW_REAL_LLM_CALLS="false"
python -m pytest -q
uvicorn app.main:app --reload
```

## Run Frontend

```powershell
cd backend\frontend
npm install
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:5173
```

Scripted mode is the default safe demo path. API mode requires explicit local secrets and double opt-in; do not put real API keys into this release folder.
'@
    $template.Replace("__TITLE__", $Title).Replace("__MODE__", $Mode) |
        Set-Content -LiteralPath (Join-Path $Path "README_RELEASE.md") -Encoding UTF8
}

Reset-Directory $RunnableRoot
Reset-Directory $CleanRoot

Copy-Project $RepoRoot (Join-Path $RunnableRoot "backend")
Copy-Project $RepoRoot (Join-Path $CleanRoot "backend")

if (-not [string]::IsNullOrWhiteSpace($HarnessRoot) -and (Test-Path -LiteralPath $HarnessRoot)) {
    Copy-Project $HarnessRoot (Join-Path $RunnableRoot "harness")
    Copy-Project $HarnessRoot (Join-Path $CleanRoot "harness")
} else {
    Write-Warning "HarnessRoot was not provided or does not exist; bundles contain backend only."
}

Write-ReleaseReadme $RunnableRoot "OpenAgent runnable bundle" "runnable"
Write-ReleaseReadme $CleanRoot "OpenAgent interview clean bundle" "interview-clean"

Write-Host "Created runnable bundle: $RunnableRoot"
Write-Host "Created interview clean bundle: $CleanRoot"
