# 隔离（quarantine）规则

核心主张：**未经验证真实性的文件不得作为可信资料入库。**

## 触发条件

`FORENSICS_REPORT.json` 中 verdict ≠ `authentic` 的每个文件，即
`type_mismatch / corrupt_suspect / empty / unreadable` 四档全部触发隔离。
不设白名单、不做例外；task.md 明确要求保留某文件时，由模型在
`result.json.change_records` 记录人工裁定，但取证判定本身不改写。

## 处置

1. 目标路径固定为 `library/_quarantine/<原相对路径>`，**保留原目录结构**
   （如原路径 `raw/2026/fake.pdf` → `library/_quarantine/raw/2026/fake.pdf`），
   便于溯源与人工复核。
2. 与正常入库同样复制（不移动）、同样做双端 SHA-256 fixity 校验；
   `unreadable` 复制失败时记入 `skipped_and_conflicts.json`，清单行 `copied=false`。
3. `LIBRARY_MANIFEST.jsonl` 对应行标注 `forensic_verdict` 与完整证据
   （头部 hex、期望/实际尾字节 hex、编码探测、错误信息）。
4. `result.json`：
   - `status` **至多 `partial`**（即使其余全部 PASS）；
   - `uncertainties` 逐条列明每个隔离文件及其判定；
   - `summary.quarantined` 给出计数。
5. 去重先于隔离判定：别名（内容相同的副本）不单独复制，清单行记
   `alias_of` 指向 canonical 的目标；若 canonical 被隔离，别名行同样指向
   `_quarantine/` 下的目标。

## 复核与解除

隔离不是删除。人工确认文件可信后，可手工把文件从 `_quarantine/` 移入对应桶
并重跑 `run_case.py apply + verify + finalize` 更新清单与状态；
引擎自身永不自动解除隔离。
