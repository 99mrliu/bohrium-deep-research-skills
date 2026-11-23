# Independent verification checklist

验证阶段是第二阶段，不从 `run` 阶段继承内存状态。它重新读取 case、task、result、统计表、异常账本、逐单元格日志、checksum 和 manifest，并用新的 cleaner 实例从源记录重建期望状态。验证报告原子写回 `validation.json`。

## 1. 标准调用

```bash
python3 scripts/contract_auditor.py run \
  --case /input/case.json \
  --task /input/task.md \
  --work /app/work \
  --out /app/output

python3 scripts/contract_auditor.py verify \
  --case /input/case.json \
  --task /input/task.md \
  --out /app/output
```

已有目录只验不洗：

```bash
python3 scripts/contract_auditor.py --verify \
  --case /input/case.json \
  --task /input/task.md \
  --out /app/output
```

如果清洗时使用了非默认行预算，verify 传同一值：

```bash
python3 scripts/contract_auditor.py verify --max-rows 10000 \
  --case /input/case.json --task /input/task.md --out /app/output
```

## 2. 机器检查清单

| 检查 | blocking 失败代码 | 证明内容 |
|---|---|---|
| strict JSON | `RESULT_INVALID_JSON`、`CLEANED_JSON_INVALID` | result/cleaned 可解析且不含 NaN/Infinity |
| case 重读 | `INPUT_CASE_INVALID`（finding） | 输入可重新摄取；若原结果诚实标为 `input_error`，验证不因源失败误判产物 |
| 契约字段 | `CONTRACT_MISSING_FIELD` | 核心字段和 output_contract 声明字段全部存在 |
| null 扩展 | `UNKNOWN_FIELD_NOT_LISTED` | 未适配字段保持 null 且列入 `unresolved_fields` |
| manifest schema/path | `MANIFEST_INVALID` | manifest 结构合法，路径相对且不含 `..` |
| artifact 存在 | `ARTIFACT_MISSING` | 所有 payload 存在 |
| checksum drift | `ARTIFACT_CHECKSUM_DRIFT` | payload 与 manifest/checksum 的大小、SHA-256 一致 |
| artifact 引用 | `ARTIFACT_REFERENCE_MISMATCH` | result 的 artifact map 指向固定文件名 |
| 表 schema | `CLEANED_SCHEMA_MISMATCH` | CSV header 与从源重建的动态 schema 一致 |
| 行数 | `ROW_COUNT_MISMATCH` | cleaned CSV/JSON 行数等于 kept+flagged |
| 单元格内容 | `CLEANED_CONTENT_MISMATCH` | 每个 retained 单元格与源重建一致 |
| raw conversion trace | `RAW_CONVERSION_TRACE_BREAK` | 换算值、change ID、raw value/unit、公式和 changes.jsonl 未被篡改 |
| source hash | `RAW_TRACE_BREAK` | 输出行的 `source_record_sha256` 绑回同一原始输入行 |
| 覆盖 | `COVERAGE_MISMATCH` | 每个输入行恰有一个互斥处置，计数与主表一致 |
| 异常对账 | `UNMAPPED_OR_ANOMALY_UNREPORTED`、`UNEXPECTED_ANOMALY` | 未映射列、未知单位、坏数字等没有漏报或凭空多报 |
| 状态诚实 | `STATUS_INCONSISTENT` | status 与 fresh anomaly/contract findings 一致 |

## 3. 验证报告解释

- `status: pass`：无 blocking/error 验证发现。仍应检查 result 中的科学 warnings/errors。
- `status: pass_with_findings`：产物结构无 blocking，但重新读取源时存在已诚实标记的 input/error finding，例如一个 `input_error` 示例。
- `status: fail`：至少一个 blocking，命令退出 3。此时不能交付为最终结果；partial 工件仍可用于人工修复。
- `exit_code` 与 shell 返回码一致。

## 4. 推荐人工复核顺序

1. 看 `validation.json.summary.blocking`；非零先修完整性问题。
2. 看 `result.json.status` 和 `result.coverage.counts`。
3. 先处理 `review_queue.csv` 中 error，再处理 warning。
4. 对任一改动，用 `changes.jsonl` 的 `input_row_id/source_pointer/change_id/rule_id` 回查 case 或 CSV 原行。
5. 对去重，只在 `duplicate_of` 指向同一显式 record_id 且 identity 完整一致时接受 D001；D002/D003 必须人工裁决。
6. 确认未知契约键仍为 null 并在 `unresolved_fields` 中；不要为凑合同补造值。

## 5. 篡改自检方法

不要在正式输出目录中做破坏性测试。复制产物到临时目录，修改一个统计值，再运行 verify：

```bash
cp -R examples/synthetic-output /tmp/contract-auditor-corrupt
python3 - <<'PY'
from pathlib import Path
p = Path('/tmp/contract-auditor-corrupt/cleaned.csv')
p.write_text(p.read_text(encoding='utf-8').replace('101325', '999999', 1), encoding='utf-8')
PY
python3 scripts/contract_auditor.py verify \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --out /tmp/contract-auditor-corrupt
```

预期：退出码 3，`validation.json` 至少含 `ARTIFACT_CHECKSUM_DRIFT`；若改动的是值或 change trace，还会出现 `RAW_CONVERSION_TRACE_BREAK` 或 `CLEANED_CONTENT_MISMATCH`。

## 6. 确定性测试

同一 case、同一脚本版本、同一 `--max-rows` 连续运行到两个不同输出目录，所有固定产物应字节一致；输出不含 wall-clock 时间戳和机器绝对路径。比较：

```bash
diff -r first-output second-output
```

预期退出码 0。平台运行时目录名不同不影响 manifest，因为 manifest 只记录相对 artifact 名。

## 7. 已知边界

- 验证器证明“按已声明规则从输入到产物可复核”，不证明科学解释为真。
- 已报告的源数据 error/warning 使 `result.status=partial`，但不会让 verify 因科学异常本身返回 3；只有交付契约/追踪/完整性失败才 blocking。
- 如果同一目录在 verify 运行期间被第三方持续修改，需暂停修改后重跑，以获得一致快照。
