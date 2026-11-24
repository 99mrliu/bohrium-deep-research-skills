---
name: metadata-evidence-registry
description: 科研资料库整理 Skill，重心是元数据字段级证据链（metadata provenance）。当任务要求把一批科研文件按约定目录组织落库、并维护 project/year/data_type/author/instrument 等元数据时触发。核心机制：四级来源优先级（L1 伴随表格/行政备注 > L2 文件内容首部 > L3 文件名语法 > L4 人工裁定），每个字段值必须带可回查 locator（文件#行号 / 文件#record键 / pattern_id / 裁定理由），多来源不同值进入冲突矩阵并保留全部候选，填不出就诚实留空、绝不按文件名"看着像"猜。适用于有伴随元数据表、行政备注、命名约定的文件批次；不适用于需要深度语义理解全文才能确定元数据的场景（此时只能给 L4 人工裁定）。
---

# metadata-evidence-registry — 元数据字段级证据链

## 1. 解决什么问题

科研资料整理最容易断链的环节不是"把文件拖进文件夹"，而是**元数据不可信**：作者、年份、项目号、仪器型号凭文件名猜得似是而非，半年后无人能核对。典型失败包括：

- 元数据只给值不给出处，对错无法复核；
- 伴随表格、文件内容、文件名三者给出不同年份/项目号时静默任取其一，不记录冲突；
- 同名文件直接覆盖、重复文件重复入库、版本链断裂；
- 遇到无权限/损坏文件静默跳过，报告却写"全部完成"。

本 Skill 的核心主张：**元数据没有 provenance 就等于没有元数据。** 每个字段值必须带可回查的出处（locator），独立校验器会逐条重读源文件回查；填不出的字段诚实留空并记录原因。

## 2. 适用 / 不适用

- 适用：有伴随元数据表（csv/tsv/json）、行政备注（txt/md）、命名约定（年份前缀、项目号、版本后缀）的科研文件批次；要求可复核、可复跑、可交接的落库。
- 不适用：元数据只能靠通读全文语义判断（如从论文正文推断通讯作者单位）——此时本工具只提供 L4 人工裁定通道，不会假装自动抽取。
- **task.md 中的约定优先于本文件的一切默认流程。**

## 3. 输入契约（防御式解析）

- `/input/case.json`：`case_id` 递归尝试 `case_id|caseId|id|case`，取不到记 `unknown_case` 并写入 uncertainties；`output_contract` 递归查找 `output_contract|contract|output_fields|required_fields|outputs|result_fields`，全部字段镜像进 result.json 的 `contract_fields`，映射不了的给 `{"value": null, "reason": "..."}`。扩展元数据字段可从 `metadata_fields|extra_fields|fields` 读取（防御式合并进字段字典）。
- `/input/task.md`：原文摘入 `work/task_excerpt.txt`。若含 `{project}/{year}/{data_type}` 形式的目录模板，优先按模板路由；若含检索/问题（含"？"/"?"/"问题："/"检索："的行），生成 `QA_LOG.json` 待模型作答。
- 材料文件：`/input` 下除 case.json/task.md 外的全部条目 + case.json 中引用的绝对路径。

## 4. 运行方式

**全自动一条命令（推荐，模型随后只做 2-3 件高价值裁定）：**

```bash
python3 /skills/weekly-skill/scripts/run_case.py all --input /input --work /app/work --out /app/output
```

分阶段（调试/人工介入时用）：

```bash
python3 /skills/weekly-skill/scripts/run_case.py init    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py scan    --input /input --work /app/work --out /app/output
# 如需人工裁定：先跑 scan+extract，再编辑 work/metadata_overrides.json，然后继续
python3 /skills/weekly-skill/scripts/run_case.py extract --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py plan    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py apply   --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py verify  --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py finalize --input /input --work /app/work --out /app/output
```

只依赖 Python 3 标准库；不写 /input；复制不移动；幂等（重跑收敛零复制，全部为 `already_committed_identical`）。

## 5. 模型职责（只做这几件需要判断的事，全部落盘留痕）

1. **L4 裁定**：跑完 `extract` 后阅读 `conflicts.json`。对规则裁定不满意或信息不足时，编辑 `work/metadata_overrides.json`，格式 `{"<源相对路径>": {"fields": {"<字段>": "<值>"}, "reason": "<必须给理由>"}}`，然后重跑 `plan apply verify finalize`。L4 显式优先于 L1-L3（它是带理由的人工裁决），理由字符串会被校验器强制核对。
2. **作答**：若 `QA_LOG.json` 存在且 status 为 `awaiting_model_answer`，逐条作答并把答案+证据路径（library/ 内相对路径或 registry locator）写入 `answers` 数组，再把 result.json 里对应 uncertainty 消除。
3. **诚实状态**：finalize 给出的 status 不得拔高。有 FAIL、有跳过、有未作答问题，就是 `partial` 并保留 limits。

**禁止**：凭文件名"看着像"猜作者/年份/项目号/仪器型号并写进元数据；绕过 registry 直接手改 metadata_registry.jsonl；把未完成写成完成。

## 6. 四级来源优先级与冲突矩阵（方向特色机制）

判定规则（详见 references/source_priority_rules.md）：

| 级别 | 来源 | locator 形式 | 置信度 |
|---|---|---|---|
| L1 | 伴随表格（csv/tsv/json，含文件列）与行政备注（txt/md 键值行） | `文件#L行号` / `文件#record:键` | 0.95（随行）/ 0.80（全局备注） |
| L2 | 文件内容首部 4KB 模式匹配（项目号：、Project:、仪器/Instrument 等） | `文件#L行号` | 0.85 |
| L3 | 文件名语法（可配置正则集，每个 pattern 有 id，如 `rx_year_prefix`） | pattern_id | 0.60 |
| L4 | 人工/模型裁定（work/metadata_overrides.json，必须给理由） | `metadata_overrides_snapshot.json#文件/字段` | 0.99 |

- **Winner 裁定**：存在 L4 → L4 胜；否则 L1 > L2 > L3；同级按子来源次序（随行 sidecar 行 > 全局行政备注；内容行号小者优先；pattern 按定义次序）。
- **冲突矩阵**：同文件同字段多来源**不同值** → 进 conflicts.json，winner 标注裁定规则，全部候选保留。
- **全局行政备注**只接受 instrument/retention/access_scope/source_party/author 这类安全字段，且只作用于已有至少一条文件级证据的文件；项目号、年份这类强文件属性不接受全局默认。
- **伴随表识别**：csv/tsv 首行含"文件列"（file/filename/文件/文件名/path 等）才当元数据表，其余列名按字段别名字典映射；普通数据 csv 不会被误吞。txt/md 仅当文件名带 行政/备注/admin 特征时才当全局备注来源。
- **诚实留空**：模板变量缺字段 → 文件进 `_unassigned/` 并在 coverage_report.json 记录缺哪些字段，绝不编造。

## 7. 通用整理规则

- **去重**：按内容 SHA-256（64KB 流式）分组，与文件名无关；canonical 为相对路径字典序最小者，别名在 manifest 记 `duplicate_of_canonical`，不重复占用库空间。
- **版本链**：文件名规范化词干（去 `vN/final/最终版/终稿/定稿/副本/copy` 后缀）+ 同扩展名分组，组内 ≥2 个不同内容才成链，按 mtime 升序排列。
- **目标冲突**：目标路径已被不同内容占用 → 自动加 `__vN` 后缀并记录进 skipped_and_conflicts.json；同内容已在库 → `already_committed_identical`。
- **缺省桶**（task.md 无模板时）：papers/ data/ scans/ supplementary/ drafts/ admin/ _unassigned/。
- **跳过**：PermissionError/UnicodeError/OSError 一律记入 skipped 并继续，绝不静默、绝不崩溃；中文与特殊字符文件名按 NFC 规范化比较。

## 8. 输出清单（/app/output/）

| 文件 | 内容 | 完成标准 |
|---|---|---|
| result.json | case_id、contract_fields 镜像、status、sources、uncertainties、change_records、summary | status 与 audit 一致；contract 字段逐项有着落或原因 |
| library/ | 落库目录树 | 与 manifest 一一对应，哈希一致 |
| LIBRARY_MANIFEST.jsonl | 每行：源文件、sha256、字节、target、status、**metadata 子对象 + provenance 摘要（level/locator/source_kind/pattern_id）** | 每个输入文件一行，含重复别名 |
| metadata_registry.jsonl | 每行一个字段值：file/field/value/level/source_kind/locator/pattern_id/confidence/note | 每行 locator 可被 verify 回查命中 |
| conflicts.json | 冲突矩阵：同文件同字段多来源不同值，winner + 全部候选 | 每条 ≥2 个不同值候选，winner 标注规则 |
| coverage_report.json | 每字段填充率、每级别贡献计数、未填充文件清单、_unassigned 原因清单 | 缺字段原因逐条在案 |
| duplicates.json | 内容哈希重复组 | 组内文件哈希确实相等 |
| version_chains.json | 规范化词干版本链 | 链成员词干相同、内容不同 |
| operations_journal.jsonl | 操作日志（copied/already_committed_identical/duplicate_recorded/skipped/phase_end） | 每行可解析、以 phase_end 闭合、覆盖 manifest 全部行 |
| skipped_and_conflicts.json | 扫描跳过 + 落库冲突全量留痕 | 不静默丢弃任何文件 |
| audit_report.json | 独立校验器逐项 PASS/FAIL | overall=PASS 才可报 complete |
| metadata_overrides_snapshot.json | L4 裁定快照（供只读校验器回查） | 无裁定时为空对象 |
| QA_LOG.json | task.md 检索/问题的作答（仅当有问题时生成） | 答案 + 证据路径 |

## 9. 异常处理与诚实状态

- init 数秒内先写 `result.json(status="in_progress")`，此后任何中断都留有中间产物；任何阶段异常记入 `failures_and_recovery` 并继续后续阶段。
- finalize 规则：audit 全 PASS 且无降级项（跳过、落库冲突、未作答 QA、运行期异常）→ `complete`；有降级项 → `partial` 并在 limits 逐条列明；audit_report.json 缺失 → `blocked`。
- conflicts.json 中的规则裁定冲突不算"未决"（已有 winner 且候选全保留），但会写入 uncertainties 供评审知悉；模型可用 L4 裁定改变 winner。

## 10. 自查方法

```bash
python3 /skills/weekly-skill/scripts/verify_registry.py --input /input --out /app/output
```

校验器只读 /input 与 /app/output，独立重算：① 逐条回查 registry provenance（L1/L2 重读源文件对应行核对值真实出现；L3 重跑 pattern；L4 核对快照与理由）；② manifest↔library 目录树一致性（存在性+SHA-256 重算）；③ 重复别名与 canonical 一致；④ 日志闭合与覆盖；⑤ 辅助交付物 JSON 可解析。**overall=PASS 才可报 complete**；有 FAIL 逐项看 detail 修复后重跑 verify+finalize。
