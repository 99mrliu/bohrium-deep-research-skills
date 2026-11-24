# PRISMA 计数对账协议（counts reconciliation）

## 1. PRISMA 2020 流程计数语义

PRISMA 2020 流程图把文献流向拆为三段，本 skill 用 flow.json 的七个字段承载：

| flow.json 字段 | PRISMA 2020 对应框 | 语义 |
|---|---|---|
| identified | 识别：数据库检索得到记录数 | 去重前的题录总数 |
| duplicates_removed | 识别：去重移除记录数 | 重复题录条数 |
| screened | 筛选：题录/摘要筛检记录数 | 进入题录级筛选的条数 |
| excluded_title_abstract | 筛选：题录级排除（按理由） | 理由码 → 篇数 |
| fulltext_assessed | 筛选：全文评估资格数 | 进入全文级筛选的条数 |
| excluded_fulltext | 筛选：全文级排除（按理由） | 理由码 → 篇数 |
| included | 纳入：最终纳入研究数 | 进入质量评价与综合的篇数 |

## 2. 轧账公式（reconcile.py 的规则码）

- **F1** `identified - duplicates_removed = screened`
- **F2** `screened = Σ excluded_title_abstract + fulltext_assessed`
- **F3** `fulltext_assessed = Σ excluded_fulltext + included`
- **F4** 各阶段排除理由计数和 = 该阶段排除总数（声明 `excluded_*_total` 时强校验）
- **F5** 若提供 decisions jsonl，逐阶段实际计数必须与 flow.json 声明值一致

任何一条不平衡，reconcile.py exit 3 并输出失衡环节与差值，例如：
`F2: screened=100 但 excluded_ta(85)+fulltext(13)=98, diff=2`

## 3. 常见漏记与双计（F 码失衡的典型根因）

1. **重复排除双计（F2 偏多）**：同一篇题录在两个理由下各计一次。纪律：一篇只记
   **一个主排除理由**，按条款优先级取首个命中（如"研究类型不符"优先于"人群不符"）。
2. **全文不可得未计入（F3 偏少）**：拿不到全文的记录从流程里"消失"。纪律：全文
   不可得必须作为全文级排除理由计入 `excluded_fulltext`（如 `"全文不可得": n`），
   不得静默丢弃。
3. **去重数漏记或多记（F1 失衡）**：手工去重后未更新 duplicates_removed；或同一
   重复对被多个库各算一次。纪律：duplicates_removed 由去重脚本输出，禁止手填。
4. **理由计数与篇数混用（F4 失衡）**：把"理由出现次数"当"排除篇数"。一篇多理由时
   两者必然不等，必须先确定主理由再计数。
5. **题录级通过数与全文级评估数不一致（F2/F5-ta-passed）**：筛选途中放宽纳排标准
   导致有人"补进"题录。纪律：纳排标准改动必须版本化并 runlog 登记（actor=human）。

## 4. 失衡排查顺序（reconcile exit 3 时按此执行）

1. **先查 F4**：各阶段理由计数和是否等于阶段排除总数 → 定位"漏记理由/双计理由"；
2. **再查 F2**：题录级是否双计或放宽标准补录 → 对照 decisions.jsonl 逐条核（F5）；
3. **再查 F1**：duplicates_removed 是否与去重脚本输出一致；
4. 修正后重跑 reconcile，直至 exit 0 再进入下一环节。

## 5. flow.json 写法

```json
{
  "identified": 8,
  "duplicates_removed": 2,
  "screened": 6,
  "excluded_title_abstract": {"非随机对照试验": 1, "人群不符": 1},
  "fulltext_assessed": 4,
  "excluded_fulltext": {"全文不可得": 1},
  "included": 3
}
```

- 数值字段必须是非负整数；理由字典的值之和即该阶段排除总数；
- 可选 `excluded_title_abstract_total` / `excluded_fulltext_total` 声明阶段排除总数
  以启用 F4 强校验；
- flow.json 应由冻结脚本从真实产物计算生成（见 examples/pipeline/step3_freeze.py），
  只允许在人工干预纪律下编辑并重新登记；
- decisions jsonl 每行一条：`{"record_id","stage":"ta"|"ft","decision":"include"|"exclude","reason"}`，
  exclude 必须给 reason，且 reason 必须与 flow.json 的理由码用词一致。

合规完整示例见 `examples/flow.json`；埋雷负例（F2 失衡 100 vs 98）见
`examples/negative/flow_broken.json`。
