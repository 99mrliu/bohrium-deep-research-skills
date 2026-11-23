# Rule Identifiers, Priority, and Failure Semantics

每条规则都是显式、可审计的。脚本只在满足“适用条件”时执行；“冲突/失效”时保留原值并进入复核。规则编号是 `change_log.jsonl`、`review_queue.json` 和 `audit_report.md` 的共同索引。

## 0. 全局优先级

1. **真实性与错误**：R-ERR-*、R-ANM-001/002。
2. **输入结构和行身份**：R-INT-*、R-ANM-006。
3. **字段映射保护**：R-FLD-*；冲突列不得覆盖。
4. **值清理**：R-VAL-*、R-NAM-001；只改外观或登记的术语，不补事实。
5. **单位/区间**：R-UNIT-*；未知单位优先于任何推断。
6. **必要字段**：R-ANM-003/004/007/010。
7. **非破坏重复分析**：R-DUP-*，永不删除或合并行。

## 1. Intake and structural rules

| 规则 | 动作 | 适用条件 | 冲突/失效处理 |
|---|---|---|---|
| R-INT-003 | 标记 ragged CSV row | 数据列数与 header 列数不同 | 缺列保持空；额外列进入 `__extra_cell_N`；复核 |
| R-INT-004 | 标记 JSON 无表 | 被引用的 JSON 可读但没有识别的记录表 | 不虚构字段；source 保留，warning |
| R-ERR-001 | 记录运行时异常 | 未预期异常 | 立即写 honest failed/partial result；已有变更不删除 |
| R-ERR-002 | 记录材料解析失败 | JSON/CSV parser 无法解析 | 不信任该材料的行；状态至少 partial，其他材料继续 |

## 2. Encoding and anomaly rules

| 规则 | 动作 | 适用条件 | 冲突/失效处理 |
|---|---|---|---|
| R-ANM-001 | 标记 malformed encoding | strict UTF-8 失败并用 U+FFFD 恢复 | 状态至少 partial；要求重读原始字节/文献 |
| R-ANM-002 | 标记 replacement character | source 或单元格含 U+FFFD | 不猜字符；单元格原样保留并复核 |
| R-ANM-003 | 标记必要字段缺失 | material/name 与 material_id 均空、property_name 空，或 property value 空 | 保持 null；`include_in_statistics=false` |
| R-ANM-004 | 标记无法解析数值 | 非空值不符合登记的标量/区间数字格式 | 原值保留在 raw/text 字段，不给 standard value |
| R-ANM-005 | 标记未知单位 | 单位不在显式字典 | 不转换；`unknown_unit` 复核 |
| R-ANM-006 | 标记空表/空行 | 无 header/记录，或整行均为空/missing token | 空行从 cleaned rows 显式排除，但 raw snapshot 保留 |
| R-ANM-007 | 标记倒置区间 | range min > max | 不交换、不取中点；复核 |
| R-ANM-010 | 标记缺单位 | 数字/区间没有任何单元格、显式文本或 header 单位 | 不猜单位；不给 standard value |

## 3. Field mapping rules

| 规则 | 动作 | 适用条件 | 冲突/失效处理 |
|---|---|---|---|
| R-FLD-002 | 列别名映射 | header 命中 `unit-field-dictionary.md` 中登记的别名 | 只建立映射，不改单元格 |
| R-FLD-003 | 保留未映射列 | header 无安全别名 | 原 cell 进入 `unmapped_fields`；非空时行需复核 |
| R-FLD-004 | 处理重复 header | 原始 CSV 有同名 header | 按 occurrence 生成 `name#2` 等，不覆盖；复核 |
| R-FLD-005 | 防止别名冲突覆盖 | 两个非空列映射到同一 canonical field 且值不同 | 保留先出现值，冲突值进入 `unmapped_fields`；error 复核 |
| R-FLD-006 | 类型化条件提升 | generic property 的属性名和 unit family 同时明确指向 temperature/pressure/time/concentration | 只复制标准值到 typed condition field；不删除 generic property |

## 4. Value and name rules

| 规则 | 动作 | 适用条件 | 冲突/失效处理 |
|---|---|---|---|
| R-VAL-001 | Unicode NFC、去外缘空白和起始 BOM | 单元格外观清理后更安全 | raw snapshot 不变；change log 记录原/新显示值 |
| R-VAL-002 | 合并内部多余空白 | property_name 的显示格式 | 不改术语；仅当未命中同义词时应用 |
| R-VAL-003 | missing token 归 null | `N/A`、`null`、`-`、`未报告` 等登记 token | 不转 0；change log 说明“no value inferred” |
| R-VAL-005 | 区间拆分 | `25–30 °C`、`25-30 °C`、`1 to 2 s`、`1..2 s` 等 | 只输出 min/max；不创建中点；倒置交给 R-ANM-007 |
| R-NAM-001 | 属性同义词归一 | 命中登记的属性同义词，如 `band gap`→`band_gap` | 未登记名称保留原文，不做模糊化学猜测 |

## 5. Unit rules

| 规则 | 动作 | 适用条件 | 冲突/失效处理 |
|---|---|---|---|
| R-UNIT-002 | 单位换算 | 单位在字典中且目标/公式明确 | Decimal 因子换算；原 cell、公式、精度说明进入 change log |
| R-UNIT-007 | 未知单位保护 | 单位未登记或大小写/上下文含糊 | 不换算；标记并复核 |
| R-UNIT-008 | 从值中拆出单位 | 值形如 `1.2 ks`、`25–30 °C` | 显式单位优先于 header default；原始组合值保留 |

单位规则不可通过提示临时扩展。新增单位必须同时更新字典、本参考表、脚本和合成回归示例。`m` 不解释为 molar，避免与 metre 冲突；只有明确大写 `M`、`mM`、`µM/μM` 或 `mol/L` 形式才进入 molarity 规则。

## 6. Duplicate rules（非破坏）

| 规则 | 动作 | 判定键 | 禁止事项 |
|---|---|---|---|
| R-DUP-001 | 精确重复候选 | 完整 raw cells（含 header occurrence）SHA256 相同 | 不删除、不选择 master |
| R-DUP-002 | 重复抽取候选 | 材料 ID（优先）/材料名 + 属性 + 标准值/区间 + 标准单位 + 文献引用相同，且实验上下文相同 | 不合并值，不平均，不隐藏任何行 |
| R-DUP-003 | 核心相同但上下文冲突 | 核心测量键相同，但实验 ID、温度、压力、时间、浓度或条件文本不同 | 明确标记 `same_core_different_context`；除非有人工证据，不得合并 |

`duplicate_group_id` 是复核索引，不是合并后的实体 ID。所有候选行的 `row_id`、原始指纹和来源定位继续有效。

## 7. Review queue 生成

所有 `review_required=true` 的 anomaly 都进入 `review_queue.json`，获得稳定 `Q#####` 编号。建议动作只说明人工接管点，不自动执行。例如 unknown unit 建议确认单位定义，duplicate 建议比较来源上下文，missing value 建议查原文；若原文未报告则继续保留 null。
