# 数据质量抽查：拒绝原因分布 / 随机抽读 / 摘要覆盖率 / 信源健康
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PGCLIENTENCODING = "UTF8"
chcp 65001 > $null
$psql = { param($sql) docker exec mining-db psql -U mining -d mining -c $sql }

Write-Host "== 1. 拒绝原因分布 ==" -ForegroundColor Cyan
& $psql "SELECT reject_reason AS 原因, COUNT(*) AS 条数 FROM mining.items WHERE status='rejected' GROUP BY 1 ORDER BY 2 DESC;"

Write-Host "== 2. 随机抽读 5 条通过条目（人工判断信噪比） ==" -ForegroundColor Cyan
& $psql "SELECT left(title,44) AS 标题, left(summary_zh,50) AS 摘要 FROM mining.items WHERE status='approved' ORDER BY random() LIMIT 5;"

Write-Host "== 3. 中文摘要覆盖率 ==" -ForegroundColor Cyan
& $psql "SELECT round(COUNT(*) FILTER (WHERE summary_zh IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS 覆盖率百分比 FROM mining.items WHERE status='approved';"

Write-Host "== 4. 信源健康（最近最久未更新的 10 个活跃源） ==" -ForegroundColor Cyan
& $psql "SELECT slug AS 信源, last_fetched_at::date AS 最近采集 FROM mining.sources WHERE active ORDER BY last_fetched_at NULLS FIRST LIMIT 10;"

Write-Host "== 5. 名册匹配审计（国别不一致=需人工核实；零语料=待补采） ==" -ForegroundColor Cyan
& $psql "SELECT COALESCE(ea.name_zh, ea.full_name) AS 名册人员, ea.tier, ea.country_code AS 名册国, p.country_code AS 档案国, COALESCE(p.corpus_works,0) AS 语料 FROM mining.expert_admissions ea LEFT JOIN mining.persons p ON p.person_id = ea.person_id WHERE ea.match_status='matched' AND ea.country_code IS NOT NULL AND p.country_code IS NOT NULL AND ea.country_code <> p.country_code ORDER BY ea.tier;"
& $psql "SELECT COALESCE(ea.name_zh, ea.full_name) AS 名册人员, ea.tier, ea.match_status AS 状态, left(ea.review_note,30) AS 备注 FROM mining.expert_admissions ea WHERE ea.match_status='created' ORDER BY ea.tier;"
