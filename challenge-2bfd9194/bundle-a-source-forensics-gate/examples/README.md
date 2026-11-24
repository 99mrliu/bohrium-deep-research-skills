# 合成示例说明（非正式案例结果）

本目录是**合成示例**：`synthetic-input/` 为人工构造的 12 个极小文本文件，
`synthetic-output/` 为本 Skill 在其上**真实运行** `run_case.py all` 产出的证据文件
（`library/` 目录体未收录，只留 JSON/JSONL）。它们不是正式评测案例的结果。

## synthetic-input 覆盖点

| 文件 | 覆盖场景 | 期望判定/归并 |
|---|---|---|
| `paper_notes.txt` + `paper_notes_副本.txt` | 同内容不同名（别名对） | duplicates 一组，canonical=前者（mtime 早） |
| `report_v1.txt` + `report_最终版.txt` | 词干相同内容不同（版本对） | version_chains：v1 →supersedes→ 最终版 |
| `数据说明.txt` | 中文文件名 | 正常入库（admin 桶） |
| `fake.pdf` | 扩展名伪装（实为文本） | `type_mismatch` → `_quarantine/` |
| `truncated.pdf` | 模拟截断 PDF（有头无 `%%EOF`） | `corrupt_suspect` → `_quarantine/` |
| `empty.txt` | 零字节文件 | `empty` → `_quarantine/` |
| `metadata.csv` | 伴随元数据表 | data 桶 |
| `admin_notes.txt` | 行政版本备注 | admin 桶 |
| `spectrum_v2.csv` / `scan_readme.md` | 普通数据 / 说明文档 | data / papers 桶 |

说明：权限不可读（unreadable）场景依赖操作系统权限位，为保证示例可移植
**不做模拟**；该路径由单元逻辑覆盖（stat/打开失败即判 unreadable 并留证）。
同理 zip/png/jpeg 等二进制签名样本无法在"全文本文件"约束下提供，
仅以文本形式的截断 PDF 演示截断启发。

## 复跑命令

```
mkdir -p /tmp/r1-test/{input,work,output}
cp -r examples/synthetic-input/* /tmp/r1-test/input/
echo '{"case_id":"synthetic-demo-r1","output_contract":["library_manifest","forensics_report","audit_report","qa_log"]}' > /tmp/r1-test/input/case.json
echo '合成示例任务：按类型组织资料，保留版本关系。' > /tmp/r1-test/input/task.md
python3 scripts/run_case.py all --input /tmp/r1-test/input --work /tmp/r1-test/work --out /tmp/r1-test/output
```

## 本次真实运行结果（目检结论）

- `LIBRARY_MANIFEST.jsonl` 12 行 = 输入 12 文件；
- `duplicates.json` 1 组：`paper_notes.txt`（canonical）+ `paper_notes_副本.txt`（alias）；
- `version_chains.json` 1 链：`report_v1.txt` →supersedes→ `report_最终版.txt`；
- `fake.pdf`=type_mismatch、`truncated.pdf`=corrupt_suspect、`empty.txt`=empty，
  三者均落 `library/_quarantine/`；
- `audit_report.json` 16/16 项 PASS；
- `result.json` status=`partial`——因为存在 3 个隔离文件，按规则状态至多
  partial（诚实状态，隔离项已在 uncertainties/limits 列明）；
- 重跑第二遍：11 个 `already_committed_identical` + 1 个别名记录，零新复制，
  audit 仍全 PASS（幂等收敛）。
