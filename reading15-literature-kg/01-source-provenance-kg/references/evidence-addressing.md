# 证据编址规则（evidence addressing）

本技能的核心约定：图谱中**每一个实质性节点与边**都必须能机械回溯到语料原文。

## 1. 地址模型

证据是三元组：

```
(source_id, paragraph_id, quote)
```

- `source_id`：语料来源标识（如 `P1`、`S1`），来自 corpus-manifest.json /
  material.json，归一化后唯一；
- `paragraph_id`：该来源内 JATS 段落地址（如 `P1.p2`）。语料段落必须自带或
  被归一化器确定性编址；
- `quote`：该段落 `text` 字段的**逐字符精确子串**（含空格、单位、标点），
  长度 ≤ 300 字符（短引文）。

## 2. 硬性规则（脚本机械执行）

1. **禁止页码地址**：本任务语料由结构化段落构成，不含 PDF 页码。
   任何对象不得以“第 1 页”“p.1”之类自制页码作为地址；
   更不允许把自造页码伪称为原文页码。
2. **引文必须精确**：`quote in paragraph.text`（Python 子串语义，逐字符）。
   常见违规：凭记忆改写、空格/全半角差异、单位符号（°C）替换、拼接两句。
3. **来源正确**：`source_id` 必须在归一化语料中存在；段落必须属于该来源。
   引文真实存在但挂在错的来源/错的段落上，同属违规（张冠李戴）。
4. **地址唯一**：重复 paragraph id 由归一化器登记进
   `duplicate_paragraph_ids`，此后该地址一律歧义不可用，引用即报错。
5. **根元数据归属**：DOI/title/authors 只属于 primary 来源。
   `kind=paper` 节点的 attributes 必须与其唯一证据来源的 article-meta
   逐字符一致；把 primary 的 DOI 安到 secondary 节点上会被检出。
6. **覆盖度可审计**：验证器统计每个来源被引用的段落比例；
   未被任何证据引用的段落列入 coverage 报告并告警。覆盖度是披露指标，
   不是质量分数——禁止据臆造“置信度”。

## 3. 合并（merge）与不合并（nonmerge）的编址含义

- **merge**（跨论文）：合并后的规范节点必须携带**每个**成员来源的至少一条
  证据；合并的语义上限是“同一概念/方法/材料类别”，绝不断言相同样本、
  相同条件或相同数值。merge 后所有边必须指向规范节点，member 节点仅作
  溯源存根保留（标记 `merged_into`）。
- **nonmerge**（显式判决）：同名/同通用术语而物理对象、模型或数据集不同的
  节点对，必须留下 nonmerge 记录（成员 + reason + 证据）。
  “generic term ≠ same physical object”：
  例：两篇论文都提到 “alumina sample”，若一方声明配方不同、样品不同，
  则样品节点不得合并，且必须显式记录。
- **数值/条件不并入结论**：同名属性不同取值（42 % vs 38 %）、
  同名条件不同参数（1250 °C vs 1350 °C）只能并存或冲突保留，
  绝不合并为单一结论、不取平均。

## 4. 冲突与未报告

- 冲突（conflict）：同一主题下不同来源给出不相容陈述。
  处理方式唯一：`resolution = "preserved"`——两个（或多个）值原样保留在
  各自 claim 节点上，冲突条目只做登记，不做消解。
- 未报告（unreported）：任务关心但来源未提供的信息。登记 topic 与 reason；
  若来源明确声明“未报告”，附该声明的精确引文作为证据。
  未报告不是错误，是诚实披露；禁止用“合理估计”填充。

## 5. 正例与反例

段落原文（P1.p2）：
`... and was then sintered in air at 1250 °C. The dwell time ...`

| 判定 | quote | 说明 |
| --- | --- | --- |
| ✅ | `was then sintered in air at 1250 °C` | 逐字符子串 |
| ❌ | `sintered in air at 1250 C` | 单位符号被改写（缺 °） |
| ❌ | `was then sintered at 1250 °C in air` | 语序改写，非子串 |
| ❌ | `see page 1` | 页码式地址，禁止 |
| ❌ | `sintered in air at 1350 °C` | 引文存在于 S1.p2 而非 P1.p2，张冠李戴 |

## 6. 验证器报错的可读性

verify_evidence.py 的每条 error 均为中文可读语句并定位到具体对象
（如 `node[n_x].evidence[0]: quote 不是 P1/P1.p2 原文的精确子串…`），
修正抽取后重跑即可，无需阅读脚本源码。
