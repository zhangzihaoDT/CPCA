---
name: CPCA Weekly Ingest
description: 将 input/weekly.md 中的乘联会（CPCA）周度文本解析为 JSON 审计数据集和 standard_dataset.csv 标准表，并运行校验。
---

# CPCA Weekly Ingest

把 `input/weekly.md` 中持续累积的周度文本，转换为 JSON 审计数据集和 `data/standard_dataset.csv` 标准表。

## 路径约定

除特别说明外，本文中的 `input/`、`data/`、`scripts/` 均相对项目根目录，命令在项目根目录执行；`references/schema.md` 相对本 skill 目录。

## 输入与输出

- 输入：`input/weekly.md`，由人工持续更新，累积全部周度文本。
- 参考：`references/schema.md`，字段定义与命名规则。
- 输出：
  - `data/YYYY-MM-DD.json`：每个统计区间一个文件，作为审计层。
  - `data/standard_dataset.csv`：面向报告的标准表，只保留乘用车零售与新能源零售。
  - 校验结果：`python3 scripts/validate_data.py`。

## 工作流

1. 读取 `input/weekly.md`，确认最新区间和块数。
2. 从全文重建 period JSON：

   ```bash
   python3 scripts/ingest_weekly.py --clean
   ```

   `--clean` 只删除非官方数据；`origin=official` 的正式数据保留。`weekly.md` 是手工种子/兜底，不是唯一来源；官方历史数据由 `cpca-official-history` 管理，手工文本不覆盖官方记录。

3. 检查脚本输出：解析块数、最新区间、是否有异常。
4. 运行 `python3 scripts/validate_data.py`。
5. 硬错误必须修复；同月累计链警告写入对应 JSON 的 `validation.checks` 和 `notes`，不要静默调平。
6. 运行 `python3 scripts/build_standard_dataset.py`，生成标准表。
7. 运行 `python3 scripts/render_report.py` 生成 HTML 简报。
8. 汇报：JSON 数量、最新区间、校验 flags、报告路径。

## 解析规则

### 指标映射

| 原文 | key |
| --- | --- |
| 全国乘用车市场零售 | `passenger_retail` |
| 全国乘用车厂商批发 | `passenger_wholesale` |
| 全国乘用车新能源市场零售 | `nev_retail` |
| 全国乘用车厂商新能源批发 | `nev_wholesale` |

每项提取：

- 区间值：`value`
- 同比：`yoy_pct`
- 较上月同期：`vs_prev_month_same_period_pct`
- 今年以来累计：`ytd_value`
- 累计同比：`ytd_yoy_pct`

“较上月同期”必须写入 `vs_prev_month_same_period_pct`，不要写成周环比 `wow`，也不要在报告中改称“环比”。

### 数字

- 去掉千分位逗号：`1,412.3` → `1412.3`。
- 单位统一为 `万辆`；原文以“辆”发布时记录换算关系，不直接混用。
- 百分数存百分数数值：`下降26%` → `-26.0`。
- 不把 `52万辆` 写成 `520000`。

### 状态

- 原文出现“初步统计”：`source.status = "preliminary"`。
- 周度报告默认按初步统计口径展示：`source.report_status = "preliminary"`，报告标题显示“（初步统计）”。
- 原文出现“此部分数据本周暂未更新”：对应 `production.status = "carried_over"`，并在 `note` 保留原句。
- 同一输入中的旧区间：`source.status = "snapshot"`。
- 最新区间：`source.status = "current"`。

### 生产数据

- 生产周期可能不是零售/批发的同一区间，例如“10月第一至二周”对应零售“10月1-18日”。
- 单独记录 `production.period`，不要强行换算成同一区间。
- 相对区间无法确定具体结束日时，`production.period.end = null`，保留 `label`。
- 本期没有生产数据时，`production = null`。

### 年份

- 原文通常不写年份。按 `captured_at` 推断，并设置 `source.year_inferred = true`、`source.year_basis` 说明依据。
- 如果采集日期与原文月份明显冲突，停止并询问，不要猜。

## 写入与修订

- 写入前检查 `data/<period.end>.json` 是否已存在。
- 已存在且 `source.origin = official`：不覆盖，交给 `cpca-official-history` 处理；如需变更，先做冲突核验。
- 已存在且所有发布值一致：跳过，不重复写入。
- 已存在但值不同（且非 official）：
  - 更新文件；
  - 在 `notes` 增加 `type: "revision"` 的记录，写明旧值、新值、本次 edition；
  - 不静默覆盖。
- 同一 `period.end` 不允许出现两个文件。
- 原文保留在 `input/weekly.md`，`source.raw_path` 指向该文件；需要引用具体句子时写入 `notes`。

## 派生值

只生成 schema 中定义的派生值：

- `daily_avg = value / days`，保留两位小数。
- 同一月份有更早累计快照时，生成 `increment = 本期累计 - 上期累计`，并记录 `increment_from`、`increment_days`。
- 非首周当周同比由 `build_standard_dataset.py` 用两期累计同比反推，写入 CSV 的 `数据口径`，不写入 JSON。
- 派生值必须在 `notes` 标注 `type: "derived"`。
- 不要生成原文和 schema 之外的预测或趋势判断。

## 标准表

`data/standard_dataset.csv` 是面向上层使用的标准数据集，按官方发布周生成快照表，用 `快照日期` 分组：

- 一般周：3 行 —— 最新区间、当月累计、当年累计。
- 每月首周：2 行 —— 当周、当年累计；当周即当月累计，不单列当月。
- “周”指 CPCA 官方发布统计区间，不保证 7 天；首周可能是 5–15 天，不按自然周补齐。

每个周快照都有一个周区间行：首周标“当周”，第二周起标“最新区间”。首周直接取原文当月累计，第二周起由相邻两期累计差额计算；N 个周快照中，第二周起共产生 N-1 个派生的最新区间行。例如 10/11 首周只有 2 行（当周、当年），10/18 第二周有 3 行（最新区间、当月、当年）；9/30 是月度收盘，只作基数和审计，不进入周快照表。

列只保留：

- 时间维度
- 乘用车零售（万辆）、乘用车零售同比（%）
- 新能源零售（万辆）、新能源零售同比（%）
- 快照日期
- 区间类型
- 区间开始、区间截止、日历天数
- 数据口径

前五列是面向阅读和报告的核心视图，后面的列用于追溯。

批发、渗透率、生产等字段保留在 JSON 审计层，不进入标准表。首周当周用原文同比；非首周当周由相邻两期累计同比反推，CSV 中 `数据口径` 标注为“由相邻两期累计值及累计同比反推”。

标准表由脚本生成，不手工编辑：

```bash
python3 scripts/build_standard_dataset.py
```

## 校验

运行：

```bash
python3 scripts/validate_data.py
```

必须通过：

- JSON 可解析，必填字段齐全。
- `period.days` 与日期差一致。
- 新能源销量不大于乘用车总销量。
- 渗透率与 `nev / total` 的差异不超过 0.3 个百分点。

需要记录但不能静默修复：

- 跨月累计基数差异（可能是初步统计修订）。
- 同月两期累计差与增量不一致（通常是四舍五入）。
- 生产数据沿用上期。

## 失败处理

以下情况停止写入，并向用户说明：

- 无法确定统计区间或年份。
- 同一指标在同一数据块出现多个互相矛盾的数值。
- 单位或口径无法判断。
- 原文缺失核心四项销量中的多项。
- 已有数据集与新数据冲突且无法判断是修订还是录入错误。

不要用往期数据补缺失值，不要把缺失写成 0。
