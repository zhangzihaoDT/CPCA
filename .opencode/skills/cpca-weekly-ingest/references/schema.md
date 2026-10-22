# CPCA 周期数据集 schema v0.1

## 文件命名

每个统计区间一个 JSON 文件，放在 `data/` 下：

```text
data/YYYY-MM-DD.json
```

文件名日期使用 `period.end`，即该统计区间的截止日，不使用发布日或 ISO 周编号。

示例：

- `data/2026-09-30.json` — 9月1-30日
- `data/2026-10-11.json` — 10月1-11日
- `data/2026-10-18.json` — 10月1-18日

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | 是 | 当前固定为 `"0.1"` |
| `period` | object | 是 | 统计区间 |
| `source` | object | 是 | 来源与采集信息 |
| `metrics` | object | 是 | 四项核心销量指标 |
| `penetration` | object | 是 | 零售与批发渗透率 |
| `production` | object \| null | 是 | 生产指标，本期无数据时写 `null` |
| `derived` | object | 是 | 派生值，必须可复算 |
| `validation` | object | 是 | 自动校验结果 |
| `notes` | array | 是 | 口径、状态与异常说明 |

## period

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `start` | `YYYY-MM-DD` | 区间开始 |
| `end` | `YYYY-MM-DD` | 区间结束 |
| `label` | string | 原文标签，如 `10月1-18日` |
| `kind` | string | `month` 或 `month_to_date` |
| `days` | integer | 区间自然日天数，必须等于 `end - start + 1` |

`kind=month_to_date` 表示 CPCA 官方发布的周度快照，不保证 7 天；首周可能覆盖 5–15 天。`kind=month` 表示月度收盘，不进入周快照表。

## source

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `publisher` | string | 固定 `CPCA` |
| `publisher_full` | string | `乘用车市场信息联席分会（乘联会）` |
| `parent_association` | string | `CADA（中国汽车流通协会）` |
| `section` | string | 原文栏目，如 `本周车市概述` |
| `report_title` | string | `全国乘用车市场零售简报` |
| `raw_path` | string | 原始 HTML 路径（官方）或 `input/weekly.md`（手工） |
| `block_path` | string \| null | 归一化概述块路径（官方） |
| `url` | string \| null | 官网文章 URL（官方） |
| `article_id` | string \| null | 官网文章 id（官方） |
| `title` | string \| null | 文章标题（官方） |
| `week_range` | string \| null | 文章标题覆盖的周区间（官方） |
| `published_at` | string \| null | 文章发布时间（官方） |
| `fetched_at` | string \| null | 抓取时间（官方） |
| `content_hash` | string \| null | 原始 HTML 的 sha256（官方） |
| `origin` | string | `official` 或 `manual` |
| `edition` | string | 本次录入批次，通常为最新截止日 |
| `edition_week` | string | 最新截止日所在 ISO 周，如 `2026-W42` |
| `captured_at` | `YYYY-MM-DD` | 采集日期 |
| `year_inferred` | boolean | 原文未写年份且按采集日期推断时为 `true`；官方数据为 `false` |
| `year_basis` | string | 年份来源说明 |
| `status` | string | `current`、`snapshot` 或 `preliminary` |
| `report_status` | string | 报告展示口径；`preliminary` 时报告标题标“（初步统计）” |

### source.status

- `current`：本次录入的最新区间。
- `snapshot`：历史周度区间，用于趋势或增量。
- `preliminary`：月度收盘，原文明确标注“初步统计”，后续可能修订。

### origin

- `official`：来自 `input/official/`，`raw_path` 指向原始 HTML，`block_path` 指向归一化概述块。
- `manual`：来自 `input/weekly.md`，`raw_path` 指向该文件。

## metrics

固定四个 key：

```text
passenger_retail
passenger_wholesale
nev_retail
nev_wholesale
```

每个指标对象：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `label` | string | 中文名称 |
| `value` | number | 区间销量，单位万辆 |
| `unit` | string | 固定 `万辆` |
| `yoy_pct` | number | 同比，百分数数值，如 `-26.0` 表示 -26.0% |
| `vs_prev_month_same_period_pct` | number | “较上月同期”，百分数数值 |
| `ytd_value` | number \| null | 年初至区间结束累计销量，单位万辆；原文未发布时 `null` |
| `ytd_yoy_pct` | number \| null | 累计同比，百分数数值；原文未发布时 `null` |

注意：

- “较上月同期”不是周环比，字段名不要写成 `wow`。
- 百分数直接存百分数数值，不存小数比例。
- 原文使用千分位逗号时去掉逗号，如 `1,412.3` → `1412.3`。

## penetration

```json
{
  "retail_pct": 65.9,
  "wholesale_pct": 76.8
}
```

类型为 `object | null`。原文未提供渗透率时写 `null`，不计算、不补数。校验脚本会用 `nev / total` 复核，容差 0.5 个百分点。

## production

```json
{
  "period": {
    "start": "2026-10-01",
    "end": null,
    "label": "10月第一至二周"
  },
  "status": "current",
  "note": null,
  "metrics": {
    "pure_fuel_light_vehicle": {
      "label": "纯燃料轻型车生产",
      "value": 15.3,
      "unit": "万辆",
      "yoy_pct": -43.0,
      "vs_prev_month_same_period_pct": -16.0
    },
    "hybrid_and_phev": {
      "label": "混合动力与插混生产",
      "value": 15.2,
      "unit": "万辆",
      "yoy_pct": -18.0,
      "vs_prev_month_same_period_pct": 2.0
    }
  }
}
```

规则：

- 生产周期可能与零售/批发不同，单独记录，不强行对齐。
- 原文只写“第一至二周”“前三周”等相对区间时，`end` 写 `null`，保留 `label`。
- 原文注明“此部分数据本周暂未更新”时，`status` 写 `carried_over`，并在 `note` 中保留说明。
- 本期没有生产数据时，整个 `production` 写 `null`。

## derived

```json
{
  "days": 18,
  "daily_avg": {
    "passenger_retail": 4.38,
    "passenger_wholesale": 4.74,
    "nev_retail": 2.89,
    "nev_wholesale": 3.64
  },
  "increment_from": "2026-10-11",
  "increment_days": 7,
  "increment": {
    "passenger_retail": 33.0,
    "passenger_wholesale": 46.8,
    "nev_retail": 23.9,
    "nev_wholesale": 35.4
  },
  "increment_daily_avg": {
    "passenger_retail": 4.71,
    "passenger_wholesale": 6.69,
    "nev_retail": 3.41,
    "nev_wholesale": 5.06
  }
}
```

规则：

- `daily_avg` = `value / days`，保留两位小数。
- `increment` 仅在同一月份存在更早累计快照时生成：本期累计减上期累计。
- 有 `increment` 时必须写 `increment_from` 和 `increment_days`。
- 所有派生值必须在 `notes` 或报告脚注中标注为派生值。

## validation

```json
{
  "checks": [
    {
      "name": "penetration_retail",
      "status": "pass",
      "detail": "新能源零售 52.0 / 乘用车零售 78.9 = 65.91%，发布值 65.9%。"
    },
    {
      "name": "ytd_base_vs_2026-09-30",
      "status": "flag",
      "detail": "以9月初步统计累计为基数推算10月累计存在差异，疑似基数修订。"
    }
  ]
}
```

- `status` 取 `pass` 或 `flag`。
- `flag` 表示需要人工确认，不代表数据错误。
- 常见检查：渗透率一致性、新能源不高于总量、累计与增量一致性、跨月累计基数衔接、生产数据状态。

## notes

```json
[
  {
    "type": "definition",
    "text": "“较上月同期”按上月同期累计值比较，不是周环比。"
  }
]
```

常见 `type`：

- `year`：年份推断
- `definition`：口径说明
- `period`：周期差异
- `derived`：派生值
- `revision`：基数或修订说明
- `status`：初步统计、沿用上期等状态
- `source_text`：原文笔误或特殊写法

## 写入顺序

1. 解析原文并生成 JSON。
2. 运行 `python3 scripts/validate_data.py`。
3. 硬错误必须修复；警告写入 `validation.checks` 与 `notes`。
4. 运行 `python3 scripts/render_report.py` 生成报告。
