# 数据库备份（建议每周一次；备份目录自动创建）
$env:PYTHONUTF8 = "1"
$date = Get-Date -Format "yyyy-MM-dd"
$dir = Join-Path $PSScriptRoot "..\backups"
$out = Join-Path $dir "backup_mining_$date.sql"
New-Item -ItemType Directory -Force $dir | Out-Null

docker exec mining-db pg_dump -U mining -d mining | Out-File -FilePath $out -Encoding utf8

$rows = (Select-String -Path $out -Pattern "COPY |INSERT " | Measure-Object).Count
if ($rows -gt 0) {
    Write-Host "备份完成: $out（$rows 行数据语句）" -ForegroundColor Green
    Write-Host "建议复制一份到网盘/移动硬盘" -ForegroundColor Yellow
} else {
    Write-Host "警告: 备份文件为空，请检查容器是否运行！" -ForegroundColor Red
}
