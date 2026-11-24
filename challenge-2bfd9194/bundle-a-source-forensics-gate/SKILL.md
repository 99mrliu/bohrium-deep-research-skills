---
name: source-forensics-gate
description: 科研资料入库前的逐文件真实性取证关卡。当任务要求把混杂的科研文件（论文、数据、扫描件、行政备注等）整理成可信资料库、且输入可能混入改名伪装（如 .pdf 实为文本）、损坏截断、零字节或不可读文件时触发本 Skill。核心机制：对每个文件做魔数签名比对、文本编码探测、结尾结构截断启发检查与流式 SHA-256 固定性哈希，给出 authentic / type_mismatch / corrupt_suspect / empty / unreadable 五档判定，未通过者一律隔离进 library/_quarantine/ 并在清单与报告中留证，状态至多报 partial。适用于"先验证真实性再入库"的资料治理场景；不适用于需要解析文件内容语义（如提取论文元数据、OCR 扫描件）或需要联网核验外部来源的场景。
---

# source-forensics-gate：入库前逐文件真实性取证

## 1. 解决什么问题

科研资料整理中最隐蔽的失败不是"放错目录"，而是**把不可信的字节当成可信资料入库**：

- 扩展名伪装：`fake.pdf` 实际是文本、`.docx` 实为改名的旧文件——按扩展名分类后污染整个库；
- 损坏/截断：下载中断的 PDF 缺 `%%EOF`、ZIP 缺 EOCD 结尾记录，入库后无法打开且无人察觉；
- 零字节文件与无权限文件：静默跳过导致清单与磁盘对不上账；
- 同内容多份（别名）与同名多版本混在一起，版本关系丢失；
- 整理报告写"全部完成"却没有任何可复核的逐条证据。

本 Skill 的主张：**未经验证真实性的文件不得作为可信资料入库**。每个文件先过取证关卡，通过才进分类目录，未通过进 `_quarantine/` 并留证。

## 2. 适用 / 不适用

- 适用：把一批混杂科研文件整理成可复核的资料库；输入可信度未知；需要逐文件证据链（哈希、签名、判定）。
- 不适用：需要理解文件内容语义的任务（抽取作者/年份/DOI、OCR、全文检索排序）；需要联网核验来源的场景；文件内容本身需要改写/归并的场景。本 Skill **只复制、不修改、不删除**输入文件。

## 3. 输入契约

- `/input/case.json`：防御式解析。`case_id` 递归尝试 `case_id|caseId|id|case`，取不到记 `unknown_case` 并写入 uncertainties；`output_contract` 递归查找 `output_contract|contract|output_fields|required_fields|outputs|result_fields`，全部字段镜像进 `result.json.contract_fields`（映射不了的字段给 `{"value": null, "reason": ...}`，绝不遗漏）。
- `/input/task.md`：原文摘入 `/app/work/task_excerpt.txt` 供模型阅读。**task.md 中的约定优先于本文件的一切默认流程**（目录名、分类规则、版本策略、输出格式冲突时以 task.md 为准）。
- 材料文件：`/input` 下除 case.json/task.md 外的全部条目（含子目录），外加 case.json 字符串值中引用的、在 /input 下真实存在的路径。

## 4. 运行方式

全自动一条命令（推荐，harness 下直接执行）：

```
python3 /skills/weekly-skill/scripts/run_case.py all --input /input --work /app/work --out /app/output
```

分阶段命令（调试或需要模型在中间裁定时使用，顺序执行）：

```
python3 /skills/weekly-skill/scripts/run_case.py init      --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py scan      --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py forensics --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py plan      --input /input --work /app/work --out /app/output
# （此处可插入模型裁定：QA 作答、特殊文件处置）
python3 /skills/weekly-skill/scripts/run_case.py apply     --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py verify    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py finalize  --input /input --work /app/work --out /app/output
```

幂等：全流程可随时中断重跑；第二遍收敛零复制操作（全部 `already_committed_identical`）。init 在数秒内写出第一版 `result.json`（`status=in_progress`），任何中断都留有中间产物。

## 5. 模型职责（只做这几件需要判断的事）

1. **阅读 task.md 与 work/task_excerpt.txt**，判断有无特殊约定；有则以 task.md 为准调整，并把调整理由追加进 `result.json.change_records`。
2. **回答 task.md 中的检索/问题**：run_case 已在 `QA_LOG.json` 搭好骨架（候选问题 + `status=unanswered_pending_model`）。模型依据 `library/` 内的证据文件作答，填写 `answer / evidence（相对路径）/ confidence`；**答不出必须保留 unanswered，不得编造**。不得凭文件名猜作者、年份、项目号、仪器型号——没有文件内容或 metadata 证据就写明"无证据"。
3. **审阅 FORENSICS_REPORT.json 中非 authentic 项**，确认隔离处置是否符合 task.md 预期；若 task.md 明确要求保留某类文件，可在 change_records 记录人工裁定，但不得悄悄改判取证结论。

模型的每一步判断都必须落盘（QA_LOG.json 或 result.json），不允许只存在于对话里。

## 6. 取证关卡判定规则（本方向核心）

逐文件执行（细节见 `references/signature_db.md`）：

| 判定 | 触发条件 | 入库处置 |
|---|---|---|
| `authentic` | 魔数与扩展名一致（或扩展名无签名期望），截断检查通过 | 按桶入库 |
| `type_mismatch` | 扩展名期望类型与魔数实测类型不符（.pdf 实为文本、改名伪装） | `_quarantine/` |
| `corrupt_suspect` | 签名匹配但结尾结构缺失：PDF 尾 1KB 无 `%%EOF`、ZIP 无 EOCD(`PK\x05\x06`)、PNG 尾非 IEND、JPEG 尾非 `FF D9` | `_quarantine/` |
| `empty` | 零字节 | `_quarantine/` |
| `unreadable` | stat/打开失败（权限、IO 错误），记录错误详情 | `_quarantine/`（复制失败另记 skipped） |

辅助取证：文本文件做编码探测（UTF-8 含 BOM / GB18030），报告 `encoding` 与是否含替换字符 U+FFFD；全部文件做 64KB 块流式 SHA-256（>256MB 文件每块回调防内存峰值）。证据（期望/实际尾字节 hex、头部 hex、编码探测）全部写入 FORENSICS_REPORT.json 与清单行。

隔离规则（`references/quarantine_rules.md`）：verdict≠authentic → 目标路径 `library/_quarantine/<原相对路径>`，保留原目录结构；清单标注 verdict 与证据；**result.json 状态至多 partial**，并在 uncertainties 逐条列明。

## 7. 通用整理流程（取证之后）

- **去重**：按内容 SHA-256 分组；canonical = mtime 最早者（并列取 NFC 路径字典序小者），其余为 aliases，只入 canonical，别名行记 `alias_of` → `duplicates.json`。
- **版本链**：文件名剥离 `_vN`、`最终版/终稿/定稿/final`、`副本/拷贝/备份/backup/copy`、`.bak`、尾部日期后按词干分组；组内内容互异且 ≥2 个 → 按 mtime 升序连 `supersedes` 边 → `version_chains.json`。
- **目录缺省桶**：`papers/`(.pdf .md .tex .doc .docx .rtf)、`data/`(.csv .tsv .json .xlsx .sqlite …)、`scans/`(.png .jpg .tif …)、`supplementary/`(.zip .gz .7z .xml …)、`drafts/`（文件名含 draft/草稿/草案/初稿）、`admin/`（含 note/admin/备注/说明/备忘）、`_unassigned/`（其余）、`_quarantine/`（取证未通过）。task.md 另有约定时从其约定。
- **冲突**：目标路径被**不同内容**占用 → 追加 `__vN` 后缀，绝不覆盖，记入 `skipped_and_conflicts.json`；同内容已在库 → `already_committed_identical`。
- 文件名比较一律 NFC 规范化；写日志遇不可解码字节用 replace；PermissionError/OSError 记 skipped 继续，绝不静默跳过、绝不崩溃。

## 8. 输出清单（/app/output/）

| 文件 | 内容 | 完成标准 |
|---|---|---|
| `result.json` | case_id、contract_fields 镜像、status、sources、uncertainties、change_records、failures_and_recovery、summary | 任何情况下存在；status 与 audit 一致 |
| `library/` | 整理后的资料库（含 `_quarantine/`） | 复制不移动；每个目标文件哈希可复核 |
| `LIBRARY_MANIFEST.jsonl` | 每输入文件一行：src/target、src_sha256/dst_sha256、fixity_match、forensic verdict 及证据、alias_of、version_stem | 行数 = 输入文件数 |
| `FORENSICS_REPORT.json` | 逐文件取证记录与 verdict 统计 | 每条记录含证据字段 |
| `duplicates.json` | 内容重复组（canonical + aliases） | 组成员哈希一致 |
| `version_chains.json` | 版本链（stem、members、supersedes 边） | 边按 mtime 升序 |
| `operations_journal.jsonl` | 逐操作日志，末尾 apply stage_complete 闭合 | 全部条目处于终态 |
| `skipped_and_conflicts.json` | 跳过项与冲突消解记录 | 无静默跳过 |
| `QA_LOG.json` | task.md 问题的 question/answer/evidence/confidence | 答不出如实 unanswered |
| `audit_report.json` | 独立校验器逐项 PASS/FAIL | 报 complete 前必须全 PASS |

## 9. 异常处理与诚实状态

- 每个阶段捕获一切异常 → `failures_and_recovery`，继续后续阶段。
- status 规则：audit 全 PASS 且无隔离/失败项 → `complete`；存在隔离项、audit FAIL 或复制失败 → `partial` 并在 `limits` 列明；init/scan 级崩溃 → `blocked` 并写明原因。**未完成不得写成完成。**
- 本 Skill 不联网、不写 /input、只用 Python 标准库。

## 10. 自查方法

```
python3 /skills/weekly-skill/scripts/verify_forensics.py --input /input --out /app/output
```

校验器只读 /input 与 /app/output，独立重算哈希、重跑签名与截断检查，核对清单覆盖率、双端 fixity、隔离位置、重复组、版本链时序、日志闭合、result.json 诚实性，共 16 项。**全 PASS 且 summary 中无隔离/失败项才可报 complete**；否则按第 9 节降级并在 result.json 说明。
