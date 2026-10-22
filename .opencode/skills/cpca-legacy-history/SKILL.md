---
name: CPCA Legacy History
description: 用 Legacy V2 管线恢复 2022–2023 年 CPCA 旧格式周度文章中的乘用车零售/批发数据，独立存放，不改变正式周度简报口径；2020–2021 只归档原始 HTML。
---

# CPCA Legacy History

恢复 2022–2023 年旧格式文章中的乘用车数据，作为**独立历史资产**。

Legacy 数据不进入 `data/*.json`，不进入 `standard_dataset.csv`，也不影响 `reports/*.html` 的正式周度简报。

## 路径约定

本文中的 `input/`、`data/`、`scripts/` 均相对项目根目录，命令在项目根目录执行。

## 产出

```text
input/legacy/
├── raw/<article_id>.html        # 2020–2023 原始 HTML
├── blocks/<period_end>.md       # 2022–2023 归一化旧格式摘要
├── blocks_failed/               # 失败样本
└── manifest.json                # 来源、时间、状态、统计

data/legacy/
├── <period_end>.json            # Legacy V2 单期数据
└── legacy_dataset.csv           # 历史乘用车零售/批发宽表
```

2020–2021 只做 raw archive，manifest 状态为 `archived_only`；2022–2023 解析为 `legacy-v2`。

## 工作流

1. 抓取并解析 2022–2023：

   ```bash
   python3 scripts/fetch_legacy_history.py --start 2022-01-01 --end 2023-12-31
   ```

2. 写入独立数据集：

   ```bash
   python3 scripts/ingest_legacy.py --write
   ```

3. 校验：

   ```bash
   python3 scripts/validate_legacy.py
   ```

4. 如需把原始归档延伸到 2020–2021：

   ```bash
   python3 scripts/fetch_legacy_history.py --start 2020-01-01 --end 2021-12-31 --archive-only
   ```

## Legacy 数据规则

- 至少恢复 `passenger_retail` 或 `passenger_wholesale` 之一。
- `nev_retail`、`nev_wholesale`、`ytd_value`、`ytd_yoy_pct`、`penetration` 原文缺失时写 `null`。
- 不补数、不插值、不推断。
- 旧格式可能有 `环比上周`，它不是“较上月同期”；不要混用。
- 月末文章按 `kind=month` 记录，但仍在独立数据集中，不进入正式周表。
- 同一 period 有“数据更新版”时，保留发布时间更新的文章；旧记录标记 `superseded`。
- 同一篇文章可能包含多个区间：如 2022-05-31 同时有 5 月收盘和 6/1-5，应拆成两条；本周区间 + 本月累计不重复拆。
- 同一 period 的新能源段落要与乘用车主段合并，不能误判成第二区间。
- 历史采集层可以容忍缺失；正式周度简报仍严格要求乘用车零售、新能源零售及同比。

## 统计口径

不要只数文章。至少统计：

- `selected` / `fetched`
- `extracted` / `parsed` / `failed`
- `month` / `week`
- `periods`（去重后的区间数，可能大于文章数）
- `superseded`（同 period 的旧文章）
- `superseded_periods`（被更新版覆盖的区间）
- `archived_only`（2020–2021 只归档）
- `has_passenger_retail` / `has_passenger_wholesale` / `has_nev` / `has_ytd`

## 关键约束

- 不修改 `data/*.json`。
- 不修改 `data/standard_dataset.csv`。
- 不修改 `reports/*.html` 的生成逻辑。
- 不把 Legacy 数据并入正式周度增量计算。
- 2020–2021 的正文没有可解析的乘用车摘要，只归档 HTML；如后续需要，另做 Legacy V1 日均解析。

旧格式细节见 `references/legacy-formats.md`。
