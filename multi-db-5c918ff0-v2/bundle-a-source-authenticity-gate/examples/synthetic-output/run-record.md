# Run Record（运行记录）

> **合成示例声明**：`examples/synthetic-input/` 全部为合成教学数据（虚构论文、虚构 DOI
> `10.99999/synth.*`、虚构数据库响应），仅用于演示门控行为，**不是官方赛题答案**。
> 本目录 `examples/synthetic-output/` 是脚本对合成输入的**真实运行产物**，非手写。

## 确切命令

在 bundle 根目录（`bundle-a-source-authenticity-gate/`）下执行：

```bash
python3 scripts/source_gate.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work examples/synthetic-output/work \
  --out  examples/synthetic-output
```

退出码：`0`（`status = "partial"` —— 诚实部分完成：契约字段 `curator_comment`
无法由本技能诚实填写，置 null 并列入 `unresolved_contract_fields`）。

## 重跑步骤

```bash
# 1. 语法与帮助
python3 -m py_compile scripts/source_gate.py && echo OK
python3 scripts/source_gate.py --help ; echo "exit=$?"   # 应为 0

# 2. 端到端（覆盖写出，幂等）
python3 scripts/source_gate.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work examples/synthetic-output/work \
  --out  examples/synthetic-output ; echo "exit=$?"       # 应为 0

# 3. 输入错误路径（应退出 3 且 status=input_error）
python3 scripts/source_gate.py --case /nonexistent/case.json \
  --task /nonexistent/task.md --work /tmp/gw --out /tmp/go ; echo "exit=$?"
```

## 确定性核验（实际执行过）

换一组临时目录重跑并逐字节对比：

```bash
mkdir -p /tmp/gate-verify/out /tmp/gate-verify/work
python3 scripts/source_gate.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work /tmp/gate-verify/work --out /tmp/gate-verify/out
for f in authenticity_ledger.json gated_records.json authenticity_report.md result.json; do
  diff -q examples/synthetic-output/$f /tmp/gate-verify/out/$f
done
diff -q examples/synthetic-output/work/intake_manifest.json /tmp/gate-verify/work/intake_manifest.json
```

实测结果：实质性产物（`authenticity_ledger.json`、`gated_records.json`、
`authenticity_report.md`、`work/intake_manifest.json`）**逐字节 IDENTICAL**；
产物不含绝对路径、不含时间戳；`run_id = gate-f14deb7e8fdd0c95` 由输入内容哈希派生，
输入不变则 run_id 不变。`result.json` 的 `artifacts` 清单如实枚举输出目录中的
每一个文件（含 sha256）：在示例目录中运行时它会额外列出本文件 `run-record.md`，
因此与临时目录运行的 `result.json` 仅差该条目——这是"枚举目录实况"的正确行为，
而非不确定性。

## 预期捕获的埋点缺陷（教学点）

| 材料 | 缺陷 | 预期原因码 | 判定 |
|---|---|---|---|
| `europepmc_response.json` | `hitCount=3` 但只有 2 条结果 | `COUNT_MISMATCH` | trusted_with_warnings |
| `import_state.json` | 条目声称 europepmc id `33000099`，源响应中不存在 | `IMPORT_INCONSISTENT`（条目隔离） | trusted_with_warnings |
| `reference_graph.json` | 边指向 `10.99999/synth.077`，不在任何材料中 | `DANGLING_EDGE`（报告，不致命） | trusted_with_warnings |

此外 `crossref_response.json` 与 `publisher_records.json` 为完全可信（trusted），
同一虚构论文 `10.99999/synth.001` 同时出现于三个来源（元数据略有差异），
7 条记录通过门控进入 `gated_records.json`，每条带有 `source_artifact` 与
jsonpath 式 `locator`（如 `message.items[0]`、`resultList.result[0]`）。
