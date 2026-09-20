# 日常管线：采集 → LLM 过滤评分 → 周报
$env:PYTHONUTF8 = "1"
$backend = Join-Path $PSScriptRoot "..\backend"
Set-Location $backend
& .\.venv\Scripts\python.exe -m app.collect.run
& .\.venv\Scripts\python.exe -c "from app.process import pipeline, digest; pipeline.run_process(); digest.generate()"
Write-Host "`n完成。打开 http://127.0.0.1:3100 查看最新内容" -ForegroundColor Green
