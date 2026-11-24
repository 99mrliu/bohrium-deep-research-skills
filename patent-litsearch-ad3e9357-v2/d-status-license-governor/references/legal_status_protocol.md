# 法律状态核验协议（登记优先 / register-first）

> 本文件是 `legal-status-license-governor` 技能的协议正文。所有示例均为合成示例 / 虚构。

## 1. 状态来源层级（source hierarchy）

| 层级（tier） | 定义 | 可支撑的法律状态断言 |
|---|---|---|
| `register` | 官方专利登记簿/注册簿（如国家知识产权局登记簿） | 任意枚举值（granted/expired/withdrawn/rejected/pending/unknown） |
| `official_gazette` | 官方公报（授权公告、失效公告等） | 任意枚举值 |
| `aggregation` | 聚合检索页/题录数据库 | **只能**支撑 `unknown`（未核验）声明 |
| `repost` | 转载页、博客、新闻转述 | **只能**支撑 `unknown`（未核验）声明 |
| `unknown` | 层级未登记/无法判定 | **只能**支撑 `unknown`（未核验）声明 |

**严禁把转载页、聚合页当作登记依据引用**（规则 S1）。聚合页可以用于发现线索，但状态结论必须回溯到登记簿或公报；回溯失败时结论就是 `unknown`。

## 2. 状态枚举

`{granted, expired, withdrawn, rejected, pending, unknown}`（规则 S4）。
**`unknown` 是一等公民**：它表示「截至 query_date，未能在登记级来源核验」，是合法且受尊重的诚实结论，不是任务失败。评测材料通常无法支撑当前官方状态核验，此时正确输出就是 `unknown` + 查询日期 + 滞后声明。

## 3. 查询日期与滞后声明

- 每条断言**必须**携带 `query_date`（规则 S2）：状态是「某日查询所得」，不是永恒事实。
- `query_date` 距今超过 90 天 → 警告「状态可能滞后」（规则 S3，不判失败），交付时必须在 `legal_status` 与 `uncertainty` 中附加滞后声明。
- `status_effective_date` 必须是 ISO `YYYY-MM-DD` 或显式 `null`（规则 S6）；材料没给就写 `null`，禁止编造。

## 4. 状态冲突处置

同一 `patent_ref` 出现互相矛盾的状态断言时（规则 S5）：

1. **双保留**：双方断言连同来源、层级、查询日期全部保留进 `conflicts` 块，不得删除任何一方；
2. **登记级优先**：头条状态（headline）取层级更高者，优先级 `register` > `official_gazette` > `aggregation` > `repost` > `unknown`；同层级取较新 `query_date`；
3. **披露**：`conflict_disclosed=true`，并在 `uncertainty` 中说明冲突双方与采纳理由；
4. 冲突本身不判治理违规（退出码不因此为 1），但**不披露冲突**属于治理失败。

## 5. 标准措辞模板

- 已核验（登记级）：「官方登记显示<状态>（登记来源：<source_id>，查询日期：YYYY-MM-DD）。状态可能滞后，请以最新官方登记为准。」
- 未核验：「官方登记未核验（查询日期：YYYY-MM-DD）。」
- 仅有聚合/转载线索：「仅见聚合/转载页线索，未回溯到官方登记，状态记为 unknown（查询日期：YYYY-MM-DD）。」
- 冲突披露：「来源 A（register）称 <status1>，来源 B（official_gazette）称 <status2>；按登记优先协议以 A 为头条状态，冲突已披露。」
- 红级来源：「该来源存在但无法访问（付费/登录受限），未使用其内容。」

**禁止**：对未核验专利使用「有效专利」「已失效」「仍受保护」「可以自由实施」等确定性措辞；任何情况下不得输出自由实施（FTO）或侵权结论——超出本技能范围，由 `wording_guard.py` 强制拦截。

## 6. 台账格式（status.jsonl）

每行一个 JSON 对象：

```json
{"patent_ref": "CN-FICT-100001A", "asserted_status": "granted", "status_effective_date": "2023-06-15", "source_id": "REG-CNIPA-FICT", "query_date": "2026-11-20", "note": "合成示例/虚构"}
```

校验：`python3 scripts/status_ledger.py validate --ledger status.jsonl --sources sources.json`，规则 S1–S6 见脚本 docstring。
