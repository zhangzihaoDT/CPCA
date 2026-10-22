# CPCA Weekly · 乘联会周度数据跟踪

一个用于跟踪乘联会（CPCA）周度数据指标的轻量项目。

官方历史数据从 CPCA 官网抓取；`input/weekly.md` 仅作为手工种子/兜底。结构化数据进入审计用 JSON 和标准表 CSV，再由 `cpca-weekly-report` 生成 HTML 版《全国乘用车市场零售简报》。

> **当前发布：v1.0.0 · 2026-10-22**  
> 数据截止 2026-10-18：正式数据 2024-01-14–2026-10-18；Legacy V2 2022–2023；原始归档 2020–2023（本地，不随仓库同步）。

## 1. 项目定位

- 只跟踪 CPCA 周度发布中的乘用车市场指标。
- 官方历史数据从 CPCA 官网抓取；`input/weekly.md` 仅作为手工种子/兜底。
- 原始文本、结构化数据集、HTML 周报按统计区间一一对应，可回溯。
- 只抓取 CPCA 官网“车市扫描”栏目；不做预测、不合并其他数据源。

项目首先是一份可复查的数据台账，其次才是一份可阅读的周报。

## 2. 组织关系与署名

```text
CADA · 中国汽车流通协会
└── CPCA · 乘用车市场信息联席分会（乘联会）
```

《全国乘用车市场零售简报》中的署名规则：

| 场景 | 使用写法 |
| --- | --- |
| 数据发布主体 | CPCA（乘联会） |
| 上级行业协会 | CADA（中国汽车流通协会） |
| 日常品牌角标 | CPCA |
| 报告页脚 | 数据来源：乘联会（CPCA） |
| 组织关系说明 | CPCA 是 CADA（中国汽车流通协会）下属的乘用车市场信息联席分会 |

一句话原则：**数据归 CPCA，关系提 CADA，角标只写 CPCA。**

不使用“CADA 数据”“CADA 乘联会”等写法，避免把上级协会与数据发布主体混为一谈。

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

Legacy V2 是旁路：`input/legacy/` → `data/legacy/`，不经过 `ingest_official.py`、标准表或简报，属于可追溯历史资产，不是第二套正式事实源。

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
│   └── legacy/                    # Legacy V2 旧格式归档（2020–2023）
│       ├── raw/<id>.html          # 2020–2023 原始 HTML，本地归档，不纳入版本库
│       ├── blocks/<date>.md       # 2022–2023 归一化旧格式摘要
│       └── manifest.json          # 来源、时间、状态、统计
├── data/                          # 本地生成，不纳入版本库
│   ├── standard_dataset.csv       # 正式标准表：面向简报
│   ├── YYYY-MM-DD.json            # 正式数据集（2024–2026）
│   ├── coverage_audit.csv         # 年度覆盖率审计表
│   ├── coverage_gaps.csv          # 缺口明细
│   ├── weekly_retail.csv          # 官方统计周乘用车零售导出
│   └── legacy/                    # Legacy V2 独立历史数据
│       ├── YYYY-MM-DD.json
│       └── legacy_dataset.csv
├── reports/
│   ├── 2026-10-18.html            # 生成的 HTML 简报
│   └── coverage_audit.html        # 历史数据覆盖率审计报告
├── scripts/
│   ├── fetch_cpca_history.py      # 抓取官网正式历史文章
│   ├── ingest_official.py         # 正式数据回填/冲突核验
│   ├── fetch_legacy_history.py    # 抓取 2020–2023 旧格式文章
│   ├── legacy_parse.py            # Legacy V2 旧格式解析
│   ├── ingest_legacy.py           # 生成独立 Legacy 数据集
│   ├── validate_legacy.py         # Legacy 数据集校验
│   ├── coverage_audit.py          # 生成历史数据覆盖率审计
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

`data/` 是本地生成目录，默认通过 `.gitignore` 排除，不随仓库同步；可由 `input/weekly.md`、`input/official/manifest.json` 和 `input/legacy/manifest.json` 重新生成。数据分两层：

- `data/standard_dataset.csv`：面向报告的标准表，只保留乘用车零售与新能源零售。
- `data/YYYY-MM-DD.json`：正式数据集，保留完整指标、状态、来源与校验。

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

### 覆盖率审计（2020–2026）

- `scripts/coverage_audit.py` 同时读取 `data/*.json`、`data/legacy/*.json` 和两份 manifest。
- `data/coverage_audit.csv`：按年统计原始文章、周度区间、月度收盘、乘用车/新能源可用性和日历覆盖。
- `data/coverage_gaps.csv`：未解析年份、日历缺口、新能源缺口、完整月度收盘缺口的区间明细。
- `reports/coverage_audit.html`：单文件审计报告，口径与缺口说明内置。
- “可覆盖月份”只表示该月有任意部分区间数据；“完整月度收盘”要求该月有 `kind=month` 记录。两者不混用。
- 审计只读现有资产，不补数、不反推，不修改正式简报或标准表。

### 标准数据集（CSV）

`data/standard_dataset.csv` 按周生成快照表，用 `快照日期` 分组：

- 一般周：3 行 —— 最新区间、当月累计、当年累计。
- 每月首周：2 行 —— 当周、当年累计；当周即当月累计，所以不单列当月。

最新一周（2026-10-18）：

| 时间维度 | 乘用车零售 | 同比 | 新能源零售 | 同比 |
| --- | ---: | ---: | ---: | ---: |
| 最新区间（10/12–18） | 33.0 万辆 | -28.6% | 23.9 万辆 | -13.0% |
| 当月累计（10/1–18） | 78.9 万辆 | -26.0% | 52.0 万辆 | -13.0% |
| 当年累计（1/1–10/18） | 1,412.3 万辆 | -22.0% | 827.8 万辆 | -13.0% |

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
- `data/2026-10-18.json` — 2026 年最新，官方来源

当前共 134 个区间文件，覆盖 2024-01-14 至 2026-10-18。

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
# 1. 先列出目标范围文章
python3 scripts/fetch_cpca_history.py --start 2024-01-14 --end 2025-12-31 --dry-run

# 2. 抓取并提取（增量不要加 --clean）
python3 scripts/fetch_cpca_history.py --start 2024-01-14 --end 2025-12-31

# 3. 先对比，不写入
python3 scripts/ingest_official.py

# 4. 确认无意外冲突后回填
python3 scripts/ingest_official.py --write

# 5. 校验、重建标准表、生成简报
python3 scripts/validate_data.py
python3 scripts/build_standard_dataset.py
python3 scripts/render_report.py
```

`--clean` 仅用于从零全量重建，会清空已有 blocks/manifest；按日期段增量回填不要加 `--clean`。脚本会跳过已缓存文章，`ingest_official.py` 只回填缺失 period，冲突只报告。

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

生成 `data/coverage_audit.csv`、`data/coverage_gaps.csv` 和 `reports/coverage_audit.html`。审计只读现有正式数据、Legacy 数据和原始归档，不修改任何数据集。

### 逐周乘用车零售导出

```bash
python3 scripts/export_weekly_retail.py
```

生成 `data/weekly_retail.csv`，固定两列：`年- XX周`、`周销量（万辆）`。每个官方统计区间一行，包含周度区间和月度收盘；2026 年 35 个官方区间 + 6 个缺失周 = 41 行，2022 年 50 个官方区间 + 1 个缺口 = 51 行。周序号是该年按时间排序后的行号（含缺失周），不是 ISO 周；月度收盘行使用原文月度值，不等同于严格周销量。2020–2021 只有原始归档，按官方区间输出 `无数据`；缺失周同样写 `无数据`。

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
- 覆盖率审计可从 `data/*.json` + `data/legacy/*.json` 重算，报告、CSV 与数据资产一致；缺口只记录、不补数。
- 逐周导出每行对应一个官方统计区间或缺失周；无结构化数据写“无数据”，不用 0 或空值填充。
- 官方数据与正式数据冲突时，只报告、不覆盖。
- 简报正文只包含最新区间、当月累计、当年累计三段；不出现批发、生产、渗透率等扩展指标。
- 单文件 HTML 在离线环境下可正常打开和阅读。

## 11. 当前状态

- 发布快照：`v1.0.0`（2026-10-22）；正式数据 2024-01-14 至 2026-10-18，最近文章发布 2026-10-21，共 134 篇。
- 2024-2025 回填：`selected=99`、`fetched=99`、`extracted=99`、`parsed=99`、`failed=0`；`new=99`，2026 年已入库的 35 条全部 `matched`。
- 数据类型：月度收盘 `month=31`、官方周度快照 `week=103`。
- 2 条冲突已人工确认为解析修正（2025-10-31 的 `1.939.5` 千分位笔误、2025-12-28 的 ASCII 分号导致新能源批发串行），已接受官方值；当前无未解决冲突。
- 缺失字段：`missing_ytd=3`、`missing_penetration=63`；原文未发布时留空，不补数。
- 校验结果：0 错误；4 条渗透率警告（2025-04-30、2025-05-31 的发布值与销量比值不一致），保留原文，不调平。
- 正式数据：134 个 `data/*.json`，103 个官方周度快照进入标准表。
- Legacy V2：2022–2023 共 98 个唯一区间（13 个月度收盘 + 85 个周度快照），0 解析失败，2 篇同 period 旧版标记为 `superseded`。
- Legacy 覆盖：98 个区间全部有乘用车零售/批发；46 个含新能源，44 个含 YTD；缺失字段留空。
- Legacy 数据：`data/legacy/` 98 个 JSON + 98 行 `legacy_dataset.csv`，不进入正式标准表和简报。
- 2022-05-31 文章同时包含 5 月收盘与 6/1-5，已拆成两条区间；2022-10-01 至 10-07 官网无独立摘要，保留缺口，不反推。
- 2020–2021 已归档 99 篇原始 HTML（`archived_only`），原始资产可追溯到 2020 年；解析数据从 2022 年起。
- 覆盖率审计：232 个已解析区间（188 周度 + 44 月度）；乘用车零售 232/232，新能源零售 180/232；2022–2026 日历覆盖 97.7%，缺口 40 天。
- 覆盖率审计报告：`reports/coverage_audit.html`；年度数据见 `data/coverage_audit.csv`，缺口见 `data/coverage_gaps.csv`。
- 逐周导出：`data/weekly_retail.csv` 共 337 行 = 232 个有数据行 + 105 个 `无数据` 行；2020 年 50、2021 年 48、2022 年 51（50 个官方区间 + 1 个缺口）、2023 年 48、2024 年 48、2025 年 51、2026 年 41（35 个官方区间 + 6 个缺失周）。2021 年有一篇同区间“数据更新”文章，去重后为 48 个唯一区间。
- 周度口径为官方发布周，不保证 7 天；不按自然周补齐。首周/间隔天数见 CSV 的 `日历天数`。
- 文章清单存在 2026-01-19 至 2026-03-08 的 6 个空周；详见 `docs/findings.md`，不按自然周补齐。
- 标准表：`data/standard_dataset.csv` 共 274 行，覆盖 2024-01 至 2026-10。
- 简报：`reports/2026-10-18.html`，结构与视觉保持不变；最新一周仍为 3 行。
- 跨月累计基数存在初步统计修订。标准表首周直接用原文当月累计，不用 YTD 差额，避免把基数修订算进当月。
- 9月生产数据原文注明本周暂未更新，已记录为 `carried_over`。
- 年份取自文章标题/发布时间，不再按采集日期推断；官方数据集 `year_inferred=false`。

## 12. 数据观察

数据层发现记录在 `docs/findings.md`。

- 2026-01-19 至 2026-03-08 的 6 个空周：春节前停更 + 春节假期 + 节后恢复，不是抓取遗漏，不按自然周补齐。
- Legacy V2 的 2022-10-01 至 10-07 只有 `10月1-16日` 累计，没有独立周摘要；保留缺口，不用累计差反推。
- 覆盖率审计：2020–2021 仅原始归档；2022 无新能源零售；2022 当前入库资产只有 2 个完整月度收盘（旧格式部分月末累计尚未入库）；2023 年 1 月缺完整月度收盘。详见 `reports/coverage_audit.html`。

## 13. 发布

当前版本 `v1.0.0`，发布日期 2026-10-22，数据截止 2026-10-18。本版为首次公开发布，包含正式数据、Legacy V2、覆盖率审计和逐周导出。

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
