# CPCA · 乘联会数据管道

CPCA 是 `mashang-data` 管理的汽车行业数据管道，位于平台的 `mashang-data/CPCA/`，以 Git 子模块保留独立的历史和远端。项目采集乘联会发布的乘用车市场数据，维护可追溯的年度数据，并生成《全国乘用车市场零售简报》。

## 2026-11-26 更新

- **数据截至 2026-11-22。** 补齐了统计截止日在 10 月 25 日至 11 月 22 日的 5 期数据，包含 10 月全月初步统计。历史复核补录了 2024 年 1 月首期和旧版摘要中的 9 份全月初步统计。 [最新周报](reports/2026-11-22.html)
- **年度资产从 2022 年开始。** `data/annual/YYYY.json` 每年一份，收录 247 个《车市扫描》区间和 15 份独立月报。2020–2021 年保留 99 篇原始 HTML 归档。
- **年度审计以 2022 年起的覆盖率为主。** 月度四项指标齐全率为 **100%（58/58 个已结束月份）**，已入库周度齐全率为 **74.1%（143/193 个区间）**，《车市扫描》日历覆盖率为 **98.2%（1,754/1,787 天）**。 [年度审计报告](reports/coverage_audit.html) · [回填与缺口记录](docs/findings.md#年度审计更新2026-11-26)

| 年份 | 月度四项齐全 | 周度四项齐全 | 《车市扫描》日历覆盖 |
| --- | ---: | ---: | ---: |
| 2022 | 12/12 | 0/48 | 100% |
| 2023 | 12/12 | 35/37 | 100% |
| 2024 | 12/12 | 37/37 | 100% |
| 2025 | 12/12 | 39/39 | 100% |
| 2026（截至 11/22） | 10/10 | 32/32 | 89.9% |

四项指标为乘用车和新能源的零售、批发。月度覆盖纳入独立《乘用车市场分析》，保留各自的发布口径。周度分母为已入库区间。2022 年的周度新能源和 2026 年春节前后的发布空档仍记在审计缺口中。

在平台根目录可用 `make status` 查看子模块版本，或用 `make validate-cpca` 校验正式和历史数据。采集、入库和生成报告从 CPCA 根目录运行。

## 1. 项目定位

- 周度数据来源为 CPCA 官网《车市扫描》，`input/weekly.md` 用于手工种子和兜底。
- 历史月度补充来源为 CPCA 官网《乘用车市场分析》，按原发布口径记入年度资产。
- 原始证据和结构化数据按来源及统计区间关联，周报可追溯到正式数据。

项目首先是一份可复查的数据台账，其次才是一份可阅读的周报。

## 2. 组织关系与署名

```text
CADA · 中国汽车流通协会
└── CPCA · 乘用车市场信息联席分会（乘联会）
```

项目与《全国乘用车市场零售简报》按使用场景署名。

| 使用场景 | 标准写法 |
| --- | --- |
| 数据源标识 | `CPCA` |
| 数据模块 | `cpca` |
| 周报名称 | CPCA Weekly Report |
| 图片品牌角标 | CPCA |
| 简报页脚 | 数据来源：乘联会（CPCA） |
| 正式报告首次引用 | 中国汽车流通协会乘用车市场信息联席分会（CPCA） |

## 3. 工作流

```text
CPCA 官网历史文章 ──> fetch_cpca_history.py ──> input/official/
                                                   │
input/weekly.md ───> ingest_weekly.py ─────────────┤
                                                   ▼
                                      ingest_official.py（对比/回填/冲突）
                                                   │
                                                   ▼
                                      data/YYYY-MM-DD.json（正式数据）
                                                   │
                                                   ▼
                                      standard_dataset.csv + HTML 简报
```

| 步骤 | 动作 | 输入 | 输出 | 执行者 |
| --- | --- | --- | --- | --- |
| 1 | 抓取官网历史 | CPCA 官网 | `input/official/` | official-history skill |
| 2 | 回填正式数据 | 官方归档 + 现有 JSON | `data/YYYY-MM-DD.json` | official-history skill |
| 3 | 手工种子（可选） | `input/weekly.md` | 非官方 period JSON | weekly-ingest skill |
| 4 | 生成标准表 | `data/*.json` | `data/standard_dataset.csv` | build script |
| 5 | 生成简报 | 标准表 + 最新 JSON 元数据 | `reports/YYYY-MM-DD.html` | report skill |
| 6 | 抽查与确认 | 简报、标准表、归档原文 | 可发布版本 | 人工 |

`input/official/` 是官网来源归档，`input/weekly.md` 是手工种子/兜底文本。正式数据统一写入 `data/*.json`，不保留两套并行的 JSON 事实源。官方历史回填使用 `fetch_cpca_history.py` + `ingest_official.py`；手工文本使用 `ingest_weekly.py`，且不会覆盖 `origin=official` 的正式数据。

Legacy V2 从 `input/legacy/` 生成 `data/legacy/`。年度审计读取正式区间、Legacy V2 和独立月报，生成按年划分的数据及覆盖率报告。周报由正式标准表生成。

## 4. 目录结构

```text
.
├── README.md
├── input/
│   ├── weekly.md                  # 手工种子/兜底文本
│   ├── official/                  # 官网正式来源归档（2024–2026）
│   │   ├── raw/<id>.html          # 原始 HTML，本地归档，不纳入版本库
│   │   ├── blocks/<date>.md       # 归一化“本周车市概述”
│   │   ├── manifest.json          # 来源、时间、hash、统计
│   │   └── conflicts.json         # 官方与正式数据差异报告
│   ├── legacy/                    # Legacy V2 旧格式归档（2020–2023）
│   │   ├── raw/<id>.html          # 2020–2023 原始 HTML，本地归档，不纳入版本库
│   │   ├── blocks/<date>.md       # 2022–2023 归一化旧格式摘要
│   │   └── manifest.json          # 来源、时间、状态、统计
│   └── monthly/
│       ├── reference.csv          # 独立月报核心指标、来源与内容哈希
│       └── raw/<id>.html          # 月报原始 HTML，本地归档
├── data/                          # 本地生成，不纳入版本库
│   ├── standard_dataset.csv       # 正式标准表：面向简报
│   ├── YYYY-MM-DD.json            # 正式数据集（2024–2026）
│   ├── annual/YYYY.json           # 2022 年起的年度数据包
│   ├── coverage_audit.csv         # 年度覆盖率审计表
│   ├── coverage_gaps.csv          # 缺口明细
│   ├── weekly_retail.csv          # 官方统计周乘用车零售导出
│   └── legacy/                    # Legacy V2 独立历史数据
│       ├── YYYY-MM-DD.json
│       └── legacy_dataset.csv
├── reports/
│   ├── 2026-11-22.html            # 最新 HTML 简报
│   └── coverage_audit.html        # 历史数据覆盖率审计报告
├── scripts/
│   ├── fetch_cpca_history.py      # 抓取官网正式历史文章
│   ├── ingest_official.py         # 正式数据回填/冲突核验
│   ├── fetch_legacy_history.py    # 抓取 2020–2023 旧格式文章
│   ├── legacy_parse.py            # Legacy V2 旧格式解析
│   ├── ingest_legacy.py           # 生成独立 Legacy 数据集
│   ├── validate_legacy.py         # Legacy 数据集校验
│   ├── coverage_audit.py          # 生成年份数据及覆盖率审计
│   ├── annual_data.py             # 年度记录和独立月报整理
│   ├── export_weekly_retail.py    # 导出逐统计周乘用车零售 CSV
│   ├── ingest_weekly.py           # 手工文本解析（不覆盖官方数据）
│   ├── validate_data.py           # 正式 JSON 数据集校验
│   ├── build_standard_dataset.py  # 生成正式标准表 CSV
│   └── render_report.py           # HTML 简报生成
└── .opencode/skills/
    ├── cpca-official-history/
    │   ├── SKILL.md
    │   └── references/site-structure.md
    ├── cpca-legacy-history/
    │   ├── SKILL.md
    │   └── references/legacy-formats.md
    ├── cpca-weekly-ingest/
    │   ├── SKILL.md
    │   └── references/schema.md
    └── cpca-weekly-report/
        └── SKILL.md
```

## 5. 数据集

`data/` 是本地生成目录。Git 同步归一化摘要、来源清单、独立月报摘录及 HTML 报告。本地原始 HTML 在 `input/*/raw/` 中单独归档。

- `data/standard_dataset.csv`：面向报告的标准表，只保留乘用车零售与新能源零售。
- `data/YYYY-MM-DD.json`：正式数据集，保留完整指标、状态、来源与校验。
- `data/annual/YYYY.json`：按年保存正式与历史区间、独立月报和审计缺口。

### 官方来源归档与正式数据

- `input/official/raw/<article_id>.html`：原始 HTML，本地归档，不纳入版本库；sha256 记录在 manifest。
- `input/official/blocks/<period_end>.md`：只包含“本周车市概述”的归一化文本。
- `input/official/manifest.json`：URL、文章 id、标题、发布时间、周区间、period、kind、hash、抓取时间与统计。
- `input/official/conflicts.json`：官方与正式数据的差异；冲突只报告，不覆盖。

正式数据来源字段：

`source.origin = official`、`source.url`、`source.article_id`、`source.published_at`、`source.content_hash`、`source.raw_path`、`source.block_path`。

数据类型：

- `kind=month`：月度收盘，只进入审计层，不进入周快照表，不参与周度增量。
- `kind=month_to_date`：周度快照，进入 `standard_dataset.csv`。

### Legacy V2（2022–2023）

- `input/legacy/`：独立旧格式归档；2020–2021 只有 raw HTML，2022–2023 解析为 `legacy-v2`。raw HTML 为本地归档，不纳入版本库。
- `data/legacy/`：独立历史数据集，不进入正式 `data/*.json`、`standard_dataset.csv` 或简报。
- `data/legacy/legacy_dataset.csv`：乘用车零售/批发宽表；新能源、YTD 缺失时留空。
- 规则：至少恢复乘用车零售或批发之一；不补数、不插值；不参与正式周度增量。
- 2020–2021 文章没有结构化摘要，只归档原始 HTML；如需解析，另做 Legacy V1（日均 → 周销量）。

### 年度数据与覆盖率审计

- 运行 `python3 scripts/coverage_audit.py`，生成 `data/annual/YYYY.json` 和年度审计。2022 年起每年一份，按统计截止日归年。
- 年度 JSON 中的 `periods` 保留结构化区间的全部字段，并补录旧版《车市扫描》明确发布的全月初步统计。同一个截止日可有周度及全月记录，按起止日期和类型识别。
- `monthly_market_analysis` 保留独立《乘用车市场分析》的全月销量及同比，来源见 `input/monthly/reference.csv`。月报和《车市扫描》有不同的发布口径与修订时间，各自保留原值。
- `data/coverage_audit.csv`：按年统计原始文章、周度区间、月度收盘、乘用车/新能源可用性和日历覆盖。
- `data/coverage_gaps.csv`：日历及官方发布缺口、新能源缺口和《车市扫描》全月缺口。
- `reports/coverage_audit.html`：单文件审计报告，口径与缺口说明内置。
- “四项齐全”要求同一来源提供全月乘用车及新能源的零售、批发，分母为已结束月份。周度缺口和月份覆盖单独统计。
- 增量采集时可用 `python3 scripts/fetch_cpca_history.py --start YYYY-MM-DD --refresh-list` 刷新官网文章清单，然后入库、验证并生成年度数据。

### 标准数据集（CSV）

`data/standard_dataset.csv` 按周生成快照表，用 `快照日期` 分组：

- 一般周：3 行 —— 最新区间、当月累计、当年累计。
- 每月首周：2 行 —— 当周、当年累计；当周即当月累计，所以不单列当月。

最新一周（2026-11-22）：

| 时间维度 | 乘用车零售 | 同比 | 新能源零售 | 同比 |
| --- | ---: | ---: | ---: | ---: |
| 最新区间（11/16–22） | 37.3 万辆 | -25.0%（估算） | 25.5 万辆 | -13.0%（估算） |
| 当月累计（11/1–22） | 98.4 万辆 | -25.0% | 70.2 万辆 | -13.0% |
| 当年累计（1/1–11/22） | 1,596.2 万辆 | -22.0% | 957.0 万辆 | -13.0% |

10月首周（2026-10-11）在 CSV 中保留两行：当周（10/1–11）45.9 万辆、当年累计（1/1–10/11）1,379.3 万辆；不单列当月累计。

每个周快照都有一个周区间行：首周标“当周”，第二周起标“最新区间”。首周直接取原文当月累计，第二周起由相邻两期累计差额计算；N 个周快照中，第二周起共产生 N-1 个派生的最新区间行。

这里的“周”指 **CPCA 官方发布的周度统计区间**，不保证 7 天。首周可能是 5–15 天的月内累计；月末是 `kind=month` 的月度收盘，不进入周表。标准表按官方发布节奏生成，不补齐自然周缺口。

CSV 列包括：`时间维度`、`乘用车零售(万辆)`、`乘用车零售同比(%)`、`新能源零售(万辆)`、`新能源零售同比(%)`、`快照日期`、`区间类型`、`区间开始`、`区间截止`、`日历天数`、`数据口径`。

口径：

- 当周：首周直接取原文当月累计；非首周用本周累计减上周累计。
- 当月累计、当年累计：原文发布值。
- 当周同比：首周用原文同比；非首周由相邻两期累计同比反推，受原文四舍五入影响；`数据口径` 列会标明。
- 10/1–11 的当周直接用原文 45.9（首周即当月累计）；如果拿 9 月 YTD 1,341.8 相减会得到 37.5，差 8.4 万辆来自 9 月初步统计基数修订，不能当作 10 月销量。
- 原文缺少今年以来累计时，不生成当年累计行；例如 2026-04-06 快照只有当周行。
- 批发、渗透率、生产不进入标准表，保留在 JSON 审计层。

非首周当周同比的计算方式：

```text
去年同区间 = 本期累计 / (1 + 本期累计同比)
           - 上期累计 / (1 + 上期累计同比)

区间同比 = (本期累计 - 上期累计) / 去年同区间 - 1
```

以乘用车零售为例：去年 10/1-11 约 60.39 万辆，去年 10/1-18 约 106.62 万辆，去年 10/12-18 约 46.23 万辆；今年 10/12-18 为 33.0 万辆，同比约 -28.6%。

注意：原文累计同比只保留整数百分比，反推的区间同比精度有限，误差可能达到约 ±1–2 个百分点，适合判断方向，不宜当作精确值。

### 审计数据集（JSON）

实际发布内容不是标准 ISO 周，而是月内累计窗口（如 10月1-11日、10月1-18日）和月度收盘（如 9月1-30日）；生产数据还可能是“10月第一至二周”。因此审计数据集按 `period.end` 命名，不按 ISO 周命名。

例如：

- `data/2024-01-31.json` — 2024 年 1 月收盘，初步统计
- `data/2024-06-23.json` — 2024 年周快照
- `data/2025-12-31.json` — 2025 年终收盘
- `data/2026-11-22.json` — 2026 年最新，官方来源

当前共 140 个正式区间文件，覆盖 2024-01-07 至 2026-11-22。

#### 核心指标

| key | 含义 | 单位 |
| --- | --- | --- |
| `passenger_retail` | 乘用车零售 | 万辆 |
| `passenger_wholesale` | 乘用车批发 | 万辆 |
| `nev_retail` | 新能源零售 | 万辆 |
| `nev_wholesale` | 新能源批发 | 万辆 |

每项包含：区间值、同比、较上月同期、年初至今累计、累计同比。原文未发布的字段允许为 `null`，不补数。

### 数据状态

- `source.origin = official`：来自官网归档；`manual` 为手工种子。
- `source.status = current`：本次最新周度区间。
- `source.status = snapshot`：历史周度区间。
- `source.status = preliminary`：月度收盘，原文标注“初步统计”。
- `source.report_status = preliminary`：报告标题显示“（初步统计）”；周度数据默认按此口径展示。
- `ytd_value` / `ytd_yoy_pct` / `penetration` 允许为 `null`：原文未发布时留空，不补数。
- `production.status = carried_over`：原文注明生产数据本周暂未更新。

### 派生值与校验

- `derived.daily_avg`：按区间天数折算的日均销量。
- `derived.increment`：同一月份内，本期累计减上期累计得到的区间增量。
- `validation.checks`：渗透率一致性、新能源不高于总量、累计与增量一致性、跨月累计基数衔接等。
- 派生值在报告中必须标注“派生值，非 CPCA 直接发布”。
- `flag` 表示需要人工确认，不代表数据错误；不自动调平。

### 数据规则

1. **原文优先**：所有数值必须来自 `input/official/blocks/*.md` 或 `input/weekly.md` 的对应段落；官方数据优先，按 `source.raw_path`、`source.block_path` 和 `period` 回溯。
2. **不推断**：原文未发布的指标不补位、不插值、不使用外部数据。
3. **不混口径**：零售与批发、区间与累计、燃油与新能源不得混用。
4. **单位统一**：对外统一使用“万辆”和“%”；原文以“辆”发布时保留换算关系。
5. **计算可识别**：同比、“较上月同期”优先采用原文口径；自行计算的字段必须标记为派生值。
6. **缺失可显示**：周报中缺失指标显示“未发布”，不显示为 0。
7. **失败不落盘**：无法确定区间、年份或关键口径时，skill 停止并说明原因，不写入半成品数据集。
8. **标准表优先**：报告核心表从 `standard_dataset.csv` 读取；JSON 仅作审计和补充信息。
9. **官方优先、冲突不覆盖**：官方数据回填以 `data/*.json` 为唯一正式数据；冲突写入 `input/official/conflicts.json`，不自动覆盖。`ingest_weekly.py` 不覆盖 `origin=official` 的数据。
10. **官方周口径**：周度 = 官方发布的统计区间，不强制 7 天；不按自然周补齐，不构造官网未发布的周。

## 6. Skill 职责

### `cpca-official-history`

- 用 `scripts/fetch_cpca_history.py` 抓取官网“车市扫描”文章，归档原始 HTML、URL、发布时间和 hash。
- 只提取“本周车市概述”，写入 `input/official/blocks/`。
- 用 `scripts/ingest_official.py` 对比正式数据：新增缺失 period，更新匹配项的官方来源；冲突只报告。
- 统计 `selected/fetched/extracted/parsed/month/week/failed/new/matched/conflicts/missing_*`，不以文章数量作为唯一验收标准。

### `cpca-weekly-ingest`

- 用 `scripts/ingest_weekly.py` 从 `input/weekly.md` 切分统计区间，生成手工种子数据。
- `--clean` 只删除非官方数据；`origin=official` 的正式数据保留，不被手工文本覆盖。
- 生成 `data/standard_dataset.csv`：每个周快照 3 行（最新区间、当月累计、当年累计），每月首周 2 行（当周、当年）；只保留乘用车零售与新能源零售。
- 运行 `python3 scripts/validate_data.py`，硬错误停止；同月累计链警告写入数据集，不静默调平。

### `cpca-weekly-report`

- 读取 `data/standard_dataset.csv` 作为三段指标数据，读取最新 JSON 的统计区间与报告状态。
- 生成单文件 HTML，离线可直接打开，不依赖外部 CDN。
- 品牌角标与页脚统一署名 CPCA。
- 缺失指标明确标注“未发布”，不补零、不隐藏。
- 校验 flag、口径说明、派生值说明保留在 JSON/CSV 数据层；简报正文只保留三段指标。
- 不自行改写数据，不添加数据集之外的结论。

## 7. 操作流程

### 官方历史回填 / 增量

```bash
# 1. 刷新官网清单并列出目标范围
python3 scripts/fetch_cpca_history.py --start 2026-10-19 --end 2026-11-22 --refresh-list --dry-run

# 2. 抓取并提取目标区间
python3 scripts/fetch_cpca_history.py --start 2026-10-19 --end 2026-11-22

# 3. 先对比，不写入
python3 scripts/ingest_official.py

# 4. 确认无意外冲突后回填
python3 scripts/ingest_official.py --write

# 5. 校验并重建报告与年度数据
python3 scripts/validate_data.py
python3 scripts/build_standard_dataset.py
python3 scripts/render_report.py
python3 scripts/coverage_audit.py
```

`--refresh-list` 更新文章清单并复用已缓存正文。`ingest_official.py --write` 写入新增区间并更新匹配记录，冲突进入差异报告。`--clean` 会清空已有摘要和清单，用于全量重建。

### Legacy V2 历史数据（2022–2023）

```bash
# 1. 抓取并解析 2022–2023 旧格式文章
python3 scripts/fetch_legacy_history.py --start 2022-01-01 --end 2023-12-31

# 2. 写入独立历史数据集
python3 scripts/ingest_legacy.py --write

# 3. 校验
python3 scripts/validate_legacy.py

# 4. 可选：把原始归档延伸到 2020–2021（只归档，不解析）
python3 scripts/fetch_legacy_history.py --start 2020-01-01 --end 2021-12-31 --archive-only
```

Legacy 管线只写 `input/legacy/` 和 `data/legacy/`，不修改 `data/*.json`、`data/standard_dataset.csv` 或 `reports/*.html`。旧格式缺失字段留空，不从累计值反推缺失周。

### 覆盖率审计

```bash
python3 scripts/coverage_audit.py
```

生成 `data/annual/YYYY.json`、`data/coverage_audit.csv`、`data/coverage_gaps.csv` 和 `reports/coverage_audit.html`。所需输入为正式 JSON、Legacy V2 JSON、归档摘要与独立月报摘录。纯 Git 检出可先运行 `python3 scripts/ingest_official.py --write` 和 `python3 scripts/ingest_legacy.py --write` 恢复结构化输入。

### 逐周乘用车零售导出

```bash
python3 scripts/export_weekly_retail.py
```

生成兼容导出 `data/weekly_retail.csv`，固定两列为 `年- XX周`、`周销量（万辆）`。行号按每年的区间顺序排列，包含周度、全月初步统计和缺口。2020–2021 年的归档占位及缺失周写 `无数据`。完整记录及补录的全月统计见 `data/annual/`。

### 手工种子更新

`input/weekly.md` 仅作为手工种子/兜底。运行 `ingest_weekly.py` 时，`origin=official` 的正式数据不会被覆盖；`--clean` 也只删除非官方数据。

```bash
python3 scripts/ingest_weekly.py
python3 scripts/validate_data.py
python3 scripts/build_standard_dataset.py
python3 scripts/render_report.py
```

### 历史简报

```bash
python3 scripts/render_report.py --period 2026-10-18 --out reports/2026-10-18.html
```

验收统计看 `input/official/manifest.json` 和 `input/official/conflicts.json`：`listed` / `selected` / `fetched` / `extracted` / `parsed` / `month` / `week` / `failed` / `new` / `matched` / `conflicts` / `missing_ytd` / `missing_penetration`。

## 8. 周报结构

1. 页头：报告名、数据统计区间、（初步统计）。
2. 最新区间（每月首周为“当周”）：乘用车市场零售、新能源市场零售；数值 + 同比。非首周标“（估算）”。
3. 当月累计：同一组两项指标；每月首周没有这一段。
4. 当年累计：同一组两项指标。
5. 页脚：数据来源：乘联会（CPCA）｜注：本简报为乘用车市场零售销量（含新能源），单位：万辆。

简报只保留乘用车零售、新能源零售两条线；批发、渗透率、生产、校验 flags 留在 JSON 审计层，不进入正文。

视觉上沿用浅色背景、白色卡片、深蓝标题、暖金点缀的简洁简报风格；不使用图表或装饰性元素干扰读数。桌面端以一屏读完为目标，短屏会自动压缩间距和字号。

## 9. 非目标

- 不抓取 CPCA 以外的数据源，不抓取图片、附件或文章正文的详细章节。
- 不补齐官网未发布的自然周，不构造 7 天周序列。
- 不做销量预测或趋势外推。
- 不生成未经人工确认的对外正式文件。
- 不把官方抓取结果直接写入 `input/weekly.md`。
- 不把 Legacy V2 数据并入正式标准表或简报；不从累计值反推旧格式缺失周。

## 10. 验收标准

- 任意一期简报都能从 HTML 回溯到 `data/*.json`，再回溯到 `input/official/raw/<id>.html` 或 `input/weekly.md` 的对应区间。
- Legacy V2 的每条记录都能从 `data/legacy/<date>.json` 回溯到 `input/legacy/raw/<article_id>.html`；2020–2021 只归档、不伪装成正式周数据。
- 数据集字段完整、类型正确；缺失值留空并记录，不补数。
- 覆盖率审计可从正式区间、Legacy V2、其归档摘要及独立月报摘录重算。报告、CSV 和年度 JSON 对应同一快照。
- 逐周导出每行对应一个官方统计区间或缺失周；无结构化数据写“无数据”，不用 0 或空值填充。
- 官方数据与正式数据冲突时，只报告、不覆盖。
- 简报正文只包含最新区间、当月累计、当年累计三段；不出现批发、生产、渗透率等扩展指标。
- 单文件 HTML 在离线环境下可正常打开和阅读。

## 11. 校验记录

- 140 个正式区间包括 108 个周度快照和 32 个全月区间。
- 2 条冲突已人工确认为解析修正（2025-10-31 的 `1.939.5` 千分位笔误、2025-12-28 的 ASCII 分号导致新能源批发串行），已接受官方值；当前无未解决冲突。
- 缺失字段：`missing_ytd=3`、`missing_penetration=64`；原文未发布时留空。
- 校验结果：0 错误；4 条渗透率警告（2025-04-30、2025-05-31 的发布值与销量比值不一致），保留原文，不调平。
- Legacy V2：2022–2023 共 98 个唯一区间（13 个月度收盘 + 85 个周度快照），0 解析失败，2 篇同 period 旧版标记为 `superseded`。
- Legacy 覆盖：98 个区间全部有乘用车零售/批发；46 个含新能源，44 个含 YTD；缺失字段留空。
- Legacy 数据：`data/legacy/` 98 个 JSON + 98 行 `legacy_dataset.csv`，不进入正式标准表和简报。
- 2022-05-31 文章同时包含 5 月收盘与 6/1-5，已拆成两条区间；2022-10-01 至 10-07 官网无独立摘要，保留缺口，不反推。
- 逐周兼容导出 `data/weekly_retail.csv` 共 343 行，其中 238 行有数据，105 行标记 `无数据`。
- 周度口径为官方发布周，不保证 7 天；不按自然周补齐。首周/间隔天数见 CSV 的 `日历天数`。
- 文章清单存在 2026-01-19 至 2026-03-08 的 6 个空周；详见 `docs/findings.md`，不按自然周补齐。
- 标准表 `data/standard_dataset.csv` 共 288 行，覆盖 2024-01 至 2026-11。
- 跨月累计基数存在初步统计修订。标准表首周直接用原文当月累计，不用 YTD 差额，避免把基数修订算进当月。
- 9月生产数据原文注明本周暂未更新，已记录为 `carried_over`。
- 年份取自文章标题/发布时间，不再按采集日期推断；官方数据集 `year_inferred=false`。

## 12. 数据观察

数据层发现记录在 `docs/findings.md`。

- 2026-01-19 至 2026-03-08 的 6 个空周：春节前停更 + 春节假期 + 节后恢复，不是抓取遗漏，不按自然周补齐。
- Legacy V2 的 2022-10-01 至 10-07 只有 `10月1-16日` 累计，没有独立周摘要；保留缺口，不用累计差反推。
- 2022 年《车市扫描》周度新能源数据缺失，全月数据见独立月报。2023 年 1 月及 2026 年春节前后的具体周度缺口见 `reports/coverage_audit.html`。

## 13. v1.0.0 发布记录

`v1.0.0` 于 2026-10-22 首次发布，发布时数据截止 2026-10-18。下列资产及检查结果对应发布快照。

### 发布资产

- 代码与文档：`scripts/`、`.opencode/skills/`、`README.md`、`docs/`。
- 手工种子：`input/weekly.md`。
- 归一化文本与来源索引：`input/official/blocks/`、`input/official/manifest.json`、`input/official/conflicts.json`、`input/legacy/blocks/`、`input/legacy/manifest.json`。
- 报告：`reports/2026-10-18.html`、`reports/coverage_audit.html`。
- `data/` 与 `input/*/raw/` 不进入版本库，分别由本地脚本生成和抓取。

本地快照（不随仓库同步）：

- 原始 HTML：`input/official/raw/` 与 `input/legacy/raw/`，覆盖 2020–2026。
- 正式数据：`data/*.json` 134 个，`data/standard_dataset.csv` 274 行。
- Legacy V2：`data/legacy/` 98 个 JSON，`data/legacy/legacy_dataset.csv` 98 行。
- 覆盖率审计：`data/coverage_audit.csv`、`data/coverage_gaps.csv`。
- 逐周导出：`data/weekly_retail.csv`，337 行（232 个有数据行 + 105 个 `无数据` 行）。

### 发布检查

发布检查需要本地先生成 `data/`；仓库本身不同步该目录。

```bash
python3 scripts/validate_data.py
python3 scripts/validate_legacy.py
python3 scripts/build_standard_dataset.py
python3 scripts/render_report.py
python3 scripts/coverage_audit.py
python3 scripts/export_weekly_retail.py
```

预期结果：

- 正式数据 `134` 个文件，`0` 错误、`4` 条渗透率 warning。
- Legacy 数据 `98` 个文件，`0` 错误。
- 标准表 `274` 行。
- 覆盖率审计 `232` 个区间，乘用车零售 `232/232`，新能源零售 `180/232`，2022–2026 日历覆盖 `97.7%`。
- 逐周导出 `337` 行，其中 `2026` 年 `41` 行 = `35` 个数据行 + `6` 个 `无数据` 行。

### 仓库卫生

`.gitignore` 已覆盖 `data/`、`input/official/raw/`、`input/legacy/raw/`、macOS 系统文件、Python 缓存、虚拟环境、日志、编辑器文件和 `blocks_failed/` 临时失败样本。`blocks/`、manifest 和报告仍会进入版本库；原始 HTML 与 `data/` 不同步。

仓库已初始化并推送到 `https://github.com/zhangzihaoDT/CPCA.git`：

- 分支：`main`
- 发布提交：`Release v1.0.0`
- 发布标签：`v1.0.0`

后续提交前确认 `data/`、`input/*/raw/`、`blocks_failed/`、`__pycache__/` 和 `.DS_Store` 未出现在暂存列表：

```bash
git status -sb
git log --oneline --decorate -1
```
