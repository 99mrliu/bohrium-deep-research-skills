# 漏检归因分类法与决策树（attribution_taxonomy）

每条漏检必须恰好归入一个主类别，并附带：探针证据（文件、字段、引用片段）、
致漏的 `query_id`、字段与时间窗指针。权威实现为 `scripts/attribute_miss.py`。

## 五类漏检类别

| 类别 | 含义 | 必需证据 |
| --- | --- | --- |
| `RECORD_ANOMALY` | 记录本身标识异常：撤稿、重复、标识符冲突 | 异常字段名与值；冲突时附冲突标题与所在索引文件 |
| `SOURCE_ABSENT` | 记录的标识符在任一来源的本地索引中均不存在（来源库未收录） | 逐个来源索引文件的路径、记录数、被查标识符清单 |
| `TIME_WINDOW` | 记录存在于来源索引，但查询时间窗将其截断；移除时间窗后同一查询可命中 | 记录年份、致漏查询的 `date_window`、`query_id` |
| `FIELD_RESTRICTION` | 查询词在放宽字段（any-field）后可命中，在原字段范围（如 title-only）下不可命中 | 原字段范围、放宽后命中的文本片段、`query_id` |
| `VOCAB_GAP` | 记录实际词汇（标题/关键词 token）未被任何查询的检索词覆盖（查询词未覆盖同义表达） | 未覆盖 token 清单、最接近的查询 `query_id` |
| `UNDETERMINED` | 全部探针执行后仍无法定论（兜底，诚实标记，禁止编造类别） | 全部探针的执行记录 |

## 决策树（文本图示）

```
漏检记录 m
│
├─(e) 记录异常探针
│    ├─ retracted / duplicate_of 非空？          → RECORD_ANOMALY（撤稿/重复）
│    ├─ 标识符在某索引存在但标题完全不相交？      → RECORD_ANOMALY（标识符冲突）
│    └─ 否 ↓
│
├─(d) 来源探针
│    ├─ m 的归一化标识符/题录在所有来源索引均找不到？→ SOURCE_ABSENT
│    └─ 找到（定位于来源 S 的索引记录 r）↓
│
├─(c) 时间窗探针（对 S 上每个带时间窗的查询 q）
│    ├─ simulate(q, 原窗)=False 且 simulate(q, 去窗)=True？
│    │                                             → TIME_WINDOW（指针：q.query_id, date_window）
│    └─ 否 ↓
│
├─(b) 字段探针（对 S 上每个查询 q）
│    ├─ simulate(q, 原字段)=False 且 simulate(q, any-field)=True？
│    │                                             → FIELD_RESTRICTION（指针：q.query_id, fields）
│    └─ 否 ↓
│
├─(a) 词汇探针
│    ├─ m 的内容词汇中存在未被任何查询词覆盖的 token？→ VOCAB_GAP（附 token 清单）
│    └─ 否 ↓
│
└─ UNDETERMINED（保留全部探针记录，人工复核）
```

## 本地查询模拟语义

探针与补检共用的可执行布尔语义（`attribute_miss.simulate_query`）：

1. 查询词：`query_string` 小写化、去标点后长度 ≥ 3 的 token 集合；
2. 命中条件：全部查询词出现在被检记录受检字段的拼接文本中；
3. 字段范围：`fields=["title"]` 仅检标题；`["any"]` 检
   标题+摘要+关键词+刊名+作者；
4. 时间窗：`date_window={from,to}` 存在时，记录年份须在闭区间内，否则不命中。

该语义是对本地留存响应文件的确定性复算工具，不模拟任何远程数据库行为。

## 归因到补检的映射

| 主类别 | 定向补检设计 |
| --- | --- |
| `VOCAB_GAP` | 检索式直接取自漏检记录的未覆盖词汇（非同义词臆造），字段 any |
| `FIELD_RESTRICTION` | 沿用致漏查询的检索式，字段放宽为 any |
| `TIME_WINDOW` | 沿用致漏查询的检索式，去除截断边界 |
| `SOURCE_ABSENT` | 切换至案例中存在的另一来源执行 |
| `RECORD_ANOMALY` / `UNDETERMINED` | 不可补检，登记 not_applicable，不强行补检 |

补检零新增命中必须如实报告 `marginal_gain=0`；以同义词改写重跑旧查询而不产生新命中
即宣称遗漏削减，属于反模式，本技能输出中禁止出现。
