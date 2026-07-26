$ErrorActionPreference = 'Stop'
$Python = if ($env:ANALOGCODER_PYTHON) {
    $env:ANALOGCODER_PYTHON
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$Root = Split-Path -Parent $PSScriptRoot

if (-not $env:DASHSCOPE_API_KEY) {
    throw 'DASHSCOPE_API_KEY is not set.'
}
if (-not $env:BAILIAN_BASE_URL) {
    $env:BAILIAN_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
}
$env:PYTHONUTF8 = '1'
$env:MPLBACKEND = 'Agg'

Push-Location $Root
try {
    & $Python evaluation\lm358_conditioner\run_agent.py `
        --model qwen3-coder-plus `
        --runs 1 `
        --max-repairs 3 `
        --api-max-retries 3
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
