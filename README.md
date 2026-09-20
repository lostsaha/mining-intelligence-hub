# 矿业前沿情报站（Mining Intelligence Hub）

矿业垂直领域的前沿信息聚合平台。参考 aihot（精选信源 + AI 预筛）与 Hacker News
（信息流 + 排名）的模式，并针对**矿业信息少、更新慢**的行业特点重新设计节奏：
每日采集一次、按周聚合精选、慢衰减排序。完整规划见 [PROJECT_PLAN.md](PROJECT_PLAN.md)，
日常运行、测试与故障排查见 [MAINTENANCE.md](MAINTENANCE.md)。

## 架构

```
frontend/  Next.js 15 (http://localhost:3100)   信息流 / 每周精选 / 主题 / 信源
backend/   FastAPI    (http://localhost:8100)   API + 采集/过滤/周报管线
db         PostgreSQL 16 (Docker, :5432)        mining schema
```

## 快速开始

```bash
# 0. 启动 Docker Desktop（Windows）

# 1. 数据库（首次启动自动执行 backend/sql/001_init.sql）
docker compose up -d

# 2. 后端
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt       # Linux/Mac: .venv/bin/pip
copy .env.example .env                              # 按需修改
.venv/Scripts/python -m app.seed                    # 导入主题+信源
.venv/Scripts/python -m uvicorn app.main:app --port 8100

# 3. 采集 + 过滤评分 + 生成周报（或直接在前端首页点「运行采集管线」）
cd backend
.venv/Scripts/python -m app.collect.run             # 抓 RSS（约 2 分钟）
.venv/Scripts/python -c "from app.process import pipeline, digest; pipeline.run_process(); digest.generate()"

# 3b. 专家发现（Phase 2，OpenAlex 学术语料 → 全球矿业专家 Top 100）
.venv/Scripts/python -m app.experts.run             # 完整：作品采集 + 专家构建
.venv/Scripts/python -m app.experts.run --build     # 仅用已有语料重建评分

# 4. 前端
cd frontend
npm install
npm run dev            # 开发模式；如 3000 端口被占用: npx next dev -p 3100
```

打开 <http://localhost:3100>。

## 接入 LLM（可选但推荐）

在 `backend/.env` 中配置任意 OpenAI 兼容服务：

```
LLM_BASE_URL=https://api.openai.com/v1     # 或其他服务商地址
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

配置后管线会用 LLM 做相关性判定、主题分类和**中文摘要**；不配置则回退为
关键词启发式过滤（仍可运行，但无中文摘要）。

## OpenAlex 配额说明（专家模块）

免费调用按 **IP 共享每日信用点** 计费（约 1000 点/天 ≈ 100 次调用），用尽后当日停止
（客户端会自动优雅收尾，次日自动恢复）。在 `backend/.env` 填写 `OPENALEX_EMAIL=你的邮箱`
作为官方推荐的礼貌标识；如向 OpenAlex 申请 API Key 并填入 `OPENALEX_API_KEY`，配额可大幅提升。

## 日常使用

```bash
docker compose up -d                                # 起数据库
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8100
cd frontend && npm run dev
```

然后在前端首页点「▶ 运行采集管线」，或用命令行依次执行
`collect.run` → `pipeline.run_process` → `digest.generate`。
定时运行可配 Windows 任务计划 / cron 每日一次。

## 信源维护

编辑 `backend/data/sources.yaml`（四层体系：专家/公司/组织/期刊媒体），
改完执行 `python -m app.seed` 同步。RSS 失效的源会被记录并跳过，不影响其他源。

## 目录结构

```
PROJECT_PLAN.md          项目规划（定位/设计原则/路线图/风险）
docker-compose.yml       PostgreSQL
backend/
  sql/001_init.sql       建表（schema 兼容 PDF 记录中的 MELTG 图谱设计）
  data/topics.yaml       矿业主题体系（13 大类 + 行业市场）
  data/sources.yaml      信源白名单（30+ 源，含失效标记）
  app/
    collect/run.py       RSS 采集器（python -m app.collect.run）
    process/pipeline.py  LLM/启发式过滤 + 多因子评分
    process/digest.py    周报生成（主题多样性优先）
    main.py              FastAPI 接口
frontend/app/            Next.js 页面（信息流/周报/专家/雷达/图谱/文献/信源）
```

## Phase 2/3 速览

- **专家发现**：`python -m app.experts.run --build` 重建 Top 100；全量采集 `python -m app.experts.run`
- **前沿雷达** `/radar`：主题热度 = 论文增速 45% + 近期产量 30% + 专家聚集 25%
  （语料分三轮采集：相关度排序 + 最新优先 + 对称对比窗口）
- **知识图谱** `/graph`：大类 → 子主题 → 专家 → 合作者网络（Cytoscape.js）
- **文献检索** `/works`：语料内 1.6 万+ 篇论文，标题/摘要搜索，作者可跳专家卡片
