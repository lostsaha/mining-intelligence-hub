# 测试与维护指南

> 适用：矿业前沿情报聚合平台（FastAPI + PostgreSQL + Next.js）
> 环境：Windows 10/11 + PowerShell + Docker Desktop
> 读者：平台维护者（单人运维模式，一切以"低维护成本"为设计原则）
> 最后更新：2026-09-20

> **首次使用脚本前，开一次 PowerShell 执行**（允许运行本地脚本，只需一次）：
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## 0. 一分钟健康检查

PowerShell 中运行（在项目根目录）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke.ps1
```

输出示例：

```
== 1. 数据库容器 ==
  OK  mining-db Up 2 hours (healthy)
== 2. 后端 API (8100) ==
  OK  条目 816（通过 711 / 待处理 0）· 活跃信源 23
== 3. 前端 (3100) ==
  OK  HTTP 200
全部正常 ✓
```

**关键观察项**（脚本第 2 步顺带显示）：
- `待处理 (pending)` 应在采集后归零（长期不为 0 = 处理管线没跑完，跑 `scripts\daily.ps1`）
- OpenAlex/采集失败偶发属正常，连续多日同一批失败 = 信源失效（见第 4 节）

---

## 1. 服务启停

**启动顺序**：Docker Desktop → 数据库 → 后端 → 前端（缺一不可）

```powershell
# 1. 数据库（在项目根目录 E:\syn\矿业聚合平台）
docker compose up -d

# 2. 后端（开一个 PowerShell 窗口，保持不关）
cd E:\syn\矿业聚合平台\backend
.\.venv\Scripts\python -m uvicorn app.main:app --port 8100

# 3. 前端（再开一个窗口）
cd E:\syn\矿业聚合平台\frontend
npx next dev -p 3100
```

**停止**：各窗口 Ctrl+C；数据库 `docker compose down`（加 `-v` 会删数据，**永远别加**）。

> 提示：本机 3000/8000 端口被其他程序占用，所以本项目固定用 **3100（前端）/ 8100（后端）**。

---

## 2. 测试

### 2.1 API 测试（最常用）

浏览器打开 **http://127.0.0.1:8100/docs** —— FastAPI 自带交互文档，每个接口点 "Try it out" 直接测试，无需写代码。

PowerShell 等价：

```powershell
irm http://127.0.0.1:8100/api/stats                  # 总览
irm "http://127.0.0.1:8100/api/items?limit=2&days=7" # 最近条目
irm http://127.0.0.1:8100/api/radar?level=1          # 大类雷达
irm "http://127.0.0.1:8100/api/works?q=kriging&limit=3"  # 文献检索
```

（`irm` 是 `Invoke-RestMethod` 的缩写，返回的 JSON 直接以对象形式打印。）

### 2.2 采集管线测试

```powershell
cd E:\syn\矿业聚合平台\backend

# 单源测试（改了 sources.yaml 后先用单源验证）
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -m app.collect.run --slug mining-com

# 处理管线测试（LLM 过滤 + 摘要 + 周报）
.\.venv\Scripts\python -c "from app.process import pipeline, digest; pipeline.run_process(); digest.generate()"
```

**验证入库**：

```powershell
docker exec mining-db psql -U mining -d mining -c "SELECT s.name, COUNT(*) AS items, MAX(i.collected_at)::date AS last_day FROM mining.items i JOIN mining.sources s USING (source_id) GROUP BY s.name ORDER BY last_day DESC LIMIT 10;"
```

### 2.3 LLM 管线测试

```powershell
cd E:\syn\矿业聚合平台\backend
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -c "from app.process import llm; print(llm.classify('Autonomous haulage trial begins at Pilbara iron ore mine', 'A miner started a fleet-level autonomous truck trial with real-time dispatch integration.'))"
```

**期望**：`relevant: True`、`topics` 含 `surface-mining`/`automation`、`summary_zh` 是通顺中文。
**若 401**：Key 失效，去 DeepSeek 后台重新生成（`sk-` 开头），更新 `.env` 的 `LLM_API_KEY` 后重启后端。Key 无效系统不会崩——管线自动回退关键词启发式，但中文摘要会缺失。

### 2.4 数据质量抽查（每月做一次）

一条命令跑完四个检查（拒绝原因分布 / 随机抽读 5 条 / 摘要覆盖率 / 信源健康）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\quality-check.ps1
```

**人工读的价值**：第 2 项随机抽 5 条，读到"这明显是噪音却通过了"或"这明明相关却被拒了"，记下来——那就是调整关键词、评分权重或 LLM 提示词的输入（权重校准的原材料）。

### 2.5 前端验收清单

| 页面 | 地址 | 看点 |
|---|---|---|
| 信息流 | `/` | 条目带中文摘要、按天分组、主题 chips 有计数 |
| 周报 | `/weekly` | 本周报告在、点开有主题分组 |
| 专家 | `/experts` | Top 100、院士徽章、认证筛选生效 |
| 名册 | `/admissions` | 四格统计、双重入选/盲区卡片 |
| 雷达 | `/radar` | 热度排序、年度趋势条 |
| 图谱 | `/graph` | 节点渲染、点专家出弹窗 |
| 文献 | `/works?q=blast` | 有结果、作者可点 |

---

## 3. 维护节奏

### 每日（约 5 分钟）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\daily.ps1
```

（= 采集 → LLM 过滤评分 → 周报；也可以在前端首页直接点「▶ 运行采集管线」按钮。）

### 每周（约 30 分钟）

1. **读本周周报**，随手记三条：有用 / 噪音 / 遗漏（产品进化的原材料）；
2. **查失效信源**：跑 `scripts\quality-check.ps1` 的第 4 项，连续 7 天没动静的源去修 URL 或在 `sources.yaml` 标 `active: false`；
3. **备份数据库**：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
```

（自动存到 `backups\backup_mining_日期.sql` 并自检非空；记得定期复制一份到网盘/移动硬盘。）

### 每月（约 1 小时）

```powershell
# ① 专家榜重算（语料月度增量后排名会变化）
powershell -ExecutionPolicy Bypass -File scripts\experts-build.ps1

# ② 雷达窗口数据补充（最新优先采集，约 700 点 OpenAlex 配额）
cd E:\syn\矿业聚合平台\backend
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -c "from app.experts import collect_works; collect_works.collect(max_records_per_query=100, queries_per_topic=1, sort='publication_date:desc', from_date='2025-01-01')"
```

3. 名册扩充：编辑 `admissions.yaml` → `.\.venv\Scripts\python -m app.experts.match_admissions`；
4. 查看费用：DeepSeek（platform.deepseek.com 用量页，预期每月几元以内）、OpenAlex（免费额度内）。

### 每季度

- **评分权重校准**：抽 20 条条目按"对矿业工程师的价值"人工排序，与算法排序对比，调 `backend\app\config.py` 里的 `WEIGHTS`；
- 依赖升级：**非必要不升级**；升级前先跑 `scripts\backup.ps1`。

---

## 4. 配置维护（三大 YAML + .env）

| 文件 | 改什么 | 改完执行 |
|---|---|---|
| `backend\data\sources.yaml` | 加信源/调权重/停用源（`active: false`） | `python -m app.seed` → 单源采集测试 |
| `backend\data\topics.yaml` | 加主题/子主题（含英文采集词族） | `python -m app.seed` → 按大类补采 → `experts-build.ps1` |
| `backend\data\admissions.yaml` | 加名册人员（含依据） | `python -m app.experts.match_admissions` |
| `backend\.env` | LLM/OpenAlex Key、数据库连接 | 重启后端生效（**永不提交到 GitHub**） |

**新增主题完整流程**（以"矿井通风"为例）：
1. `topics.yaml` 对应大类下加 children（`query_keywords` 写 2~3 条英文检索词）；
2. `.\.venv\Scripts\python -m app.seed`；
3. 采集该类语料（可仿照第 3 节每月第 ② 步，指定 `category_slug='mine-ventilation'`）；
4. `experts-build.ps1` 重算 → `/radar` 查看新子主题数据。

---

## 5. 故障排查（症状 → 原因 → 解法）

| 症状 | 原因 | 解法 |
|---|---|---|
| 后端起不来 `EADDRINUSE` | 端口被占 | 先跑 `scripts\smoke.ps1`：若全部 OK，说明服务已在别的窗口运行，**直接用即可**；要换到自己窗口，先关旧窗口或 `taskkill`。本机 8000/3000 被其他程序占用，固定用 8100/3100 |
| 停了服务端口仍被占 | `npx next dev` 会残留 node 子进程 | `netstat -ano | findstr :3100` 找 PID → `taskkill /PID <pid> /F` |
| `docker compose up` 报 project name | 中文目录名 | 已在 compose 固定 `name: mining-hub`，勿删该行 |
| 采集大量 `403 Forbidden` | 站点反爬 | 属正常；源标记失败并跳过，批量失效再处理 |
| OpenAlex 全部 `429` | 当日信用点耗尽（匿名按 IP 1000 点/天） | 已配 API Key（10000 点/天）；若仍 429 检查 `.env` 的 `OPENALEX_API_KEY` |
| LLM 全部 `401` | DeepSeek Key 失效 | 后台重新生成（`sk-` 开头），更新 `.env` 重启后端 |
| 采集 `400 Bad Request` | OpenAlex 接口字段变更 | 看报错 URL 里的 select/filter，对照官方文档修 `client.py` |
| 摘要全是英文原文 | LLM 未启用或全挂 | `smoke.ps1` 看后端状态，再看后端窗口最后 20 行 |
| 前端 500 | 后端没起或接口报错 | 先 `irm http://127.0.0.1:8100/api/stats` 确认后端 |
| 数据库连不上 | Docker 没起 | Docker Desktop → `docker compose up -d` |
| 脚本报"禁止运行脚本" | PowerShell 执行策略 | 管理员/本用户执行一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 控制台中文乱码 | Windows 控制台编码 | 命令前 `$env:PYTHONUTF8="1"`；SQL 输出乱码已由 `quality-check.ps1` 内置修复 |

**万能三连**：重启后端 → `docker compose restart` → 还不行就看后端窗口的最后 20 行报错。

---

## 6. 备份与恢复

**什么值得备份**：名册匹配关系、评分历史、条目的 LLM 摘要与判定——这些是时间的复利，重采不可再生。

```powershell
# 备份（每周一次）
powershell -ExecutionPolicy Bypass -File scripts\backup.ps1

# 恢复（新库：docker compose up -d 会自动建表）
Get-Content backups\backup_mining_2026-09-20.sql -Encoding UTF8 | docker exec -i mining-db psql -U mining -d mining
```

`scripts\backup.ps1` 会自动检查备份文件非空。备份目录建议同步一份到网盘/移动硬盘。

---

## 7. 命令速查表

```powershell
# ---- 服务 ----
docker compose up -d                                        # 数据库
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --port 8100   # 后端
cd frontend; npx next dev -p 3100                           # 前端

# ---- 脚本（推荐） ----
scripts\smoke.ps1            # 健康检查
scripts\daily.ps1            # 每日：采集→过滤→周报
scripts\quality-check.ps1    # 每月：数据质量抽查
scripts\experts-build.ps1    # 每月：专家榜重算
scripts\backup.ps1           # 每周：数据库备份

# ---- 专家/名册 ----
cd backend
.\.venv\Scripts\python -m app.experts.run                    # 全量：采集+重建
.\.venv\Scripts\python -m app.experts.run --build            # 仅重建评分
.\.venv\Scripts\python -m app.experts.match_admissions       # 名册匹配

# ---- 同步 GitHub ----
git add -A; git commit -m "说明"; git push
```
