# 一分钟健康检查：数据库 / 后端 / 前端
$ProgressPreference = "SilentlyContinue"
[System.Net.WebRequest]::DefaultWebProxy = $null   # 防止系统代理拦截 localhost
$fail = 0

Write-Host "== 1. 数据库容器 ==" -ForegroundColor Cyan
$docker = docker ps --format "{{.Names}} {{.Status}}" 2>$null | Select-String "mining-db"
if ($docker) { Write-Host "  OK  $docker" -ForegroundColor Green }
else { Write-Host "  FAIL  mining-db 未运行（先开 Docker Desktop，再 docker compose up -d）" -ForegroundColor Red; $fail = 1 }

Write-Host "== 2. 后端 API (8100) ==" -ForegroundColor Cyan
try {
    $stats = Invoke-RestMethod "http://127.0.0.1:8100/api/stats" -TimeoutSec 5
    Write-Host ("  OK  条目 {0}（通过 {1} / 待处理 {2}）· 活跃信源 {3}" -f `
        $stats.items.total, $stats.items.approved, $stats.items.pending, $stats.sources.active) -ForegroundColor Green
    if ($stats.items.pending -gt 50) { Write-Host "  提醒: pending 偏多，运行 scripts\daily.ps1" -ForegroundColor Yellow }
} catch { Write-Host "  FAIL  后端未启动" -ForegroundColor Red; $fail = 1 }

Write-Host "== 3. 前端 (3100) ==" -ForegroundColor Cyan
try {
    $r = Invoke-WebRequest "http://127.0.0.1:3100/" -TimeoutSec 8 -UseBasicParsing
    Write-Host "  OK  HTTP $($r.StatusCode)" -ForegroundColor Green
} catch { Write-Host "  FAIL  前端未启动" -ForegroundColor Red; $fail = 1 }

if ($fail) { exit 1 } else { Write-Host "`n全部正常 ✓" -ForegroundColor Green }
