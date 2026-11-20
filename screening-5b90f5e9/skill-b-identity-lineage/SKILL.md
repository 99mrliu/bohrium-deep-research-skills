---
name: identitylineage-dedup-first
description: 当案例提供多来源文献导出文件（JSON/JSONL/CSV/RIS/BibTeX）、存在同一研究的重复副本（多平台重复导出、预印本×正式发表版、题名细微差异、DOI 缺失）并要求去重后做全量题录筛选时触发。本 Skill 主张「筛选的正确性以记录身份解析的正确性为前提」：先做多格式导入嗅探与字段三级语义（missing/unknown/not_provided）标注，再做标识符与题名规范化，按三层身份匹配（Tier1 标识符精确自动合并、Tier2 归一题名+年份自动合并、Tier3 模糊匹配只进仲裁队列绝不自动合并）构建记录身份图，每次合并/不合并都产出可复算的 tier+scores+证据；预印本与正式版合并为一簇但保留完整版本谱系链、以正式版为 canonical；canonical 记录经确定性字段级合并（每字段 provenance、冲突全量入 conflict_log）后由模型批量判定 include/exclude/needs_human 并附理由码与证据片段，脚本强制 evidence_quote 归一化子串锚定（失败 exit 3 重锚），结论经簇谱系传播到全部副本；最终审计 identified = canonical + 合并副本数、screened = included+excluded+needs_human 的计数闭合。边界：不联网检索、不声称实时数据库查询或全局召回（只有输入快照）、不臆造跨标识符映射（PMID-only×DOI-only 只走书目证据）、Tier3 裁决属模型职责不得调阈值强并、不预置任何案例答案、不伪造人工复核。
---

# identitylineage-dedup-first：身份解析优先的去重与谱系化筛选

## 1 适用场景与边界

**适用**：案例提供一批文献导出文件（可能来自多个数据库/平台，含 search09 式合成重复导出），要求先正确识别「哪些记录是同一研究」，再对去重后的 canonical 记录做全量题录筛选（all-record screening），且每个判定可复算、可审计。

**边界（必须遵守）**：
- 不联网：只处理 `/input` 下提供的快照材料；输出中禁止声称实时数据库检索或全局召回，一律标注 snapshot_only。
- 不臆造跨标识符映射：一条只有 PMID、另一条只有 DOI 的记录，不得编造「它们指向同一研究」的标识符对应关系；只能凭 Tier2/Tier3 书目证据（题名/作者/年份）判断。
- Tier3 模糊候选的 merge/split 裁决是**模型职责**，脚本只负责入队、校验 rationale 非空、落痕；不得通过调阈值把 Tier3 升级成自动合并。
- 不预置答案：本 Skill 不含任何具体案例的纳排结论；`examples/` 全部为虚构合成数据。
- 不伪造人工复核：`needs_human` 必须原样保留并写明原因，不得冒充人工裁定。
- 纳排标准编译（从研究问题推导 PICOS 细则）不属本方向，使用 `rules/reason_codes.md` 的简表，按案例 task.md/case.json 的标准直接套用。

## 2 运行环境

- Python 3 标准库（json/re/csv/sys/argparse/pathlib/unicodedata/collections），无第三方依赖、无网络、无二进制。
- 定位 skill 目录（运行时装到 `/skills/weekly-skill`，路径不确定时兜底）：
  ```bash
  SKILL="${SKILL:-$(dirname "$(find / -maxdepth 6 -name identity_resolve.py -path '*identity-lineage*' 2>/dev/null | head -1)" | xargs dirname)}"
  ```
- 退出码约定（全部脚本一致）：`0`=通过；`2`=输入不足、诚实降级（产出部分结果并写明原因）；`3`=校验失败（锚定失败/计数不闭合/rationale 为空等，修复后可重跑）。
- 所有脚本顶层 try/except 兜底：任何异常打印 JSON 错误到 stderr 并 exit 3，绝不 traceback-crash；均支持 `--help`。
- 幂等断点续跑：所有脚本可重复执行，输出覆盖式重写；`scaffold_result.py` 默认**不覆盖**已有 `result.json`（保护增量填充成果，需 `--force` 才重建）。

## 3 工作流程（预算友好：模型判断全部批量化）

预算约束：64 次模型请求 / 900 秒 / 每次响应 16384 token。脚本做掉全部确定性工作，模型只做**两次批量判断**（仲裁一次、筛选一次）。

0. **定位与解析案例**（脚本，无模型消耗）：
   ```bash
   python3 "$SKILL/scripts/parse_case.py" --input-dir /input --work /app/work
   ```
   产出 `/app/work/case_summary.json`（case_id、research_question、output_contract、材料清单与嗅探格式）。
1. **尽早落盘 result.json 骨架**（防超时零交付）：
   ```bash
   python3 "$SKILL/scripts/scaffold_result.py" --work /app/work --output-dir /app/output
   ```
2. **多格式导入嗅探**：
   ```bash
   python3 "$SKILL/scripts/import_records.py" --work /app/work
   ```
   → `records.jsonl`（identified 总条数在此确定；field_status 三级语义；解析失败降级留痕于 `import_warnings.json`）。
3. **身份解析（规范化+阻塞+三层匹配）**：
   ```bash
   python3 "$SKILL/scripts/identity_resolve.py" --work /app/work
   ```
   → `pair_decisions.jsonl`（每个候选对 tier/decision/scores/evidence）、`clusters.json`（Tier1/Tier2 自动合并簇）、`review_queue.json`（Tier3 待仲裁对）。
4. **模型批量仲裁（第 1 次模型请求）**：把 `review_queue.json` 全量贴给模型，按 `templates/arbitration.md` 与 `rules/matching_policy.md` 对每个 pending 对给 merge/split + 非空 rationale（标题相似但人群/年份/期刊/DOI 冲突的必须显式 split），落盘 `/app/work/arbitrations.json`，然后：
   ```bash
   python3 "$SKILL/scripts/apply_arbitration.py" --work /app/work   # rationale 空或漏裁 → exit 3
   ```
5. **canonical 构建**：
   ```bash
   python3 "$SKILL/scripts/build_canonical.py" --work /app/work
   ```
   → `canonical_records.json`（字段级合并+provenance+version_chain）、`conflict_log.jsonl`。
6. **模型批量筛选（第 2 次模型请求）**：把 `canonical_records.json` 的 canonical_id/title/abstract 与研究问题、纳排标准一次性给模型，按 `templates/screen_judgments.md` 与 `rules/reason_codes.md` 逐条给 {decision, reason_code, evidence_quote}，落盘 `/app/work/screen_judgments.jsonl`，然后：
   ```bash
   python3 "$SKILL/scripts/screen_canonical.py" --work /app/work   # 锚定失败 → anchor_failures.json + exit 3，按失败项重锚后重跑本步
   ```
   → `final_decisions.jsonl`（含副本谱系继承清单）、`screening_counts.json`。
7. **计数闭合审计**：
   ```bash
   python3 "$SKILL/scripts/audit_check.py" --work /app/work        # 不闭合 → exit 3
   ```
8. **填充交付并终检**：
   ```bash
   python3 "$SKILL/scripts/fill_result.py" --work /app/work --output-dir /app/output
   python3 "$SKILL/scripts/selfcheck.py" --work /app/work --output-dir /app/output   # 必须 exit 0 才交付
   ```
   `fill_result.py` 只填已知语义字段；合同额外字段（pending_fields 列出）由模型按语义补写进 result.json 后，再跑一次 `selfcheck.py`。

## 4 输出合同映射表

| result.json 字段 | 填充来源产物 |
|---|---|
| case_id | `case_summary.json.case_id` |
| skill_name | 常量 `identitylineage-dedup-first` |
| status | `audit_summary.json.all_ok` → completed / degraded |
| product | 各产物路径（final_decisions / canonical_records / clusters.final / pair_decisions / audit_summary）+ snapshot_only 声明 |
| evidence_matrix | `final_decisions.jsonl`（每 canonical 的 decision/reason_code/evidence_quote/members） |
| sources | `case_summary.json.material_files`（文件名+嗅探格式+大小） |
| uncertainty | `conflict_log.jsonl` + needs_human 清单 + import warnings + snapshot_only/no_live_search 标注 + pending_fields |
| change_records | 流水线各步骤固定台账（fill_result 生成） |
| counts | `audit_summary.json` + `screening_counts.json`（identified/canonical/merged_copies/screened/included/excluded/needs_human/propagated_records/field_conflicts） |
| checks | `audit_summary.json.checks` 逐条闭合证据 |
| 合同额外字段 | 由运行时模型按字段名语义填充；`fill_result.py` 把未覆盖字段登记到 `uncertainty.pending_fields`，`selfcheck.py` 强制非空 |

## 5 异常处理表

| 异常 | 行为 | 退出码 |
|---|---|---|
| /input 或 case.json 缺失 | 写降级 case_summary（case_id=UNKNOWN），诚实标注 | 2 |
| research_question / output_contract 缺失 | warnings 留痕，骨架用默认字段集 | 2 |
| 材料文件格式不支持/解析失败/零记录 | 跳过该文件，记入 `import_warnings.json`，继续其余文件 | 2 |
| 全部文件无记录可导入 | 无法继续 | 3 |
| 无 Tier3 待仲裁对 | 自动簇直接定稿 `clusters.final.json` | 2（正常路径） |
| arbitrations.json 缺失/漏裁/未知 pair/rationale 空 | 写 `arbitration_errors.json` | 3 |
| evidence_quote 锚定失败 / 缺判定 / 理由码前缀不符 / needs_human 无 note | 写 `anchor_failures.json`，修复后重跑 | 3 |
| 计数不闭合 / 簇成员不覆盖全量记录 / 多副本簇无合并证据 / 谱系副本数不符 | 写 `audit_summary.json` 标出失败检查项 | 3 |
| result.json 合同字段缺失或为空 / 产物缺失 / 审计未过 | selfcheck 列出 failures，禁止交付 | 3 |
| 任何未预期异常 | 顶层兜底打印 JSON 错误 | 3 |

## 6 最小调用示例

见 `examples/example_walkthrough.md`（基于 `examples/example_case.json` 与 `examples/example_exports/` 两个合成导出文件，含 1 对 DOI 相同副本、1 对题名细微差异副本、1 对预印本×正式版、1 对标题相似但不同研究必须 split、1 条 DOI 缺失记录；**全部为虚构数据**）。完整自测命令与真实退出码见 `examples/selftest_log.md`。

## 7 维护信息

- 版本：v1.0.0（2026-11-20）
- 规则文档：`rules/matching_policy.md`（三层匹配判据与两类错误防护）、`rules/version_chain.md`（版本谱系）、`rules/reason_codes.md`（理由码简表）
- 模板：`templates/arbitration.md`、`templates/screen_judgments.md`
- 脚本：`scripts/`（parse_case → scaffold_result → import_records → identity_resolve → apply_arbitration → build_canonical → screen_canonical → audit_check → fill_result → selfcheck）
