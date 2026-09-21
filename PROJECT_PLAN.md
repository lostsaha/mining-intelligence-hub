# 矿业前沿情报聚合平台（Mining Intelligence Hub）项目规划

> 版本：v1.0（2026-09-20）
> 前置输入：《寻找活跃矿业专家.pdf》——矿业专家—文献—技术知识图谱（MELTG）设计交互记录
> 参考对象：aihot（AI 热点聚合站）、Hacker News（技术社区信息流）

---

## 1. 项目背景与定位

### 1.1 缘起

此前的交互记录（《寻找活跃矿业专家.pdf》）完成了三件事：

1. **明确了信息需求**：露天采矿、边坡稳定、岩石力学、矿山水文、矿山规划、爆破、AI/数字矿山等方向的矿业前沿信息；
2. **设计了信息源四层体系**：专家个人 → 矿业公司 → 专业组织（AusIMM/SME/ARMA/ACG 等）→ 期刊/会议；
3. **完成了 MELTG 知识图谱的完整设计**：14 种节点、约 25 种关系、PostgreSQL 建表 SQL、OpenAlex 采集管线、MiningExpertScore 评分体系与 100 位专家自动发现算法。

本规划在此之上回答下一个问题：**如何把分散的矿业信息持续地聚合、过滤、组织起来，成为矿业工程师每天/每周真正会打开的入口？**

### 1.2 产品定位

**矿业垂直领域的前沿情报聚合平台**——不是通用新闻站，不是搜索引擎，而是：

- **入口**：一个页面看完全球矿业值得关注的动态；
- **过滤器**：把"mining"歧义噪音（加密货币挖矿等）与低质内容挡在门外；
- **组织者**：按矿业技术主题体系（而非媒体栏目）组织信息；
- **节奏适配器**：把低频、慢节奏的矿业信息流，整理成高信噪比的周报与主题档案。

一句话定位：**「矿业的 aihot」+「慢节奏的 Hacker News」+ 未来 MELTG 知识图谱的前端窗口。**

### 1.3 与远景（MELTG）的关系

```
第一阶（本项目·MVP）：信息聚合层 —— 信源采集 → AI 过滤打分 → 信息流/周报/主题频道
第二阶：专家层 —— 接入 PDF 中的 OpenAlex 管线与 MiningExpertScore，产出 Top 100 专家动态
第三阶：图谱层 —— MELTG 知识图谱可视化 + 前沿技术雷达
```

聚合平台不是知识图谱的对立面，而是它的**数据源与展示层**：平台每日积累的过滤后条目（专家帖子、公司动态、期刊论文、会议信息），正是未来图谱 Person/Work/Topic/Mine 节点的原料。

---

## 2. 行业特点分析与设计原则（核心差异化）

矿业信息生态与 AI/互联网行业截然不同，直接照搬 HN/aihot 会失败。逐条对比：

| 维度 | HN / aihot（AI行业） | 矿业行业 | 本平台设计应对 |
|---|---|---|---|
| 信息总量 | 每天数千条，信源 168+ | 每天全球有效动态仅数十条 | 精选 ~30 个高质量信源即可覆盖；宁缺毋滥 |
| 更新频率 | 热点以小时计，aihot 每 6 小时全量更新 | 以周/月计；期刊月刊、会议年度 | **每日采集一次**；主打**周报**而非实时热榜 |
| 内容半衰期 | 48 小时后基本无价值 | 指南、标准、技术报告常年有效 | 时间衰减慢（半衰期约 14 天）；设"常青资源"区 |
| 排序信号 | 社区投票、讨论热度 | 无社区，投票不可行 | **算法多因子评分**：相关性+权威度+新鲜度+深度 |
| 噪音特征 | 软文、重复报道 | "mining"歧义（加密货币/数据挖掘）、股讯噪音、营销通稿 | LLM 逐条相关性判定 + 主题分类；信源白名单制 |
| 用户决策 | "今天有什么新东西" | "这个方向最近有什么进展""哪篇文章值得精读" | 按主题频道浏览 + 周报深读，而非无限下滑 |

### 2.1 设计原则（六条）

1. **精选优于海量**：信源准入白名单，按四层体系人工核定权威权重；不做开放式爬虫。
2. **周报是主产品**：每周自动生成「矿业前沿周报」——按主题分组的 Top 精选 + 一句话点评；信息流只承担"补充浏览"角色。
3. **算法排序，不依赖社区**：`final_score = 矿业相关性×0.35 + 信源权威度×0.25 + 新鲜度×0.20 + 内容深度×0.20`（MVP 可配权重）。
4. **主题体系是骨架**：采用 PDF 记录中的 Mining Ontology 13 大类（露天采矿、地下采矿、岩土/边坡、矿山水文、钻爆、矿山规划、自动化、AI 与数字矿山、矿物加工、尾矿、矿山安全、矿山闭坑、关键矿产），所有条目归入主题频道。
5. **AI 过滤 + 证据留痕**：每条条目记录 LLM 判定的相关性分数与摘要（未来可扩展为 MELTG 的 Evidence 节点），可审计。
6. **低运维、可中断**：采集脚本幂等、可手动触发、失败不影响已有数据——适配单人 vibe-coding 维护模式。

---

## 3. 产品设计

### 3.1 页面结构（MVP）

```
首页 /            信息流：HN 式单列，按天分组；每条显示标题/信源/主题标签/AI 一句话摘要/评分
周报 /weekly      周报列表；详情页按主题分组展示当周 Top 15-25 条 + 编辑说明
主题 /topics/[slug]  13 大类频道页，每频道按评分排序的历史条目
信源 /sources     信源目录：四层体系（专家/公司/组织/期刊会议）+ 更新频率 + 权威度
```

### 3.2 内容条目（Item）形态

- 标题（原文）+ 中文一句话摘要（LLM 生成）
- 原文链接、信源、发布时间
- 主题标签（1~3 个）、矿业相关性分、综合评分
- 类型：新闻 / 论文 / 技术报告 / 会议 / 公司公告 / 专家观点（后续版本）

### 3.3 周报生成逻辑

每周一凌晨（或手动触发）聚合上周 approved 条目：每主题取 Top 5，全局取 Top 20，生成结构化周报并存库，支持导出 Markdown（后续可接 RSS/API 输出，复刻 aihot 的多渠道分发）。

### 3.4 明确不做（MVP 边界）

- 不做用户系统/投票/评论（矿业流量密度不支持，遵循设计原则 3）
- 不做 LinkedIn/X 爬虫（反爬与合规风险，专家动态留待 Phase 2 用 OpenAlex 学术数据切入）
- 不做全文抓取解析（MVP 用 RSS 摘要即可，降低复杂度）

---

## 4. 信源体系

### 4.1 八级信源金字塔（S0–S7，源自《全球矿业信源分析》）

| 层级 | 类型 | 作用 | 平台收录 |
|---|---|---|---|
| S0 | 政府/地调/监管/交易所（USGS、BGS、GSC） | 确认事实：资源/储量/产量/法规 | 目录·人工查阅 |
| A | 国际与标准组织（IEA/ICMM/CRIRSCO） | 全球统计、标准规范 | CRIRSCO 采集中 |
| A- | 公司公告与技术报告（SEC/ASX，NI 43-101/JORC） | 一手项目信息（证据链顶端） | 目录·人工检索 |
| B+ | 商业数据库（S&P Global/Fastmarkets/WoodMac/CRU） | 定位：矿山数据/成本/价格 | 目录·付费 |
| B | 专业矿业媒体（Mining.com/IM 等） | 新闻、项目动态、技术趋势 | **自动采集主力**（30 源） |
| B- | 学术文献（OpenAlex/期刊） | 技术原理与研究进展 | OpenAlex 管线 + 期刊源 |
| C | 专家个人渠道（LinkedIn/博客） | 专家观点与前沿信号 | 人工浏览（合规限制） |
| D | 普通媒体/论坛 | 仅发现线索 | 原则上不收录 |

**关键原则**：社交媒体适合"发现"，专业数据库适合"定位"，一手文件适合"验证"；
对同一矿山：公司新闻 < 交易所公告 < 监管文件 < 技术报告。

**Source × Question Matrix（节选）**：全球产量→USGS/BGS；某矿山储量→JORC/NI 43-101；
矿山技术→学术论文/SME；专家是谁→OpenAlex/ORCID；矿业新闻→Mining.com/IM；金属价格→Fastmarkets/S&P。

**Evidence Chain（证据链）**：条目 → 一手公告 → 技术报告 → 合格人签字的资源表——
平台的 evidence 表已为此预留（专家推荐证据已实现），Phase 3+ 将把"新闻声称"溯源到
"一手文件"（Question→Retrieve→Claim→Evidence→Source→Confidence→Answer）。

### 4.2 首批信源清单（48 源）

完整目录见 `/sources` 页面与 `backend/data/sources.yaml`。可自动采集 24 个（B 级媒体与
Google News 定向查询为主），人工查阅目录 25 个（S0/A-/B+ 付费数据库等）。
RSS 可用性随时间变化：失效源自动跳过并记录，需定期巡检（`quality-check.ps1` 第 4 项）。

---

## 5. 技术架构（MVP）

```
┌────────────────────────────────────────────────────┐
│  前端 Next.js (App Router, SSR)                      │
│  /  /weekly  /topics/[slug]  /sources               │
└───────────────▲────────────────────────────────────┘
                │ HTTP (localhost:3000 → 8000)
┌───────────────┴────────────────────────────────────┐
│  后端 FastAPI                                        │
│  /api/items /api/topics /api/weekly /api/sources    │
│  /api/stats /api/digest/run                         │
├────────────────────────────────────────────────────┤
│  处理管线（Python，手动/定时触发）                      │
│  ① collect：feedparser 抓 RSS → 归一化 → URL 去重入库 │
│  ② process：LLM 过滤/摘要/主题分类/评分（可回退启发式）│
│  ③ digest：周报聚合生成                              │
├────────────────────────────────────────────────────┤
│  PostgreSQL（mining schema）                         │
│  sources / items / topics / item_topic /            │
│  weekly_digests / digest_item / collect_runs        │
└────────────────────────────────────────────────────┘
```

### 5.1 技术选型与理由

| 组件 | 选择 | 理由 |
|---|---|---|
| 采集/处理 | Python 3.12+（feedparser、httpx、pydantic） | 与 PDF 记录的 OpenAlex 管线同一技术栈，Phase 2 可直接复用 |
| API | FastAPI + Uvicorn | 轻量、类型安全、自动文档 |
| 数据库 | PostgreSQL 16（Docker） | 遵循 PDF 的 mining schema 设计，JSONB 存原文，未来无缝扩图谱表 |
| LLM | OpenAI 兼容接口（环境变量配置 base_url/model/key） | 可接任意服务商；无 Key 时自动回退关键词启发式，保证开箱可跑 |
| 前端 | Next.js 15 (App Router) + 原生 CSS | SSR利于首屏；极简 HN 风格无需 UI 框架 |

### 5.2 评分模型（MVP）

```
relevance   矿业相关性（LLM 0~1，加密货币/无关内容 → 直接 rejected）
authority   信源权威度（sources.yaml 权重 1~10 → 0~1）
freshness   新鲜度（exp(-ln2 × 天龄/14)，14 天半衰期）
depth       内容深度（标题+摘要长度、论文/报告类型加权、原文词数代理）
final_score = 0.35×relevance + 0.25×authority + 0.20×freshness + 0.20×depth   （×100）
```

---

## 6. 数据模型（MVP，兼容 PDF mining schema 风格）

```sql
mining.sources        -- 信源：name, feed_url, layer(1-4), authority_weight, lang, active
mining.topics         -- 主题：slug, name_zh, name_en, parent_id, level（种子=13大类）
mining.items          -- 条目：source_id, title, url(唯一), author, published_at,
                      --       summary_raw, summary_zh, item_type, lang,
                      --       mining_relevance, authority, freshness, depth, final_score,
                      --       status(pending/approved/rejected), reject_reason, raw_data JSONB
mining.item_topic     -- 条目↔主题：relevance
mining.weekly_digests -- 周报：week_start, title, summary, generated_at
mining.digest_item    -- 周报↔条目：rank, topic_id
mining.collect_runs   -- 采集运行记录：started/finished, per-source 结果统计（可观测性）
```

后续阶段直接并入 PDF 记录中的 `persons / works / topics / institutions / social_accounts / evidence / expert_score_history` 等表（同名 schema `mining`，主题表 `topics` 两版完全兼容）。

---

## 7. 路线图

### Phase 1 — 聚合平台 MVP（本次交付，1~2 周）

- [x] 规划文档
- [x] PostgreSQL 建表 + 主题/信源种子
- [x] RSS 采集器（~30 信源，幂等去重）
- [x] LLM 过滤/摘要/分类/评分（含启发式回退）
- [x] FastAPI 接口
- [x] Next.js 四页面（信息流/周报/主题/信源）
- [ ] 部署到 VPS + 每日定时采集（cron）+ 周报 RSS 输出

### Phase 2 — 专家模块（承接 PDF 记录，2026-09-20 实现核心）

- [x] OpenAlex Client + cursor 分页 + abstract 重建（`app/openalex/client.py`）
  - 免费调用为**每 IP 共享每日信用点**（约 1000 点 ≈ 100 次调用），客户端带预算监控，
    耗尽自动优雅停止；`OPENALEX_EMAIL` 为礼貌标识，申请 API Key 填 `OPENALEX_API_KEY`
    可大幅提升配额
- [x] Mining Ontology V0.1：14 大类 + 53 子主题（`data/topics.yaml` children + query_keywords）
- [x] 作品采集管线：查询词族 → works → 子主题归类 → 作者/机构同步入库（`app/experts/collect_works.py`）
- [x] 专家评分：MiningExpertScore 六维（相关性 35/影响 20/活跃 15/深度 10/行业 10/合作 10，
  social 未采集，其权重并入主题深度）
- [x] Entity Resolution：OpenAlex author id 消歧 + ORCID 安全回填（防多实体共用 ORCID）
- [x] 双层选择：0.70 × Expert Score + 0.30 × Coverage Score（大类/机构/国家动态多样性约束）
- [x] 证据留痕：selection 与 key_works 证据（evidence 表），"为什么被选中"可解释
- [x] API：/api/experts /api/experts/meta /api/experts/{id}
- [x] 前端：专家榜单（分类筛选 + 搜索）+ 专家卡片（评分条/研究方向/代表作品/合作者/证据）
- [ ] 社交媒体补全（LinkedIn/X，Phase 3 与合规评估一起做）
- [ ] 每月定时重算 + 评分趋势图表

运行方式：`cd backend && python -m app.experts.run`（完整）/ `--build`（仅重建评分）。

### Phase 3 — 知识图谱与前沿雷达（核心已实现，2026-09-20）

- [x] 前沿技术雷达：热度 = 0.45×论文增速（近12月 vs 对称前12月窗口）+ 0.30×近期产量
  + 0.25×专家聚集；大类/子主题两级视图 + 年度趋势条 + 动向标签（新兴/升温/平稳/降温）
  - 语料分三轮采集保证窗口对称：相关度排序（2019+）+ 最新优先（2025.9+）+
    对比窗口（2024.9–2025.9）
- [x] 知识图谱可视化：/graph 页（Cytoscape.js cose 力导布局），大类→子主题→专家→
  合作者网络，节点大小=论文量/评分，点击专家跳转专家卡片（MELTG 图查询走 PostgreSQL）
- [x] 文献检索：/works 页（标题/摘要检索、主题筛选、被引/年份排序、作者跳转专家卡片）
- [x] API：/api/radar /api/graph /api/works
- [ ] Neo4j/Memgraph 迁移（当前规模 PostgreSQL 足够，遵循 PDF 记录 V0.3 建议）
- [ ] 周报 LLM 深度导读（等待配置 LLM_API_KEY）
- [ ] 语义搜索（pgvector，PDF V0.2 方案）

### 长期

- 语义搜索（pgvector，PDF V0.2 方案）
- 多渠道分发：RSS / API / Agent Skill（aihot 模式）
- 矿山/项目节点（Mine Graph），会议日历，经典资源库（书籍/指南/标准）

### 固定名册 × 算法榜对照（2026-09-20 实现，用户提出）

- **定位**：名册是权威对比基准——院士/泰斗直通、院校教授、企业骨干、标准指南编写者
  四层准入（T1~T4），每条入选附公开依据；对应 PDF persons 设计中预留的 is_seed/is_verified
- **首版 96 人**（admissions.yaml，可随时扩充）：T1 院士 52 / T2 教授 35 / T3 企业 7 / T4 指南 2
- **挂接**：OpenAlex authors 检索 + 严格姓名评分（姓+名全对上；名姓颠倒需机构佐证；
  宁漏配不错配）→ 88 挂接 + 8 独立记录（OpenAlex 无档案者）
- **三类信号**：双重入选（高置信）/ 仅名册=算法盲区（语言/学术/时间三偏差的兜底）/
  仅算法=新发现待审；/admissions 页对照展示，专家卡片带认证徽章
- 运行：编辑 backend/data/admissions.yaml → `python -m app.experts.match_admissions`

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 信源 RSS 失效/改版 | 采集中断 | collect_runs 记录逐源结果；采集器静默跳过；信源清单可维护 |
| LLM API 费用/不可用 | 过滤停摆 | 启发式回退过滤；批处理逐条容错；只对增量条目调用 |
| "mining" 歧义噪音入库 | 信噪比下降 | LLM 相关性硬门槛 + reject_reason 留痕 + 信源白名单 |
| 单人维护精力有限 | 项目搁置 | 极简架构、幂等脚本、手动触发即可运行；周报自动生成降低运营成本 |
| 矿业条目量太少显得空 | 产品观感 | 信息流按天分组容忍稀疏；周报按周聚合放大密度；主题页显示历史沉淀 |

---

## 9. 验收标准（MVP）

1. 采集管线对真实信源抓取成功（≥3 个源、≥30 条增量条目）；
2. 过滤与评分生效：加密货币类条目被拒绝且留有原因；条目带主题标签与中文摘要（LLM 或启发式）；
3. 四个页面真实渲染数据库内容，信息流按天分组、周报可生成；
4. PROJECT_PLAN.md 与实际实现一致。
