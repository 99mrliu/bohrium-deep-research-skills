# 关系记录 Schema 与受控词表

## 1. 设计立场

本 Skill 的中心不是“通用三元组”，而是**关系语义、方向、认识状态与条件作用域**。
一条关系记录必须回答四个问题：什么关系（类型与方向）、谁在说（author voice）、
在什么条件下成立（条件作用域）、证据在哪里（source_id + JATS paragraph_id +
逐字短引）。跨篇共现**不是**直接关系，背景转述**不是**一手证据。

## 2. 受控关系词表（允许案例任务扩展）

| relation | 含义 | 方向 | 必备约束 |
|-|-|-|-|
| `uses` | 使用（样本/方法/数据集/工具） | subject→object | 条件缺失→partial |
| `evaluates` | 在某任务/数据集上评估 | 评估者→对象 | 建议带 dataset/task |
| `reports` | 报告某事实（非比较） | 主体→客体 | — |
| `derives_from` | 派生自（蒸馏/微调/改造） | 派生物→来源 | — |
| `compares_with` | 与……比较（无方向结论） | 双向语义 | 必须 metric/basis + comparator |
| `outperforms` | 优于（有方向） | 优者→劣者 | 必须 metric/basis + comparator；禁止全局赢家 |
| `supports` | 证据支持某说法 | 证据方→说法方 | — |
| `contradicts` | 证据与某说法冲突 | 证据方→说法方 | 触发冲突检测 |
| `measured_on` | 在……上测得 | 被测对象→数据集/任务 | measurement 必须带 unit + 条件 |
| `cites_background` | 背景转述（引用他人结果） | 转述对象→被引内容 | 永远不得 used_as_primary_evidence=true |

案例任务可在 relations.json 顶层 `"extensions": ["新关系名", ...]` 扩展词表；
校验器把扩展并入受控词表并在 audit 中记录，**不允许静默使用未声明的新类型**。

## 3. 关系记录字段

```json
{
  "edge_id": "e1",                      // 必填，稳定编号
  "relation": "outperforms",            // 必填，受控词表∪extensions
  "subject": "n_transA",                // 必填，节点 id
  "object": "n_transB",                 // 必填，节点 id
  "voice": "primary-results",           // 必填，见 voice-conditions.md
  "polarity": "positive",               // positive/negative/neutral
  "conditions": {"dataset": "n_lowmt", "metric": "n_bleu",
                 "condition": "n_lowres", "sample": "...", "model_config": "..."},
  "comparator": "n_transB",             // 比较型必填
  "basis": "...",                       // 无标准 metric 时的比较依据（可替代 metric）
  "measurement": {"kind": "margin", "value": 2.6, "unit": "BLEU"},
  "used_as_primary_evidence": true,
  "status": "asserted",                 // asserted/partial/uncertain/rejected
  "evidence": [{"source_id": "SYN-P1", "paragraph_id": "SYN-P1.s3.p2",
                "quote": "逐字短引（≤一句话）"}]
}
```

## 4. 硬性规则（校验器强制执行）

- **R5 逐字短引**：quote 必须在对应 JATS 段落原文中逐字命中
  （NFKC 归一、弯引号/破折号直化、折叠空白后的子串匹配）。定位只用
  组织方 JATS paragraph_id，**禁止 PDF 页码**。
- **R6 比较必须有依据**：`outperforms`/`compares_with` 必须有
  `conditions.metric`（或 `basis`）和 `comparator`；缺一则拒绝，
  不得写成“全局更优”。
- **R7 数值必须带条件**：`measurement.value` 必须有 `unit`，且
  `conditions` 至少含一个作用域键（sample/model_config/dataset/metric/
  condition/task）；否则 linter 把数值降级为 `unscoped_value_note`，
  数值不入图（禁止全局数值）。
- **R8 背景转述不得当一手证据**：voice=`cited-background` 且
  `used_as_primary_evidence=true` 直接拒绝。

## 5. 节点记录

`node_id`、`type`（model/dataset/metric/condition/task/method/material/
researcher/claim 等）、`label`、`aliases`、`evidence`（同边证据结构）。
跨篇合并/不合并决定写入 `merge_decisions.json`，含显式依据与证据；
同名不同对象（如 TransB vs TransB-ft）禁止合并。
