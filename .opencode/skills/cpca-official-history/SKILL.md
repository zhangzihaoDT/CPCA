---
name: CPCA Official History
description: 从 CPCA 官网抓取“车市扫描”周度文章，提取“本周车市概述”，归档原始 HTML 与来源信息，并在不覆盖冲突数据的前提下回填 data/*.json 正式数据集。
---

# CPCA Official History

把 CPCA 官网的历史周度文章，转换为可追溯的官方来源归档，并回填正式标准数据集。

## 目标

- 官方来源归档：`input/official/`
- 正式标准数据：`data/*.json`
- 现有标准表与简报生成逻辑保持不变

官方抓取结果 **不写入** `input/weekly.md`。`weekly.md` 只作为手工种子/兜底来源；官网数据是正式来源。

## 路径约定

本文中的 `input/`、`data/`、`scripts/` 均相对项目根目录，命令在项目根目录执行。

## 目录结构

```text
input/official/
├── raw/<article_id>.html          # 原始 HTML 缓存
├── blocks/<period_end>.md         # 归一化后的“本周车市概述”
├── blocks_failed/<article_id>.md  # 提取/解析失败的样本
├── manifest.json                  # 来源、时间、hash、状态、统计
└── conflicts.json                 # 官方与正式数据的差异报告
```

## 标准工作流

1. 列出目标文章，先 dry-run：

   ```bash
   python3 scripts/fetch_cpca_history.py --start 2026-01-01 --dry-run
   ```

2. 抓取并提取：

   ```bash
   python3 scripts/fetch_cpca_history.py --start 2024-01-14 --end 2025-12-31
   ```

   只有从零全量重建时才用 `--clean`；按日期段增量回填不要加 `--clean`，否则会清空已有 blocks/manifest。

3. 对比正式数据，先报告不写入：

   ```bash
   python3 scripts/ingest_official.py
   ```

4. 确认无意外冲突后写入：

   ```bash
   python3 scripts/ingest_official.py --write
   ```

5. 校验并重建标准表和简报：

   ```bash
   python3 scripts/validate_data.py
   python3 scripts/build_standard_dataset.py
   python3 scripts/render_report.py
   ```

## 兼容范围

- **2024-01-17 起**：文章包含结构化“本周车市概述”，可进入当前 schema。
- **2024-01-07 及以前（2020–2023）**：旧格式，没有完整的乘用车/新能源/渗透率摘要，不进入当前标准表；需要 legacy 解析或只保留原始 HTML。
- 2025-01 至 2025-12 已验证可正常解析。

## 数据类型

- `kind=month`：月度收盘，进入 JSON 审计层，不进入周快照表。
- `kind=month_to_date`：官方周度快照，进入 `standard_dataset.csv`。
- “周”指 CPCA 官方发布统计区间，不保证 7 天；首周可能是 5–15 天的月内累计。
- 月末文章（如 4/27-30）的概述通常是 4/1-30 月度累计，不能当作单周增量。
- 不按自然周补齐，不构造官网未发布的 7 天周序列。

## 年份与 period

- 年份取文章标题/发布时间，不用 `date.today()`。
- period.start/end 取“本周车市概述”中的统计区间。
- 文章标题的周区间（如 `20260427-0430`）只作为来源元数据，不能替代概述中的 period。

## 数据冲突

- 只报告，不自动覆盖。
- 与 `data/*.json` 逐项比较核心指标和渗透率。
- 一致：更新正式数据的官方来源字段。
- 不一致：写入 `input/official/conflicts.json`，保留现有正式数据。
- 新 period：在 `--write` 时写入正式数据。

## 验收指标

不要只统计文章数。至少统计：

- `listed`：列表页发现的文章数
- `selected`：目标时间范围内的文章数
- `fetched`：成功取得原始 HTML 的文章数
- `extracted`：成功提取“本周车市概述”的文章数
- `parsed`：成功解析的文章数
- `month`：月度收盘数
- `week`：周度快照数
- `failed`：提取/解析失败数
- `new`：新增正式数据数
- `matched`：与现有正式数据一致数
- `conflicts`：冲突数
- `missing_ytd` / `missing_penetration`：原文缺失字段数

节假日、春节、官网发布节奏都会影响文章数量，不能假设每周都有文章。不要用 52 个自然周或 7 天周数作为覆盖率分母；以实际官方文章清单为准。

## 抓取约束

- 使用浏览器 User-Agent、Accept、Accept-Language、Referer。
- 请求间隔默认 2 秒，失败重试并退避。
- 优先使用 `input/official/raw/` 缓存，`--force` 才重抓。
- 不抓取图片、附件或正文详细章节，只取“本周车市概述”。
- 官网资料版权归 CPCA；本管线用于项目内部数据整理，保留来源 URL 和文章标题。

## 源结构参考

详细 URL、HTML 结构和已知变体见 `references/site-structure.md`。
