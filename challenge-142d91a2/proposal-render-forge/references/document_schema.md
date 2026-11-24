# 开题文档 JSON Schema（proposal-render-forge 单一事实源）

本文件定义开题报告的结构化 JSON 表示。所有下游交付物（Markdown / SVG / HTML /
修订对照报告）都由该 JSON **确定性渲染**而来；任何内容修改必须先改 JSON，
再重跑渲染脚本，禁止直接手改渲染产物。

## 1. 顶层结构

```json
{
  "meta":     { ... },        // 文档元信息（必填）
  "sections": [ ... ],        // 七要素章节数组（必填，恰好 7 项）
  "sources":  [ ... ],        // 引用来源数组（必填，可为空数组）
  "revision": [ ... ]         // 修改记录数组（必填，初稿至少含一条 create 记录）
}
```

## 2. meta 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 开题题目 |
| `discipline` | string | 学科方向 |
| `degree` | string | 学位层次（如「博士研究生」） |
| `author` / `advisor` | string | 申请人 / 导师 |
| `period.start` / `period.end` | string | 研究周期起止（YYYY-MM） |
| `period.quarters` | int | 周期总季度数（甘特图横轴长度） |
| `budget_wan` | number | 经费预算（万元） |
| `version` | string | 版本号（如 v1、v2），渲染进页眉 |
| `date` | string | 本版本日期（YYYY-MM-DD），渲染进页眉 |

渲染脚本**不读取系统时钟**，页眉日期一律取自 `meta.date`，这是字节级确定性的前提。

## 3. sections 数组（七要素，固定编号 1–7）

每节对象：

```json
{
  "number": 1,                       // int，必须恰好为 1..7 连续不重
  "id": "background_gap",            // 固定 id 集合，见下表
  "title": "研究背景与缺口",
  "paragraphs": ["段落一……[S1]", "段落二……"],   // 非空字符串数组
  "table": {                          // 可选；不需要表格的节省略该键
    "caption": "表 1 ……",
    "headers": ["列1", "列2"],
    "rows": [["...", "..."]]
  }
}
```

| number | id | 标题（建议） | 内容要点 |
|---|---|---|---|
| 1 | `background_gap` | 研究背景与缺口 | 背景、现状、缺口三段式 |
| 2 | `problem_definition` | 问题定义 | 输入/输出/形式化/评价基线 |
| 3 | `objectives` | 研究目标 | 可考核目标，指标阈值须给出依据 |
| 4 | `technical_route` | 技术路线 | 分层路线，可选对比表格 |
| 5 | `schedule` | 阶段计划 | **必须含表格**，供甘特渲染 |
| 6 | `risks` | 风险与备选 | 每项风险含触发信号与备选方案 |
| 7 | `outcomes` | 预期成果 | 论文/数据/系统/专报等 |

### 3.1 schedule 节表格的硬性约定

甘特图直接解析该表，表头必须为：

```
["编号", "任务", "开始季度", "结束季度", "交付物"]
```

- `开始季度`/`结束季度` 为整数（JSON number），满足 `1 ≤ 起 ≤ 止 ≤ period.quarters`；
- 渲染 Markdown 时该表照原样输出为 GFM 表格，渲染预览时同一数据转为横向甘特条——
  单一事实源，不允许在别处重复维护一份计划数据。

### 3.2 来源标注

段落中以 `[S#]` 行内标注引用（如 `……分钟级滚动预警 [S5]`），`#` 对应 `sources`
数组中条目的 `id`。渲染时原样保留，文末依据 `sources` 自动生成来源清单。

## 4. sources 数组

```json
{"id": "S1", "authors": "……", "title": "……", "venue": "……",
 "year": 2024, "url": "https://…", "note": "可选备注（如合成示例声明）"}
```

`url` 与 `note` 可省略；`note` 存在时会渲染进来源清单（用于标注合成文献、
预印本状态等诚实性信息）。

## 5. revision 数组（修改记录）

```json
{"date": "2026-12-05", "section": 3, "op": "rewrite", "reason": "导师意见：……"}
```

- `section`：被修改的章节编号（1–7），全文级操作用 0；
- `op`：`create`（新建）/ `add`（新增内容）/ `delete`（删除）/ `rewrite`（改写）；
- `reason`：修改理由（导师意见、评审意见、数据更新等）。

`diff_ledger.py revisions` 把该数组渲染为修改记录表；
`diff_ledger.py diff` 则基于两个版本 JSON 的**实际内容**逐节对照——
两者互为印证：revision 是「声明的修改史」，diff 是「可机器复核的修改史」。

## 6. 校验规则（render_markdown.py 启动时强制执行，失败即拦截）

1. `meta` 必备字段齐全（见第 2 节）；
2. `sections` 恰好 7 项，`number` 恰好为 1..7 连续不重，`id` 属于固定集合；
3. 每节 `paragraphs` 为非空数组且元素为非空字符串；
4. schedule 节必须含 `table`，且表头符合第 3.1 节约定，季度区间合法；
5. 段落中出现的 `[S#]` 必须能在 `sources` 中找到对应 `id`（防悬挂引用）。

## 7. 字数统计口径（render_preview.py 使用）

节字数 = 该节全部 `paragraphs` 文本去除空白字符后的字符数（CJK 与 ASCII
混排统一按字符计），不含表格单元格。该口径写入预览卡片页脚，供快速核对
各节篇幅是否均衡。
