---
name: source-truth-gate
description: 引用与事实核验的"上游数据真实性"门禁协议。当任务要求对论文或科研材料做质量、引用、事实、方法、统计、逻辑或规范审查时使用。核心立场：先做来源真实性门禁（参考文献是否真实存在、是否被撤稿或更正、预印本与正式版本是否一致、DOI 与元数据是否自洽），再做内容审查——任何引用支持判定若建立在伪造或已撤稿的来源上都是无效结论。配套三个 stdlib 脚本：ingest_text.py（材料解析）、extract_refs.py（参考文献条目抽取与 DOI 校验）、verify_sources.py（七态来源核验状态机，对伪造/冲突/撤稿条目以退出码 1 硬报警）。无网络或无可信快照时所有条目降级为 not_checked 并在报告中标记待复核，绝不凭空给出"来源可靠"结论。
---

# source-truth-gate：上游来源真实性门禁 + 全面审查

## 1. 定位与核心立场

本 Skill 是"引用与事实核验"任务的一个**重心错位**实现：大多数审查流程把力气花在正文语义判断上，把参考文献列表当作给定事实。本 Skill 把重心放在**上游数据真实性**——被引来源本身是否真实、是否仍然有效（撤稿/更正）、引用的是否是正确的版本。理由：引用支持判定的前提是被引文献真实且如条目所描述；伪造文献（fabricated reference）、撤稿后继续引用、预印本与正式版结论不一致，这三类问题不查上游就永远发现不了。

门禁之后的第二阶段仍然是**完整的六类审查**（事实核验、引用支持、方法设计、统计报告、论证链、学术规范），因为任务要求完整覆盖；但每条涉及外部来源的 finding 都必须回指门禁的核验状态，来源状态为 `not_checked` 的引用支持判定 confidence 不得高于 medium。

## 2. 适用条件与不适用范围

适用：单篇论文或科研材料（电子 PDF、扫描 PDF 配合 OCR、纯文本、仅摘要）的质量审查，尤其是参考文献较多、依赖外部事实的综述与实证论文。

不适用：论文润色、综述写作、数据分析建模；不替代作者对研究结论的判断。文献核读只是取证手段。

## 3. 运行契约（Harbor）

- 输入：`/input/case.json` 与 `/input/task.md`；材料（PDF/TXT/MD/HTML）由 case 指定或位于 `/input/` 下。
- 工作目录：`/app/work`；最终交付：`/app/output/`。
- `result.json` 必须含 `case_id` 与 **case.json 中 output_contract 声明的全部字段**（防御式复制，见 3.2），并含诚实的状态、来源、不确定性与变更记录。
- 预算：64 次模型请求、900 秒、单次响应 ≤16384 token。脚本不占模型预算，重活一律交给脚本。每个阶段结束立即落盘中途产物，任何时刻中断都能从 `/app/work` 恢复；预算不足时保存诚实的 partial（`status="partial"`，`unchecked_items` 写明缺什么、为何缺）。
- 禁止编造：不存在的核验记录、DOI、工具输出、撤稿信息一律不得虚构；查不到就写"待复核"与复核路径。

### 3.1 防御式输入解析

1. 读 `/input/case.json`（不存在则取 `/input/` 下任意 `*.json`）。`case_id` 依次尝试 `case_id`/`id`/`caseId`/`case.id`；取不到时用文件名并在 `uncertainties` 说明。
2. 材料路径：依次尝试字段 `paper`/`pdf`/`material`/`document`/`file`/`manuscript`（含一层嵌套）；都不命中则在 `/input/` 按 `*.pdf → *.txt → *.md → *.html` 取第一个。
3. 读 `/input/task.md`，提取本案例的具体审查面、finding 类型与证据要求。**task.md 优先于本文件通用清单**，冲突时以 task.md 为准并在报告中说明。
4. 材料缺失：`status="blocked"`，findings 为空，`unchecked_items` 写明缺失项，仍写出 result.json 与报告后终止。

### 3.2 output_contract 防御式复制

case.json 若含 `output_contract`（或 `outputContract`/`outputs`）字段，逐字段在 result.json 顶层建立同名字段并按其语义填充；无法填充的字段保留并置 `null`，在 `uncertainties` 逐条说明。不得丢弃 contract 字段，不得捏造其取值。

## 4. 工作流程

### 阶段 0：解析（脚本，0–1 次模型请求）

```bash
cd /app/work
python3 <SKILL_DIR>/scripts/ingest_text.py --input <材料路径> --out pages.jsonl --meta ingest_meta.json
```

- 依次尝试 `pdftotext -layout`、`pdftotext` 原始模式、纯文本直读；扫描件且环境提供 OCR 工具时对渲染页 OCR（页数多时只 OCR 关键页并在 uncertainties 说明）。
- 全部失败：`ingest_meta.json` 记 `extract_status="failed"` 与原因，转 blocked 流程。

### 阶段 1：参考文献抽取与门禁核验（脚本为主，0–2 次模型请求）

```bash
python3 <SKILL_DIR>/scripts/extract_refs.py --pages pages.jsonl --out refs.json
python3 <SKILL_DIR>/scripts/verify_sources.py --refs refs.json --snapshot <可信快照.json，可选> \
    --out source_report.json   # 有网络且确有需要时加 --online（Crossref 公开 API，超时即放弃）
```

- `extract_refs.py`：定位参考文献节（References/参考文献/Bibliography），解析编号制 `[1]` 与作者-年份制条目，抽取 DOI 并做语法校验（`10.\d{4,9}/\S+` 且不含空格/句点结尾），抽取年份、首作者姓、标题猜测段。解析失败条目保留 raw 文本并标 `parse_ok=false`，不得丢弃。
- `verify_sources.py` 七态状态机（定义见 `references/verdict_states.md`）：`verified / metadata_conflict / not_found_in_snapshot / suspected_fabricated / retraction_flagged / version_mismatch / not_checked`。对 `suspected_fabricated`、`metadata_conflict`、`retraction_flagged`、`version_mismatch` 以退出码 1 硬报警。
- **可信快照来源优先级**：① task.md 或 case.json 随附的快照/数据库导出；② 环境联网时用 `--online` 对每条带 DOI 的条目查询 Crossref 公开元数据自动构建快照（记录查询时间）；③ 二者皆无 → 全部 `not_checked`，报告写明"来源真实性未核，待复核"，复核路径给出建议查询入口（Crossref、Retraction Watch Database、出版社页面）。**绝不允许在无任何来源记录的情况下把条目判为 verified。**
- 撤稿/更正处理规则、预印本-正式版版本比对规则见 `references/source_reliability.md`。

### 阶段 2：主张清单与六类审查（约 20–35 次模型请求）

按页块阅读全文（每块 1–2 页，不超 token 预算），先建三张表（写入 `/app/work/tables.md`）：主张清单（claim_id、位置、摘录、类型）、引文清单（正文标记→参考文献条目编号映射，可借助 extract_refs 输出的正文标记索引）、数字清单（样本量、百分比、p 值及其位置）。随后逐类审查：

1. **事实核验**：数值、名称、缩写、他文结论转述；依赖外部来源的事实必须回指阶段 1 的来源状态。
2. **引用支持**：对每个引文标记判定 完整支持/部分支持/不支持/无法判定；重点识别"结论超出引文范围"的过度推断；来源状态非 verified 时 confidence ≤ medium 且 basis 写明"来源状态=X"。
3. **方法设计**：样本量与统计方法匹配、对照组、可复现性（参数、试剂、软件版本）。
4. **统计报告**：摘要/正文/表格数字交叉一致；凡可重算（百分比、合计）必须重算并把过程写入 basis。
5. **论证链**：结论跳跃、循环论证、以偏概全、相关当因果；写明缺失的中间环节。
6. **学术规范**：署名、重复发表线索、数据/代码可用性声明兑现度、伦理与利益冲突声明；**撤稿文献被继续引用归入本类且 severity 至少 major**。

每类给出 checked/partial/unchecked 覆盖状态。每条 finding 使用第 6 节 schema；`issue_type` 区分 事实错误/证据不足/规范问题/建议性意见。

### 阶段 3：核验回写与交付（脚本 + 2–4 次模型请求）

- 每条涉及引文的 finding 在 `basis` 末尾追加来源状态回执（如 `source_state[3]=verified`）。
- 自检：finding 的 `location.quote` 必须是 pages.jsonl 中对应页文本的逐字子串（允许折叠空白与断词）；写交付前逐条回查，对不上的降级 `待复核`。
- 写 `/app/output/`：`result.json`、`review_report.md`（执行摘要、来源门禁结果表、六类覆盖状态表、逐条 finding、待复核清单、局限）、`run_log.jsonl`（每行 `{"t","action","artifact","status"}`，含解析方式、快照来源、online 查询次数与时间）、`evidence/`（refs.json、source_report.json、online 原始响应副本如有）。

## 5. 异常处理

| 情况 | 处置 |
|-|-|
| PDF 无法解析/OCR 失败 | blocked 流程；说明失败原因与已尝试方法 |
| 参考文献节定位失败 | 引用清单只能基于正文标记重建，在报告与 uncertainties 中声明；来源核验整体降级 not_checked |
| 无快照且无网络 | 全部 not_checked；不判 verified；给出复核路径 |
| online 查询超时/限流 | 记录失败条目与错误，继续离线核验其余条目；不重试超过 2 次 |
| 数据库权限不足（如 Retraction Watch 需注册） | 写明权限限制与替代公开入口 |
| 发现撤稿/伪造条目 | 不删除、不静默；记入 finding（规范问题，severity≥major）并保留条目原文 |

## 6. result.json Schema

```json
{
  "case_id": "来自 case.json",
  "skill": "source-truth-gate",
  "status": "completed | partial | blocked",
  "coverage": {"事实核验": "checked", "引用支持": "checked", "方法设计": "partial", "统计报告": "checked", "论证链": "checked", "学术规范": "checked"},
  "source_gate": {"total_refs": 0, "verified": 0, "metadata_conflict": 0, "not_found_in_snapshot": 0, "suspected_fabricated": 0, "retraction_flagged": 0, "version_mismatch": 0, "not_checked": 0, "snapshot_source": "case-supplied | crossref-online | none"},
  "findings": [
    {
      "id": "F-01",
      "category": "引用支持 | 事实核验 | 方法设计 | 统计报告 | 论证链 | 学术规范",
      "issue_type": "事实错误 | 证据不足 | 规范问题 | 建议性意见",
      "severity": "critical | major | minor | advisory",
      "location": {"locator": "p.3 ¶2", "page": 3, "quote": "逐字摘录"},
      "claim": "被审查的主张或陈述",
      "verdict": "判定结论，一句话",
      "basis": "判定依据；涉及外部来源时末尾附 source_state[n]=...",
      "suggestion": "具体可执行的修改建议",
      "confidence": "high | medium | low",
      "recheck": "复核路径：命令或来源 URL + 访问日期",
      "needs_human_review": false
    }
  ],
  "unchecked_items": ["未检查项及原因"],
  "uncertainties": ["不确定性说明"],
  "artifacts": {"report": "review_report.md", "source_report": "evidence/source_report.json", "log": "run_log.jsonl"}
}
```

## 7. 参考资料

- `references/source_reliability.md`：来源等级、撤稿/更正核查流程、预印本-正式版比对规则。
- `references/verdict_states.md`：七态状态机的精确定义、触发条件与退出码语义。
- `examples/`：一个**合成示例**（synthetic，非正式案例结果），演示门禁对伪造、撤稿、版本错配条目的硬报警。
