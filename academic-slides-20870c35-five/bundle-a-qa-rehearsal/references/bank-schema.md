# 数据契约（bank-schema）

qa_seed.py 与 qa_gate.py 消费的四个 JSON 文件的字段契约。
所有文件 UTF-8、单个 JSON 根对象。标注 ▲ 的字段被门控机械引用。

## 1. claims.json（Phase 1 产物）

```json
{"claims": [ { ...claim card... } ]}
```

每张 claim card：

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` ▲ | string | 是 | 唯一，如 `C-01`；题库的 `claim_ids` 引用它（G2） |
| `statement` | string | 是 | 一句话主张，回答的"重述主张"不得超出它 |
| `kind` | string | 是 | question / method / result / comparison / limitation 等 |
| `strength` ▲ | string | 是 | `established` / `preliminary` / `contextual`；弱强度触发 G4 措辞检查 |
| `locator` | object | 是 | `file` / `section` / `exhibit`（可加 `pdf_page` / `printed_page`） |
| `anchor` ▲ | string[] | 可（缺省 `[]`） | 逐字数字锚点，含单位，如 `"12.7%"`、`"n=48"`、`"25 °C"`；G3 的比较基准 |
| `limitations` | string[] | 可（缺省 `[]`） | 每条 limitation 会被 qa_seed.py 播成一道 limitation 题（R1） |
| `slide` | string | 建议 | 该 claim 所在正片页 id，播种时作为建议 primary_slide |

anchor 书写规则：一个 anchor 只含一个数字（可加 `n=` 前缀）加单位，
如 `"0.42 mL/min"`；单位用 NFKC 规范形（`℃` 写成 `°C`）。

## 2. audience.json（Phase 2 产物）

```json
{"audience": {"role": "...", "decision_goal": "...", "prior_knowledge": "...",
              "objections": [ { ... } ]}}
```

`objections`（也可放顶层 `objections`）每条：

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` ▲ | string | 是 | 如 `OB-1`；G5 要求每个 id 被题库的 `objection_ref` 覆盖 |
| `category` | string | 建议 | mechanism / data / comparison / limitation；播种时作为题类别（缺省 data） |
| `text` | string | 是 | 质疑原文，播种时直接成为题目 |
| `likely_claim_ids` | string[] | 可 | 预判被攻击的 claim，播种时挂接 |

## 3. deck_plan.json（Phase 2 产物）

```json
{"slides": [ {"id": "S-01", "message": "...", "role": "...", "time_s": 90,
              "backup": false, "exhibits": [...]} ]}
```

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` ▲ | string | 是 | 唯一；题库的 `primary_slide` / `backup_slides` 引用它（G2） |
| `backup` ▲ | bool | 可（缺省 false） | 备用页必须显式 `true`；G2 要求 backup_slides 只指向 `backup:true` 的页 |
| `message` | string | 是 | 该页唯一主张（Phase 2 纪律） |
| `role` / `time_s` / `exhibits` | — | 建议 | 叙事角色 / 时间片 / 图表绑定，供 storyboard 治理 |

## 4. qa_bank.json（Phase Q 产物，被门控）

```json
{"questions": [ { ... } ]}
```

每题：

| 字段 | 类型 | 必需 | 门控 |
|---|---|---|---|
| `id` | string | 是 | 违例报码时引用 |
| `category` ▲ | string | 是 | G1：mechanism/data/comparison/limitation 各 ≥1 题 |
| `question` | string | 是 | 追问原文 |
| `claim_ids` ▲ | string[] | 可（缺省 `[]`） | G2 须存在于 claims.json；G3/G4 的作用范围 |
| `objection_ref` ▲ | string | 可（缺省 `""`） | G5：audience 每个 objection 须被 ≥1 题引用 |
| `primary_slide` ▲ | string | 是 | G2 须存在于 deck_plan |
| `backup_slides` ▲ | string[] | 可（缺省 `[]`） | G2 每条须存在且 `backup:true` |
| `answer_points` ▲ | string[] | 是 | G2 ≥2 条非空；G3 数字口径；G4 强度措辞 |

## 5. 退出码语义（两脚本一致）

| 退出码 | qa_seed.py | qa_gate.py |
|---|---|---|
| 0 | 播种成功 | G1–G5 全部通过 |
| 1 | （不使用） | 存在门控违例，stdout 逐行 `G编号: 细节` |
| 2 | 用法/IO/schema 错误 | 用法/IO/schema 错误（文件缺失、JSON 损坏、结构不符本契约） |

schema 错误（exit 2）与门控违例（exit 1）的分界：结构不合法导致无法
判定的是 schema 错误（如 questions 不是数组、缺 id）；结构合法但内容
不达标的是门控违例（如 answer_points 只有 1 条）。
