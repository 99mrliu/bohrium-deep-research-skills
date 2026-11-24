# 状态分类法：success / partial / unable_to_determine / refused

## 1. 定义

- **success**：output_contract 指定的每个字段均已填写为真实值（无 "__pending__" 占位、无缺失），登记的 artifact 全部存在且非空，uncertainty 中不存在足以推翻结论的未决事项。success 是对契约的完整满足，而非对内容质量的自我表扬。
- **partial**：流水线实际运行并产出了部分成果，但契约未被完整满足，或关键不确定性未消解。partial 必须附带精确的 partial_reason：完成了什么、缺什么、为何缺（如"材料 B 缺失，对应分支以占位标注"）。笼统的"时间不够"不合格；须指明受影响的契约字段。
- **unable_to_determine**：因输入缺失或损坏（如 case.json 不可解析、全部材料不可用）而无法开展实质工作，连部分结论都无法给出。此时 result.json 仍须合法写出，uncertainty 说明无法确定的原因。
- **refused**：任务本身不应被执行（违反政策、越权、要求伪造数据等）。result.json 写明拒绝理由，不生成任何内容产物。

## 2. 允许的转移

```
(初始) → partial                    # boot 完成即处于 partial
partial → success                   # 仅当零占位、零契约违例（checkpoint 强制校验）
partial → partial                   # 任意次自我更新（推荐路径）
partial → unable_to_determine       # 运行中发现输入根本性不可用
partial → refused                   # 运行中发现任务不应执行
unable_to_determine → partial       # 输入被修复/补齐后重新引导（重跑场景）
任意 → partial                      # success 请求被拒绝时的强制回退
```

不允许的转移：success → partial 之外的任意"降级后伪装升级"（重跑须重新经历 partial → success 校验）；任何状态直接跳到 success 而不经占位检查。

## 3. 各状态的必备伴随字段

| 状态 | 必备字段 |
| --- | --- |
| success | 全部契约字段为实值；artifacts 非空（契约含文件产物时）；sources 非空；partial_reason 不存在 |
| partial | partial_reason 非空且精确；占位字段保持 "__pending__"（禁止伪造实值）；uncertainty 列出全部未决事项 |
| unable_to_determine | case_id 尽力填写（无法获取时 "unknown"）；uncertainty 至少一条说明原因；sources 可为空 |
| refused | uncertainty 或专门说明字段给出拒绝理由；不登记任何内容 artifact |

## 4. 反模式（禁止）

- 为通过审计而把占位值 "__pending__" 改写为无意义字符串（如 "done"、"见文件"）——审计无法识别语义造假，但复核会识别，且违反诚实原则；
- 将未读材料列入 sources 以充数；
- 删除仍有意义的 uncertainty 条目以求"干净"；条目只应在确实消解后以 --resolve-uncertainty 移除；
- 预算充足时提前宣布 success 而跳过 final_audit；对账通过是 success 的必要条件。
