# manifest 字段定义与重建判据

本文件定义 `manifest.json`（capture.py 生成）与 `rebuild_report.json`
（rebuild.py 生成）的字段语义，以及一致性判定规则。

## 1. manifest.json 顶层字段

| 字段 | 类型 | 含义 |
|------|------|------|
| `manifest_version` | string | 清单格式版本，当前 `"1.0"` |
| `kind` | string | 固定 `"latex-build-manifest"` |
| `created_utc` | string | 生成时间（UTC, ISO 8601） |
| `project.main_tex` | string | 主 .tex，相对工程根目录 |
| `tools.pdflatex / bibtex / pdftotext` | object\|null | 探测到的 `{path, version}`；不可用为 `null` 并在 `limitations` 说明 |
| `engine` | object | 从日志首行解析：`name`（如 pdfTeX）、`version`、`distribution`（如 TeX Live 2026）、`line`（原始首行） |
| `inputs[]` | array | 全部源输入：`path`（相对路径）、`sha256`、`bytes`；排除 .aux/.log/.pdf 等构建产物 |
| `build.steps[]` | array | 精确命令序列：`seq`、`tool`、`argv`（不含二进制绝对路径）、`pass`、`exit_code`、`elapsed_s`、`timed_out` |
| `build.passes` | int | pdflatex 实际轮次（≤4） |
| `build.bibtex_ran` | bool | 是否运行过 bibtex |
| `build.aux_converged` | bool | 收敛判据：相邻两轮全部 .aux（含 \include 子级）按文件名排序拼接的 SHA256 不变 |
| `build.listfiles_injected_on_copy` | bool | \listfiles 是否已生效（工程自带或在构建目录副本注入；绝不改原文件） |
| `build.compile_ok` | bool | 是否生成 PDF |
| `build.pdf_pages` | int\|null | 从日志 `Output written ... (N pages)` 解析 |
| `build.pdf_sha256` | string\|null | PDF 字节哈希（仅供如实报告，不作判据） |
| `file_versions[]` | array | \listfiles 区块逐条：`file`（基名）、`date`、`version`、`description`；无版本信息的条目（如 .bbl）date/version 为 null |
| `fonts[]` | array | 日志中提取的字体文件基名（.pfb/.ttf/.otf），日志折行已归并 |
| `output_text.sha256` | string\|null | `pdftotext -enc UTF-8` 全文文本哈希；工具缺失为 null 并记 `note` |
| `status` | string | complete / partial / blocked / failed |
| `limitations[]` | array | 全部降级与异常说明（诚实记录，不掩饰） |

## 2. rebuild_report.json 比对条目

- `checks.inputs.entries[]`：逐文件 `same / changed / missing`（双侧 SHA256）。
- `checks.versions.entries[]`：类/宏包清单按文件名对齐，逐条目：
  - `same`：两侧 date+version 相同；
  - `different`：两侧都有但 date/version 不同（**版本漂移，主判据**）；
  - `missing`：只在一侧出现，`side` 标明 `absent-in-rebuild`（他人环境缺包）
    或 `absent-in-baseline`（基线记录不全）。
- `checks.engine`：`same / different / unknown`（名称+版本+发行版三元组）。
- `checks.passes`：基线与重建的 pdflatex 轮次及是否相同。
- `checks.aux_converged.rebuild`：重建后 aux 指纹是否与基线一致。
- `checks.pages` / `checks.text`：页数与全文文本哈希是否一致（不可比为 null）。
- `checks.pdf_bytes`：双侧 PDF 字节哈希；附注“/ID 与时间戳导致字节级不同属
  正常，不作为判据”。

## 3. 判定规则（verdict）

| verdict | 条件 |
|---------|------|
| `reproducible-identical` | 源码逐文件 same ∧ 版本清单无 different/missing ∧ 引擎 same ∧ 轮次相同 ∧ 重建 aux 收敛 ∧ 页数一致 ∧ 全文文本一致 |
| `not-reproducible-identical` | 上述任一不满足；版本 different 时必须逐条列出文件名与双侧版本，不得含糊带过 |
| `inconclusive` | 重建侧编译未完成，或 pdftotext 缺失导致文本不可比；必须写明缺什么 |

判定**不使用** PDF 字节哈希一致作为条件（见 references/reproducibility-notes.md
第 4 节）。
