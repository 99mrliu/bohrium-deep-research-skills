# 模型产物 schema — adjudication.json 与 extractions.json

模型在整个流程中只写这两个小 JSON（放在工作目录 /app/work）。
两者都必须 UTF-8、无时间戳；证据只用段落 ID（无页码）。

## 1. adjudication.json（身份裁决，必需）

```json
{
  "decisions": [
    {"pair_id": "P16",
     "decision": "nonmerge",
     "reason": "TiO2 in S1 is the compact ETL; in S2 a mesoporous scaffold — different physical samples.",
     "evidence": ["s1-p03", "s2-p03"]}
  ]
}
```

校验规则（adjudicate.py 机械执行，违反即隔离该条并保守默认 nonmerge）：

- `pair_id` 必须存在于 candidates.json；不允许重复裁决同一对；
- `decision` ∈ {`merge`, `nonmerge`}；
- `reason` 必填非空（一行即可）；
- `evidence` 为 0..n 个**存在的** paragraph_id。

只裁决你能判断的对；其余留空会自动进入保守默认（nonmerge，
decision_source="default-conservative"）。trap=true 的对务必裁决并写清理由。

## 2. extractions.json（事实抽取，必需）

```json
{
  "nodes": [{"surface": "MAPbI3", "type": "material",
             "source_id": "S2", "paragraph_id": "s2-p03",
             "quote": "MAPbI3 films were prepared by sequential deposition"}],
  "edges": [{"subject": "MAPbI3", "object": "spiro-OMeTAD",
             "relation": "uses", "source_id": "S1", "paragraph_id": "s1-p04",
             "quote": "...", "qualifiers": {"role": "hole transport layer"}}],
  "claims": [{"entity": "MAPbI3", "metric": "PCE", "value": 21.1, "unit": "%",
              "conditions": ["1-sun AM1.5G illumination", "initial scan"],
              "source_id": "S1", "paragraph_id": "s1-p01", "quote": "..."}],
  "unreported": [{"item": "hysteresis index", "reason": "not measured",
                  "source_id": "S1", "paragraph_id": "s1-p08", "quote": "..."}],
  "notes": ["..."]
}
```

规则：

- `quote` 必须是所引段落文本的**精确子串**（大小写、空格敏感；verify.py 会
  机械核对，不符即失败）。请从原文复制，不要凭记忆改写。
- `subject` / `object` / `entity` 用**论文中的表面形式**；解析按
  (归一键, source_id) 落到规范实体——同一表面在不同论文会解析到不同实体，
  这正是同名异物保护。`nodes[].type` 供类型标注（material/metric/method/
  condition/process/…），缺省时按 references/identity_model.md 的规则猜。
- `relation` 建议使用封闭词表：uses、measures、improves、suppresses、
  decomposes-into（系统内部另有 concerns、conflicts-with、aliases）。词表外
  关系会被记 warning 但仍保留。
- `claims`：数值声明必须带 metric + conditions（条件写全：辐照、老化时长、
  温湿度、封装状态）。**不要**把不同条件的数值平均或合并——冲突由脚本登记
  保留。value 用 JSON 数字。
- `unreported`：文中明确说"未测/未报告"的项。
- `notes`：综述转述、推测句等"看见了但不抽"的判断说明（进 evidence_notes）。

## 3. 体积预算

两个文件合计应 < 8KB（本示例约 6KB）。段落级地址 + 短 quote，不要整段照抄。
