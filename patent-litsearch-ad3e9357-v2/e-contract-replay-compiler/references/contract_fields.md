# output_contract 镜像语义与字段写法

（result-contract-replay-compiler 参考文档 · 契约字段）

## 1. 契约镜像语义

`output_contract` 是案例对交付物的硬性字段要求。镜像规则：

1. **逐字段顶层落地**：契约中每个字段名都必须作为 `result.json` 的顶层键出现，不多不少地覆盖契约；额外信息性键允许存在，但不替代契约字段。
2. **未填即 null**：任何没有真实证据支撑的契约字段一律置 `null`，**绝不编造**占位值（如空字符串伪装、虚构号码、"N/A"充当数据）。
3. **null 必须登记**：每个为 null 的契约字段都必须在 `uncertainty` 中有一条以该字段名开头的条目，说明"未填写 + 原因/待办"。这是 V2 校验的强制要求。
4. **防御式提取**：契约可能写作 `{字段名: 描述}`（对象）、`["字段名", ...]`（字符串列表）或 `[{"name": ...}, ...]`（对象列表），且可能嵌在 `task`/`spec`/`requirements`/`case` 之下。提取失败时生成空镜像并发出警告，由人工确认交付要求，而不是凭空假设字段。
5. **骨架保留键**：`case_id`、`status`、`sources`、`uncertainty`、`change_records` 由脚手架直接生成；若契约中也列有 `status`/`sources`/`uncertainty`，骨架值即视为其镜像值（`sources`、`uncertainty` 天然非 null）。
6. **case_id 权威**：`case_id` 只能来自 case.json；fill 文件中的 `case_id` 一律忽略，以防串案。

## 2. status 判定标准

| status | 条件 | 含义 |
| --- | --- | --- |
| `ok` | 所有契约字段均非 null，且有真实证据支撑 | 契约完整交付 |
| `partial` | 至少一个契约字段为 null，且 `uncertainty` ≥ 1 条点名限制 | 诚实部分交付（默认起点） |
| `failed` | 管线无法产生有效结果（如输入损坏、环境失败） | 失败也须交付 result.json 说明原因 |

- 首分钟落地的一定是 `partial`（或 `failed`），随着 `--fill` 合并逐步补齐；只有当**最后一个 null 契约字段被真实数据填充**时才允许升级为 `ok`。
- `status=ok` 与任何 null 契约字段并存 = 过度声明，V3 判 fail。
- `uncertainty` 为空而 `status=partial` = 限制未点名，V3 判 fail。

## 3. uncertainty 写法

- 每条一个限制，**以字段名开头**加冒号，便于校验器与人复核定位，例如：
  - `legal_status: 未填写（脚手架初始化为 null，待补）`
  - `evidence_records: 检索库覆盖不全，2026 年数据可能缺失`
- 字段被 `--fill` 填充后，其名目条目自动移除；手工添加的非字段性限制（如范围声明）会保留。
- 禁止写"基本正确""应该没问题"之类无信息条目。

## 4. change_records 写法

- 每次重写 result.json 追加一条：`{"ts": "<UTC ISO8601>", "note": "<本次改了什么、为什么>"}`。
- note 要能让人重建演变过程：初始脚手架 / 合并哪批 fill / 状态为何升级。
- 任何交付的 result.json 至少有一条记录（V6）。

## 5. sources 写法

每条来源记录至少含：

```json
{"name": "来源名称", "version": "版本或快照标识（可选）", "query_date": "YYYY-MM-DD"}
```

`query_date` 可用 `access_date` 替代（V4）。日期必须是真实查询/访问日期，不得回填估计值。

## 6. 候选与证据定位

- `candidates` 每条候选须携带证据定位符（`evidence` 列表，值为 `来源#段落/权利要求` 形式的可定位标识）。
- 候选的 `evidence` 为空列表意味着"无证据占位"，V5 记 warning——空证据候选不应出现在交付物中。
