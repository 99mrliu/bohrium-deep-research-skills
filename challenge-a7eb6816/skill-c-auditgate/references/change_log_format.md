# 改动清单（edit_log.jsonl）格式规范

改写/翻译/文体转换过程中，**每一处删改都必须留痕**。改动清单为 JSONL
（每行一个 JSON 对象），供审计门校验合法性、追溯删减。

## 1. 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `locator` | 是 | 定位引用：`S<n>`（源文第 n 句）、`D<n>`（稿第 n 句）、`P<n>`（第 n 段）、`GLOBAL`；可用 `-` 连接两个引用，如 `S3-D2`。句号以 align_map 分句结果（alignment.json）为准 |
| `action` | 是 | `retain`（保留）/ `rephrase`（改写）/ `move`（移动）/ `condense`（压缩）/ `omit`（删除）/ `translate`（翻译） |
| `reason` | 是 | 非空且 ≥ 4 字，说明**为什么**这么改；以「待确认」开头表示存疑 |
| `needs_confirmation` | 否 | `true` 表示该改动需原作者确认，审计时单独汇总 |

## 2. 规则

1. 每处删改一条记录；未改动的关键句建议用 `retain` 显式声明，便于核对覆盖。
2. **删减必须可追溯**：删除或大幅压缩源文中的关键句（含数字/图表引用/
   强度词），必须有 `omit` 或 `condense` 记录且 locator 指向该源句，否则
   审计门判 FAIL。
3. 拿不准的改动不要硬写理由，标 `needs_confirmation: true` 交原作者。
4. 空清单本身可疑：改写必有改动，`omit` 缺失会被覆盖性检查抓住。

## 3. 示例

合法：

```jsonl
{"locator": "S2-D2", "action": "rephrase", "reason": "合并浸出条件与结果，数据原样保留"}
{"locator": "S4", "action": "omit", "reason": "删去浸出渣金属残留率细节以压缩篇幅", "needs_confirmation": true}
{"locator": "S9-D7", "action": "retain", "reason": "结论句基本保留不变"}
```

非法（审计检出）：

```jsonl
{"locator": "S1-D1", "action": "rephrase", "reason": ""}
{"locator": "X9", "action": "omit", "reason": "locator 无法解析"}
{"locator": "S3", "action": "rewrite", "reason": "action 不在允许集合内"}
{"locator": "S5", "action": "omit", "reason": "删了"}
```

对应处理：空 reason / 过短 reason → `bad_reason`；locator 无法解析 →
`bad_locator`；非法 action → `bad_action`；关键源句删减无记录 →
`omit_not_logged`。任一类错误均使 editlog_check 判 FAIL（退出码 4）。
