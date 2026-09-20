# 每月专家榜重算（用最新语料重新评分排名 Top 100）
$env:PYTHONUTF8 = "1"
Set-Location (Join-Path $PSScriptRoot "..\backend")
& .\.venv\Scripts\python.exe -m app.experts.run --build
Write-Host "`n完成。打开 http://127.0.0.1:3100/experts 查看新榜单" -ForegroundColor Green
