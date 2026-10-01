# 一键启动整个平台：Docker → 数据库 → 后端 → 前端 → 打开浏览器
# 用法：双击本文件，或在 PowerShell 中 .\scripts\start-all.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$ProgressPreference = "SilentlyContinue"

Write-Host "== 1/4 检查数据库 ==" -ForegroundColor Cyan
$dbOk = docker ps --format "{{.Names}}" 2>$null | Select-String -SimpleMatch "mining-db"
if (-not $dbOk) {
    # Docker Desktop 未运行则先拉起（首次约 1 分钟）
    $daemon = docker info *> $null; if ($LASTEXITCODE -ne 0) {
        Write-Host "  启动 Docker Desktop，等待守护进程（最多 2 分钟）..." -ForegroundColor Yellow
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        $deadline = (Get-Date).AddSeconds(120)
        while ((Get-Date) -lt $deadline) {
            docker info *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 5
        }
    }
    docker compose -f (Join-Path $root "docker-compose.yml") up -d | Out-Null
    Write-Host "  等待 PostgreSQL 就绪..." -ForegroundColor Yellow
    Start-Sleep -Seconds 8
}
Write-Host "  OK mining-db" -ForegroundColor Green

Write-Host "== 2/4 启动后端（8100，新窗口）==" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --port 8100"

Write-Host "== 3/4 启动前端（3100，新窗口）==" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npx next dev -p 3100"

Write-Host "== 4/4 等待服务就绪并打开浏览器 ==" -ForegroundColor Cyan
Start-Sleep -Seconds 25
Start-Process "http://127.0.0.1:3100"
Write-Host "`n完成。两个服务窗口请保持开启；关闭=停止服务。" -ForegroundColor Green
