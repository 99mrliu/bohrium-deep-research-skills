---
name: lineage-guardian
description: 文献抽取数据的上游真实性、文件完整性、字段/单位标准化与行级来源谱系守护；适用于 CSV/TSV/嵌套 JSON 抽取记录，强调无损保留、保守单位换算、非破坏性重复标记和人工复核队列。
---

# Lineage Guardian：文献数据清洗与标准化（输入谱系优先）

## 何时使用

当任务是清洗一批**已经由文献、表格或抽取工具产生**的 CSV/TSV 记录，或 `case.json` 中嵌套的 JSON 表，并要求追溯每个输出值时使用本 Skill。它不是通用的论文质量评价器，也不会用领域标签代替原文证据。

优先处理：

- 输入真实性：UTF-8/BOM、非法字节、U+FFFD、文件 SHA256、缺失引用材料。
- 行级谱系：源文件、表、原始行号/JSON pointer、原始列名、原始单元格、行指纹。
- 字段归一：同义列名映射、冲突列不覆盖、未映射列不丢弃。
- 基本单位/区间：`25–30 °C`、`1.2 ks`、SI 前缀、温度/压力/时间/能量/浓度的显式规则换算。
- 重复治理：相同实验的重复抽取只打组号和标记，不静默合并；不同条件即使核心值相同也禁止自动合并。
- 可信交付：cleaned CSV、机器可读 cleaned rows、raw snapshot、逐格 change log、review queue、审计报告和完整 `result.json`。

不适用范围：直接声称从 PDF 中重新抽取科学事实、裁决真实科学冲突、猜测缺失值、识别未登记的复合单位、将不同物质/条件强行归并。遇到这些情况必须保留原值并进入复核。

## 固定运行方式

Python 3.10+，只用标准库。Skill 被安装后，从 Skill 根目录执行：

```bash
python3 scripts/lineage_guardian.py \
  --case /input/case.json \
  --task /input/task.md \
  --work /app/work \
  --out /app/output
```

四个路径都有上述默认值，也都可以覆盖。不要预先假设某个材料文件名；实际执行必须读取 `case.json`、`task.md` 和它们所在输入目录。

## 完整工作流

1. **立即落盘诚实部分结果**：在读取 case 前先创建输出目录并写入 `result.json`，状态为 `partial`，没有任何推断值。
2. **控制文件完整性检查**：读取 `case.json` 和 `task.md` 的字节，记录 SHA256、大小、BOM、UTF-8 解码状态和 U+FFFD 数。
3. **材料发现**：
   - 解析 `case.json` 中的嵌套表（如 `rows`、`records`、`data`、`columns`/`rows`）。
   - 跟踪 case/task 中的相对或绝对 `.csv`、`.tsv`、`.json` 引用。
   - 再排序扫描 case 所在输入目录，补足 wrapper 未显式列出的材料；排除输出/工作目录。
4. **无损原始快照**：为每个源分配 `S###`、每个表分配 `T###`、每行分配 `T###-R#####`；记录原始 header 次序、重复 header 的 occurrence key、CSV 物理行范围、JSON pointer、原始单元格和 SHA256 行指纹。短行不补造，额外单元格不丢弃。
5. **编码守护**：仅按 UTF-8 解释。BOM 被记录且不影响列名匹配；非法 UTF-8 用 U+FFFD 恢复并把运行降为 `partial`。任何已有或恢复产生的 U+FFFD 都列入复核。
6. **字段映射**：按 `references/unit-field-dictionary.md` 的显式别名映射。多个非空列映射到同一字段且值冲突时，保留先出现列，后列进入 `unmapped_fields`，并产生错误级复核项。
7. **值和缺失处理**：只做 Unicode NFC、外缘空白/BOM 清理和显式 missing token 归空；`N/A`、`null`、`-`、`未报告` 等不变成 0。内部术语不改写，除登记过的属性同义词外不做化学推断。
8. **数值/区间/单位**：分离数字与单位；区间只保留 min/max，不创造中点。只转换 `references/unit-field-dictionary.md` 中列出的单位。未知或上下文含糊的单位保持不转换并标记。每次换算在 change log 中写明原值、新值、规则 ID、公式、单位和精度说明。
9. **重复检测**：先按完整 raw-row SHA256 找精确候选，再按“材料 ID（优先）/材料名 + 属性 + 标准值 + 单位 + 文献引用”构造语义候选键；实验 ID、温度、压力、时间、浓度和条件文本构成上下文。所有重复候选全部保留。核心相同但上下文不同的行标记为 `same_core_different_context`，不得合并。
10. **复核与审计**：缺失材料/属性/值、未知单位、无法解析数值、编码损坏、列冲突、未映射非空列和重复候选进入 `review_queue.json`。审计报告汇总来源、计数、规则命中、复核热点、artifact SHA256 和未解析 contract 字段。
11. **最终 `result.json`**：始终包含 `case_id`、`status`、`sources`、`uncertainty`、`change_records`、`artifacts`，并保留 `output_contract` 的每个顶层字段。dict/list/string 三种 contract 形态均可解析。不能语义填充的未知键为 `null`，同时列入 `unresolved_contract_fields`，绝不编造。

## 输出契约

成功或部分成功时，输出目录至少包含：

- `result.json`：结构化结果、case 标识、状态、来源、uncertainty、change_records、artifact 哈希、contract 字段。
- `cleaned_rows.csv`：扁平 UTF-8 数据表；非空输入行全部保留，重复候选不被删除。
- `cleaned_rows.json`：机器可读 cleaned rows，含 typed fields 与完整 provenance。
- `raw_snapshot.json`：无损输入快照、原始列/单元格、行身份与指纹。
- `change_log.jsonl`：逐格变更，一行一个 JSON，带规则 ID、源定位、公式和精度说明。
- `review_queue.json`：所有需要人工裁决的项及建议动作。
- `audit_report.md`：人类可复核的确定性审计报告。

`cleaned_rows.csv` 中 `include_in_statistics=false` 表示存在缺失关键字段或别名冲突；它不是说原始行不存在。`row_status=needs_review` 要求回到 `source_id`、`table_id`、`row_id`、`row_fingerprint` 和 `source_locator` 检查。

## 状态语义

- `success`：解析完成。仍可能存在 review queue；成功不等于科学冲突已裁决。
- `partial`：至少一个输入无法完整信任（如非法 UTF-8 恢复、引用材料缺失、部分材料解析失败），但已诚实保留所有可用结果。
- `input_error`：case 本身不可用、找不到/解析不了，或没有可处理的材料。仍会写入所有可得 contract 字段和空值，不填造。

## 规则边界和维护

规则 ID 的适用条件、优先级和失效处理见 `references/rule-identifiers.md`。字段别名、单位目标、换算公式和精义见 `references/unit-field-dictionary.md`。新增单位或字段时必须先改参考表和脚本中的显式规则，再运行合成示例；不要在单次任务中用模型临时猜规则。

优先级：输入完整性异常 > 行身份/原始值保留 > 字段冲突保护 > 显式单位规则 > 缺失/异常标记 > 非破坏重复分析。任何自动转换都不得覆盖 raw snapshot。

## 确定性与自查

脚本不使用网络、随机数、时钟或第三方包；目录扫描排序，JSON 输出键排序，行顺序按发现顺序。连续两次用同一输入和不同输出目录运行时，除用户明确排除的绝对输入路径/运行路径或时间外，实质 artifacts 应一致。自查最小步骤：

1. 运行示例命令。
2. 检查 `result.json.status` 与 `review_queue.json`。
3. 抽一个被换算值，沿 `change_log.jsonl` 的 `row_id` 回查 `raw_snapshot.json`。
4. 对重复组确认所有候选行仍在 `cleaned_rows.csv`。
5. 重跑到另一个目录并比较 cleaned CSV、cleaned JSON、change log、review queue 和 audit report 的实质内容。

## 示例

`examples/synthetic-input` 与 `examples/synthetic-output` 是最小可运行示例。它们是**合成教学数据，不是官方测试答案，也不是真实实验**。命令与重跑说明见 `examples/synthetic-output/run-record.md`。
