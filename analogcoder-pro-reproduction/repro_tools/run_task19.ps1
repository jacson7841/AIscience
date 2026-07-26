$ErrorActionPreference = 'Stop'
$Python = if ($env:ANALOGCODER_PYTHON) {
    $env:ANALOGCODER_PYTHON
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$Root = Split-Path -Parent $PSScriptRoot

if (-not $env:DASHSCOPE_API_KEY) {
    throw 'DASHSCOPE_API_KEY is not set. Set it in this PowerShell session before running Task 19.'
}
if (-not $env:BAILIAN_BASE_URL) {
    $env:BAILIAN_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
}
$env:PYTHONUTF8 = '1'
$env:MPLBACKEND = 'Agg'

Push-Location $Root
try {
    $ModelDir = Join-Path $Root 'qwen3-coder-plus_retry_4\p19'
    $CompletedRuns = 0
    while ($CompletedRuns -lt 3) {
        $Record = Join-Path $ModelDir "$CompletedRuns\run_record.json"
        if (-not (Test-Path -LiteralPath $Record)) { break }
        $CompletedRuns++
    }
    if ($CompletedRuns -ge 3) {
        Write-Host 'Task 19 already has three completed independent runs.'
        exit 0
    }
    $IncompleteRun = Join-Path $ModelDir "$CompletedRuns"
    if (Test-Path -LiteralPath $IncompleteRun) {
        $Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $Archive = Join-Path $ModelDir "${CompletedRuns}_interrupted_$Stamp"
        Move-Item -LiteralPath $IncompleteRun -Destination $Archive
        Get-ChildItem -LiteralPath $ModelDir -File -Filter "p19_${CompletedRuns}_*.txt" |
            Move-Item -Destination $Archive
        [pscustomobject]@{
            status = 'interrupted'
            iteration = $CompletedRuns
            archived_at = (Get-Date).ToString('o')
            reason = 'No run_record.json was produced; prior process ended before task completion.'
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Archive 'interruption.json') -Encoding utf8
        Write-Host "Archived incomplete run at $Archive"
    }
    Write-Host "Resuming Task 19 at independent run $CompletedRuns of 3."
    & $Python run.py `
        --task_id 19 `
        --num_per_task 3 `
        --num_of_done $CompletedRuns `
        --num_of_retry 4 `
        --model qwen3-coder-plus `
        --vlm-model qwen3.7-plus `
        --api-max-retries 3 `
        --api-retry-delay 5 `
        --vlm-timeout 180
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
