# E:\syn 翻译书籍中英 md 准备清单与规划

> 2026-10-14 盘点 · 只读规划，未执行任何操作 · 依据《入库指南-书籍.md》
> 范围：E:\syn 翻译书籍（按用户要求不含 E:\syn\书籍\）

## 一、盘点总览（39 个书目录）

| 批次 | 数量 | 状态 |
|---|---|---|
| A 地质批次（经典书单落地） | ~10 本 | **新书已到，翻译进行中**（章节 md / 整本 md 两形态） |
| B SME/技术新书批次 | ~13 本 | 新增，MinerU 解析稿为主，翻译未开始或早期 |
| C 存量书更新 | ~16 本 | epub 修复版已就位（Blasting/MRE/HaulRoad 等有新增代） |
| D E:\syn\mineru_results（论文） | 1,713 md | **新批次论文解析成果已回传**，走论文管线另行入库，不在本清单 |

## 二·补、子目录成果分布（2026-10-14 补充盘点，用户指出成果在子目录）

各书成果不在顶层，分布形态归纳为六类（合并/转换工具需按此适配）：

| 成果形态 | 典型书 | 子目录 | 处理 |
|---|---|---|---|
| **中文译稿目录** | SME Surface（译稿:159）、SME Underground（translation:253）、Surface Mining Technology（work:212）、Sustainable Management（work:206）、Surface Mining Machines（work:36） | `译稿/` `work/` `translation/` | 章节译稿按序合并 → `_zh.md` |
| **MinerU 分章块** | Optimisation（zh:95+chunk_NN:1×多）、Paste Tailings、haul roads、big data（units:45） | `zh/` `chunk_51_60/`… | 分章块合并（序号识别）→ 质检 |
| **MinerU 解析专区** | SME mining reference（mineru_reparse:139+mineru_results:103）、SME Underground（mineru_results:184）、SME Surface（mineru_results:138） | `mineru_results/` `mineru_reparse/` | 英文分章解析稿合并 → en 四关质检 |
| **构建工作区** | SME mining reference（zh_build:130+epub_build:43）、SME Underground（epub_build:2）、Data Analytics（epub_build:2）、Hard Rock（handbook_build:2） | `*_build/` | epub 构建源——若 epub 已成品则 epub→md 更稳 |
| **翻译准备/混杂** | SME Mine Safety（translation_prep:66）、Water in Pit（zh:3）、Blasting（work:145+成果:49）、MRE（顶层:15+chunks:4） | 各异 | 逐本甄别：译稿 vs 原文解析 |
| **书内嵌套书目录** | 地质\An Introduction...（内含 mineu_results/）、SME_missing_chapter_openings | 嵌套 | 上卷已列，动工时展平处理 |

**规则补充（入指南 v1.1）**：md 准备扫描必须 rglob 全目录树；成果甄别顺序：
①整本 `_zh.md`/整本翻译 md → ②`译稿|work|translation` 章节稿合并 → ③`*_build` 的 epub 优先转 md
→ ④MinerU 分章合并（en 侧）→ ⑤顶层散 md 质检。命名归一时**原位保留全部源文件**，
生成的 `_zh.md`/`_en.md` 放书目录顶层。

## 三、分批明细与行动项

### A. 地质批次（对应 geology_classics.yaml 六层书单——书单已实现大半）

| 书 | 经典书单 | en md | zh 现状 | 行动项 |
|---|---|---|---|---|
| Isaaks & Srivastava《Applied Geostatistics》 | L4 ✓ | mineu_results 有 | **整本 zh md 已成**（isaaks_1990..._zh.md） | zh：整本 md 直接采用（信任翻译产出）；en：四关质检 |
| Sinclair & Blackwell《Applied Mineral Inventory Estimation》 | L5 ✓ | 待查 | 章节翻译 md（work/translated_full/ 01~03 章） | zh：**章节 md 合并成整本 _zh.md**（新需求）；翻完续并 |
| Journel & Huijbregts《Mining Geostatistics》 | L4 ✓ | 待查 | 待翻译 | en 质检备用；zh 等翻译 |
| Marjoribanks《矿产勘查及开发中的地质方法》 | L1 ✓ | — | **现成中文译本 epub+pdf**（万方译） | zh：epub→md 直接生成 |
| Houlding《3D Digital Geological Models》(geokniga) | L3 ✓ | 待查 | 待翻译 | 同上模式 |
| geokniga-mineralresourceandorereserveestimation | L5 ✓ | 待查 | 待翻译 | 同上 |
| Bassani《Geostatistics with Data of Different Support》 | 补充 | — | — | 双目录（地质\ 与 鍦拌川\ 各一份）需去重 |
| Li Li《Numerical Modeling in Civil & Mining Geotech》 | 补充 | — | — | 同上 |
| 章节首页补解析区（章节首页_补MinerU解析 / SME_missing_chapter_openings） | — | — | — | MinerU 补解析待跑 |

**问题项**：`鍦拌川\`（"地质"的 GBK 乱码名）与 `地质\` 内容部分重叠、部分互补——动工前需并目录去重（哪个为准待定，建议"地质"为准、乱码目录按文件级比对后并入）。

### B. SME/技术新书批次

| 书 | en md | zh | 行动项 |
|---|---|---|---|
| Application of Optimisation Techniques in Min...（157 md 分章） | 分章 MinerU | 无 | 分章 md 合并 + 四关质检 |
| SME Mine Safety & Health Handbook | 65 散 md | **1 zh_md 已开始** | 沿用用户流程，翻完合并 |
| Surface Mining Machines / Technology | 54/247 md | 各 1-2 zh_md 开始 | 同上 |
| Sustainable Management of Mining Operations | 246 md | 无 | en 质检备用 |
| SME Underground Mining Methods | 449 md | 无 | 同上 |
| SME mining reference handbook | 348 md + 64 zh_md | 部分成 | zh 合并 + en 质检 |
| SME Statistics for Mining Eng.（4 zh epub!） | 2 md | **epub 已出** | zh：epub→md |
| Introduction to Paste Tailings / Mining haul roads / SME Mineral Processing / Open pit mining / SME-Mineral-Processing | 少量 | 无 | PDF→MinerU 补解析 |
| epub_check_work（工作目录） | — | 2 zh epub | 归属甄别后并入对应书 |

### C. 存量书更新（16 本）

Blasting（新增导读/恢复代）、MRE、HaulRoad、Hard Rock、OPMD、各 Guidelines 系列、SME Surface（35 分章 zh epub + 36 en epub）、Principles and Practice（25 en epub 代）等——epub 修复版齐备，**统一按指南跑 epub→md（zh）+ 既有 en md 质检**。

## 四、准备工具清单（动工前实现，均只读源文件）

| # | 工具 | 用途 | 新增需求来源 |
|---|---|---|---|
| 1 | `epub_to_md.py` | 修复版 epub → 整本 `_zh.md`（spine 顺序+章内标题+目录页过滤） | 指南既定 |
| 2 | `md_quality_check.py` | 英文 MinerU md 四关质检（层级/骨架比/乱码/目录页） | 指南既定 |
| 3 | **`merge_chapter_md.py`** | 章节翻译 md（01_ch01.../vol1_ch01...）按序合并为整本 `_zh.md` | **本轮新发现**：地质批次与 SME 新书以章节 md 形态翻译 |
| 4 | **`merge_mineru_chapters.py`** | MinerU 分章解析 md 合并 + 章节序识别（Application of Optimisation 157 章等） | 同上 |
| 5 | 目录甄别器 | `地质` vs `鍦拌川` 文件级去重；epub_check_work 归属判定 | 本轮盘点 |
| 6 | `assign_book_codes.py` | 按主类自动编号（GEO-BOOK-0001 起），存量 67 本回溯编号 | §10.7 |

## 五、执行顺序（发令后）

1. **清障**：地质双目录并轨去重 → 乱码目录名归一
2. **中文 md**（指南铁律）：整本翻译 md 直接采 → 章节翻译 md 合并 → epub→md（其余）
3. **英文 md**：既有 MinerU md 四关质检（不过者 PDF 重解析）→ 分章 MinerU 合并
4. **命名归一**：全部落 `<书名>_zh.md` / `<书名>_en.md` 规范（原散 md 保留不删）
5. **验收**：每书 zh 章节数 vs epub 目录抽查、乱码扫描、路径体检
6. 转入 import_all_books 入库队列（编号/配对/分段/向量，另行发令）

## 六、两个待确认

1. 地质批次以哪个目录为准（建议 `地质\`，乱码目录并入）？
2. SME Statistics 的 4 个 zh epub 是否终版（mtime 10-07）？若是，直接 epub→md。
