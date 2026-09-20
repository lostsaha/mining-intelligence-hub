# 测试与维护指南

> 适用：矿业前沿情报聚合平台（FastAPI + PostgreSQL + Next.js）
> 读者：平台维护者（单人运维模式，一切以"低维护成本"为设计原则）
> 最后更新：2026-09-20

---

## 0. 一分钟健康检查

每天打开平台前，跑一遍这四条（或直接肉眼确认服务在跑）：

```bash
docker ps --format '{{.Names}} {{.Status}}'          # 期望: mining-db Up (healthy)
curl -s http://127.0.0.1:8100/api/stats | head -c 200 # 期望: 返回 JSON 统计
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3100/   # 期望: 200
```

**关键观察项**：`/api/stats` 里
- `items.pending` 应在采集后归零（长期不为 0 = 处理管线没跑完）
- `last_run.sources_failed` 偶尔几个属正常（RSS 失效/504），连续多日同一批失败 = 信源失效，去改 `sources.yaml`
- `items.rejected` 突然暴增 = LLM 判定或信源出问题，进入第 5 节排查

---

## 1. 服务启停

**启动顺序**（缺一不可）：Docker Desktop → 数据库 → 后端 → 前端

```bash
# 1. 启动 Docker Desktop（Windows 开始菜单），然后：
cd /e/syn/矿业聚合平台
docker compose up -d                      # PostgreSQL（首次自动建表）

# 2. 后端（端口 8100）
cd backend
.venv/Scripts/python -m uvicorn app.main:app --port 8100

# 3. 前端（端口 3100；注意 3000 被本机其他程序占用）
cd frontend
npx next dev -p 3100
```

**停止**：终端里 Ctrl+C；数据库 `docker compose down`（加 `-v` 会删数据，**永远别加**）。

> Windows 控制台中文乱码时，命令前加 `PYTHONUTF8=1`（只影响显示，不影响功能）。

---

## 2. 测试

### 2.1 API 测试（最常用）

浏览器打开 **http://127.0.0.1:8100/docs** —— FastAPI 自带交互文档，所有接口可点"Try it out"直接测试，无需写代码。

命令行等价（Git Bash）：

```bash
curl -s "http://127.0.0.1:8100/api/stats"                        # 总览
curl -s "http://127.0.0.1:8100/api/items?limit=2&days=7"         # 最近条目
curl -s "http://127.0.0.1:8100/api/radar?level=1"                # 大类雷达
curl -s "http://127.0.0.1:8100/api/works?q=kriging&limit=3"      # 文献检索
curl -s "http://127.0.0.1:8100/api/admissions" | head -c 300     # 名册对照
```

**看什么**：返回 JSON 而不是 `Internal Server Error`；`total` 数量级符合预期；中文字段正常显示。

### 2.2 采集管线测试

```bash
# 单源测试（改了 sources.yaml 后先用单源验证）
cd backend && PYTHONUTF8=1 .venv/Scripts/python -m app.collect.run --slug mining-com

# 处理管线测试（LLM 过滤 + 摘要）
PYTHONUTF8=1 .venv/Scripts/python -c "
from app.process import pipeline, digest
print(pipeline.run_process())   # 期望: processed>0, approved/rejected 有数
print(digest.generate())        # 期望: item_count>0
"
```

**验证入库**（数据库直查）：

```bash
docker exec mining-db psql -U mining -d mining -c "
SELECT s.name, COUNT(*) AS items, MAX(i.collected_at)::date AS last_day
FROM mining.items i JOIN mining.sources s USING (source_id)
GROUP BY s.name ORDER BY last_day DESC NULLS LAST LIMIT 10;"
```

### 2.3 LLM 管线测试

```bash
cd backend && PYTHONUTF8=1 .venv/Scripts/python -c "
from app.process import llm
print(llm.classify('Autonomous haulage trial begins at Pilbara iron ore mine',
                   'A miner started a fleet-level autonomous truck trial with real time dispatch integration.'))"
```

**期望**：`relevant: True`、`topics` 含 `surface-mining`/`automation` 之类、`summary_zh` 是通顺中文。
**若 401**：Key 失效，换 `.env` 里的 `LLM_API_KEY`（DeepSeek 后台重新生成，`sk-` 开头）。Key 无效不会导致系统崩溃——管线自动回退关键词启发式，但中文摘要会缺失。

### 2.4 数据质量抽查（每月做一次）

```bash
docker exec mining-db psql -U mining -d mining -c "
-- ① 拒绝原因分布（噪音治理是否正常）
SELECT reject_reason, COUNT(*) FROM mining.items
WHERE status='rejected' GROUP BY 1 ORDER BY 2 DESC;

-- ② 随机抽 5 条通过条目人工读（判断信噪比）
SELECT left(title,50), left(summary_zh,60) FROM mining.items
WHERE status='approved' ORDER BY random() LIMIT 5;

-- ③ 摘要覆盖率（LLM 是否全量生效）
SELECT COUNT(*) FILTER (WHERE summary_zh IS NOT NULL)::float / COUNT(*) AS 覆盖率
FROM mining.items WHERE status='approved';"
```

**人工读的价值**：读到"这明显是噪音却通过了"或"这明明相关却被拒了"，记下来——那就是调整关键词、评分权重或 LLM 提示词的输入（这就是权重校准的原材料）。

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

```bash
# 一键：采集 → LLM 过滤评分 → 周报（也可在前端首页点按钮）
cd backend && PYTHONUTF8=1 .venv/Scripts/python -c "
from app.collect.run import run_collect
from app.process import pipeline, digest
run_collect(); pipeline.run_process(); digest.generate()"
```

接入定时后（未来部署到服务器）改为 cron 每日一次，本地阶段手动即可。

### 每周（约 30 分钟）

1. **读本周周报**，随手记三条：有用 / 噪音 / 遗漏（产品进化的原材料）；
2. **查失效信源**：`SELECT slug, last_fetched_at FROM mining.sources WHERE active ORDER BY last_fetched_at NULLS FIRST LIMIT 10;` 连续 7 天没动静的源去修 URL 或标停用；
3. **备份数据库**（见第 6 节）。

### 每月（约 1 小时）

```bash
# ① 专家榜重算（语料月度增量后排名会变化）
cd backend && PYTHONUTF8=1 .venv/Scripts/python -m app.experts.run --build

# ② 雷达窗口数据补充（最新优先 + 对称对比窗口，各约 700 点配额）
PYTHONUTF8=1 .venv/Scripts/python -c "
from app.experts import collect_works
collect_works.collect(max_records_per_query=100, queries_per_topic=1,
                      sort='publication_date:desc', from_date='2025-01-01')"
# 对比窗口：from_date/to_date 各前移一个月
```

3. 名册扩充（编辑 `admissions.yaml` → `python -m app.experts.match_admissions`）；
4. 查看费用：OpenAlex（openalex.org 后台）与 DeepSeek（platform.deepseek.com 用量页）——预期每月DeepSeek 几元以内、OpenAlex 在免费额度内。

### 每季度

- 评分权重校准：抽 20 条人工排序 vs 算法排序，调 `config.py` 里 `WEIGHTS`；
- 依赖升级：**非必要不升级**（能跑不动它）；升级前先备份数据库。

---

## 4. 配置维护（三大 YAML + .env）

| 文件 | 改什么 | 改完执行 |
|---|---|---|
| `backend/data/sources.yaml` | 加信源/调权重/停用源（`active: false`） | `python -m app.seed` → 单源采集测试 |
| `backend/data/topics.yaml` | 加主题/子主题（含采集词族） | `python -m app.seed` → 按大类补采 → `--build` |
| `backend/data/admissions.yaml` | 加名册人员（含依据） | `python -m app.experts.match_admissions` |
| `backend/.env` | LLM/OpenAlex Key、端口、评分权重 | 重启后端生效（**永不提交到 GitHub**） |

**新增主题的完整流程**（以"矿井通风"为例）：
1. `topics.yaml` 对应大类下加 children（`query_keywords` 2~3 条英文检索词）；
2. `python -m app.seed`；
3. `python -m app.experts.run` 采集该类（或用 `collect(category_slug=...)` 补采单类）；
4. `/radar?parent=<大类>` 查看新子主题数据。

---

## 5. 故障排查（症状 → 原因 → 解法）

| 症状 | 原因 | 解法 |
|---|---|---|
| 后端起不来 `EADDRINUSE` | 端口被占 | 换端口 `--port 8101`（本机 8000/3000 已被占，用 8100/3100） |
| `docker compose up` 报 project name | 中文目录名 | 已在 compose 固定 `name: mining-hub`，勿删该行 |
| 采集大量 `403 Forbidden` | 站点反爬 | 属正常；源会标记失败并跳过，批量失效再处理 |
| OpenAlex 全部 `429` | 当日信用点耗尽（匿名按 IP 共享 1000 点/天） | 次日自动恢复；已配 API Key（10000 点/天），确认 `.env` 的 `OPENALEX_API_KEY` 在 |
| LLM 全部 `401` | DeepSeek Key 失效 | 后台重新生成（`sk-` 开头），更新 `.env` 重启后端 |
| 采集 `400 Bad Request` | OpenAlex 接口字段变更 | 看报错 URL 里的 select/filter，对照官方文档修 `client.py` |
| 摘要全是英文原文 | LLM 未启用或全挂 | 查 `/api/stats` 无异常则看后端日志 `[fail]`/401 |
| 前端 500 | 后端没起或接口报错 | 先 `curl /api/stats` 确认后端，再看前端终端日志 |
| 数据库连不上 | Docker 没起 | Docker Desktop → `docker compose up -d` |
| 中文乱码 | Windows 控制台编码 | 命令前加 `PYTHONUTF8=1` |

**万能三连**：重启后端 → `docker compose restart` → 还不行就看后端终端的最后 20 行报错。

---

## 6. 备份与恢复

**什么值得备份**：名册匹配关系、评分历史、条目的 LLM 摘要与判定——这些是时间的复利，重采不可再生。

```bash
# 备份（每周一次，文件名带日期）
docker exec mining-db pg_dump -U mining -d mining > backup_mining_$(date +%F).sql

# 恢复（新库先建表：docker compose up -d 后自动执行 001~003）
cat backup_mining_2026-09-20.sql | docker exec -i mining-db psql -U mining -d mining

# 检查备份可用性（别等真丢了才发现备份是空的）
grep -c "INSERT\|COPY" backup_mining_2026-09-20.sql
```

备份文件建议同时复制一份到网盘/移动硬盘。

---

## 7. 命令速查表

```bash
# ---- 服务 ----
docker compose up -d                                  # 数据库
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8100   # 后端
cd frontend && npx next dev -p 3100                   # 前端

# ---- 日常管线 ----
python -m app.collect.run                             # 采集全部信源
python -m app.collect.run --slug <slug>               # 采集单源
python -c "from app.process import pipeline,digest; pipeline.run_process(); digest.generate()"

# ---- 专家/名册 ----
python -m app.experts.run                             # 全量：采集+重建 Top100
python -m app.experts.run --build                     # 仅重建评分
python -m app.experts.match_admissions                # 名册匹配

# ---- 数据库 ----
docker exec mining-db psql -U mining -d mining        # 进 SQL 终端
docker exec mining-db pg_dump -U mining -d mining > backup.sql   # 备份

# ---- 同步 GitHub ----
git add -A && git commit -m "说明" && git push
```
