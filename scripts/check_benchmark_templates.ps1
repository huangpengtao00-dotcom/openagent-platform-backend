param(
    [string]$ApiUrl = "http://127.0.0.1:8000",
    [string]$TemplatePath = "benchmark_templates\templates.json"
)

$ErrorActionPreference = "Stop"
$templates = Get-Content -Raw -Encoding UTF8 $TemplatePath | ConvertFrom-Json
$results = @()

foreach ($template in $templates) {
    $body = @{
        source_filename = $template.source_filename
        source_code = $template.source_code
        instruction = $template.goal
    } | ConvertTo-Json -Depth 8

    $draft = Invoke-RestMethod -Method Post -Uri "$ApiUrl/evaluation-drafts" -ContentType "application/json; charset=utf-8" -Body $body
    $results += [pscustomobject]@{
        id = $template.id
        expected = $template.difficulty
        actual = $draft.difficulty_level
        score = $draft.difficulty_score
        reasons = ($draft.difficulty_reasons -join " | ")
    }
}

$results | Format-Table -AutoSize
