# 来源优先级与冲突裁定规则（source priority rules）

## 四级来源

| 级别 | source_kind | 证据形式 | locator | confidence |
|---|---|---|---|---|
| L1 | sidecar_table | 伴随表（csv/tsv）中含"文件列"的行内单元格 | `<伴随表>#L<行号>` | 0.95 |
| L1 | sidecar_json | 伴随 JSON（{文件名:{字段:值}} 或 [{file:...}]） | `<伴随JSON>#record:<文件键>` | 0.95 |
| L1 | admin_note | 行政备注 txt/md 中的 `键：值` 行（仅安全字段，全局默认） | `<备注文件>#L<行号>` | 0.80 |
| L2 | content_head | 文本类文件首部 4KB 内模式命中（项目号：/Project:/仪器/Instrument/作者：/年度：） | `<文件自身>#L<行号>` | 0.85 |
| L3 | name_pattern | 文件名正则（pattern_id 见 naming_patterns.md） | `<文件相对路径>`（pattern_id 单列） | 0.60 |
| L4 | manual_override | work/metadata_overrides.json 人工/模型裁定 | `metadata_overrides_snapshot.json#<文件>/<字段>` | 0.99 |

## 伴随来源识别（防止误吞）

- csv/tsv：首行含"文件列"（file/filename/filepath/path/文件/文件名/文件路径 之一）才视为伴随元数据表；无文件列的普通数据表不抽取。文件列取值按 NFC 先匹配相对路径、再唯一匹配 basename。
- txt/md：**仅当文件名带 行政/备注/admin 特征**时才作为全局行政备注来源；普通正文文件里的"作者："等行只通过 L2 作为该文件自身的证据。
- 全局备注只接受 GLOBAL_NOTE_FIELDS（见 field_dictionary.md），且只下发给已有至少一条文件级证据的文件。

## Winner 裁定

1. 存在 L4 候选 → L4 胜（resolution=`l4_override`）。L4 是带理由的人工裁决，显式优先于一切自动来源；理由字符串为空时仍采信但在 note 标注。
2. 否则级别低数字优先：L1 > L2 > L3（resolution=`level_priority`）。
3. 同级 tie-break：sidecar 随行记录 > 全局行政备注；L2 行号小者优先；L3 按 pattern 定义次序。

## 冲突矩阵（conflicts.json）

- 触发条件：同文件同字段存在 ≥2 个**不同值**候选。值相同的重复证据不进矩阵（winner note 记"共N条候选"）。
- 每条记录：file、field、winner（完整 registry 行）、resolution、**candidates 全量**（含落选者及其 locator/level/confidence）、note。
- 冲突不会因规则裁定而"消失"：矩阵是永久留痕，供评审与 L4 裁定参考。

## 校验回查（verify_registry.py 对应逻辑）

- L1/L2 `#L行号`：重读源文件该行，值必须是该行的子串。
- L1 `#record:键`：重读源文件全文，文件键与值都必须出现。
- L3：用内嵌同名 pattern 对 basename 重跑，捕获值（或固定值）须与登记值完全一致。
- L4：output/metadata_overrides_snapshot.json 中该文件该字段的值须一致且 reason 非空。
- 任何一条不符 → 该项 FAIL，audit overall=FAIL，finalize 不得报 complete。
