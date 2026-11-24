# 趋势主张文件 schema（claims.json）

claim_audit.py 的输入：一个 JSON **列表**，每个元素是一条待审计的趋势主张。
该文件应在趋势章节**定稿前**从草稿中提取生成（每条报告里的趋势句一条主张）。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `claim_id` | string | 是 | 唯一标识，建议可追溯到报告段落（如 `sec2-p3-c1`） |
| `kind` | string | 是 | `trend` \| `changepoint` \| `fluctuation` \| `decline` |
| `year` | int | 二选一 | 单年主张（changepoint/fluctuation/单年 decline 用） |
| `year_range` | [int, int] | 二选一 | 区间主张（trend/decline 用），闭区间 |
| `direction` | string | 是 | `up` \| `down` \| `stable`（stable 仅 trend 有意义） |
| `significance` | string | 是 | `claimed`（报告写了“显著”） \| `not_claimed` |
| `statement` | string | 是 | 报告中的原句（便于回链与人工复核） |

## 审计规则与违规码

| 违规码 | 触发条件 | 含义与处置 |
|---|---|---|
| `censored_year_as_decline` | decline/trend-down 主张的 year 或 year_range 终点落在 `partial_year_suspect` 的末段 | 右删失年份的计数是数据截取伪象，不能作衰退证据。必须删除该主张或改用未删失区间的证据 |
| `unsupported_changepoint` | changepoint 主张的 τ 不在 supported 候选中（rate-ratio CI 未排除 1），且 `significance=claimed` | “显著变点”字样必须有 CI 排除 1 的支撑；否则删“显著”或换 τ |
| `fluctuation_as_inflection` | changepoint 主张的 τ 是波动清单中的单年（\|z\|≥2）且无 supported 候选支持 | 把泊松噪声尖峰当真实拐点；应改写为波动描述（kind=fluctuation, significance=not_claimed） |
| `direction_mismatch` | trend/decline 的主张方向与半数分段重算速率比矛盾，且 CI 排除 1（统计上可区分） | 方向与计数相反，必须改写方向或删除主张 |

补充规则：

- 与 (b) 同条件但 `significance=not_claimed` ⇒ **downgraded**（探索性表述，非违规）。
- trend 主张方向与点估计不符但 CI 跨 1（功效不足）⇒ **downgraded**。
- 主张 stable 但重算 CI 排除 1 ⇒ `direction_mismatch`（stable 也是一种方向主张）。
- 主张落在右删失末段区间内的 trend/decline，审计时**剔除末段**再重算（evidence 中注明 trimmed）。
- 全部一致 ⇒ **ok**，evidence 回显支撑数字（counts、CI、rate_ratio、ll_gain、z 等）。

## 输出与退出码

`<work>/claim_audit.json`：

```json
{
  "claims_file": "claims_bad.json",
  "n_claims": 4,
  "summary": {"ok": 0, "violation": 4, "downgraded": 0},
  "verdicts": [
    {"claim_id": "...", "kind": "...", "statement": "...",
     "verdict": "ok|violation|downgraded",
     "violations": ["..."],
     "evidence": {"...": "重算支撑数字"}}
  ]
}
```

退出码：任一 `violation` ⇒ **1**（流水线必须停下来修主张，禁止绕过）；否则 **0**。

## 最小示例

```json
[
  {"claim_id": "c1", "kind": "changepoint", "year": 2018,
   "direction": "up", "significance": "claimed",
   "statement": "2018年前后出现显著上升变点。"}
]
```
