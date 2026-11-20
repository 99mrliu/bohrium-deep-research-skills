---
name: dualscreen-adjudicate-audit
description: >-
  系统性文献检索纳排筛选的「双人独立标注 + 分歧显式仲裁 + 全程审计链」方法。触发场景：
  案例要求双人独立筛选并报告一致性（如 Cohen's kappa）、输入材料自带冲突标注 fixture
  （文件名或键名含 annotation/conflict/reviewer/标注 等标记，如 search09 式合成重复导出
  与两位标注者意见不一致的标注）、需要分歧分类（D1 标准歧义 / D2 证据阅读 / D3 元数据缺失
  / D4 边界情形）与逐条仲裁记录、要求 PRISMA 式计数闭合与可追审计链的纳排任务。方法链：
  parse_case（盘点材料、嗅探 fixture、判定 dual_fixture/dual_model 双模式取数）→
  scaffold_result（按 output_contract 尽早落盘 result.json 骨架防超时零交付）→
  load_records（导入 JSON/JSONL/CSV/RIS 题录；fixture 原样旁路保存且仅标注为输入 fixture
  而非事实/金标准）→ exact_dedup（仅归一 DOI/题名精确合并并写台账，疑似模糊重复仅列
  uncertainty 不合并）→ prepare_sheets（生成 S1 正序 / S2 逆序两套互不可见空白标注表，
  或从 fixture 转换两组外部标注）→ validate_annotations（decision∈include/exclude/uncertain、
  reason_code 非空、evidence_quote 经 NFKC+小写+压缩空白归一后须为 title/abstract 子串，
  失败 exit 3 重锚）→ agreement（列联表 + percent agreement + 纯 Python Cohen's kappa，
  二分类与三分类各报一个，生成双方对照的分歧清单）→ 模型逐条 D1-D4 分类并仲裁
  （禁止平均/多数票掩盖实质争议，D1 须回写标准解释）→ adjudicate（校验仲裁完整与锚定，
  生成 final_labels 与 human_confirmation_required 标记）→ audit_log（audit.jsonl 逐阶段
  {stage,input_count,output_count,operator_role,basis_files,notes}，PRISMA 闭合校验
  identified=duplicates_removed+screened、screened=S1=S2、screened=included+excluded+
  needs_human，不闭合 exit 3 打印差额）→ selfcheck（终检合同字段齐、kappa 一致、分歧全仲裁、
  人工门清单一致）。边界：不联网、不声称实时数据库检索或全局召回（只有有限快照）；
  fixture 不当金标准；不伪造人工复核——D3 元数据缺失最终判定、所有 uncertain 升级记录、
  涉及未提供全文信息的判断一律只给「待复核建议」并标 human_confirmation_required: true；
  模糊去重/完整身份解析与全文精读不属本方向。
---

# dualscreen-adjudicate-audit：双人独立筛选 + 分歧仲裁 + 审计链

核心主张：纳排结论的可信度来自「两个真正独立的判断 + 分歧显式分类与仲裁 + 全程可追审计」，
而不是一次过的一言堂。任何需要人工最终确认的结论只输出「待复核建议」。

## 1. 适用场景与边界

适用：

- 案例要求双人/双视角独立筛选并报告一致性指标（一致率、Cohen's kappa）；
- 输入自带冲突标注 fixture（如 search09 式：合成重复导出 + 两位标注者意见不一致）；
- 要求分歧分类、逐条仲裁记录、PRISMA 式计数闭合与逐条理由码/证据片段。

边界（必须向用户声明）：

1. **不联网**：只处理 /input 下的有限快照材料；**禁止声称实时数据库检索或全局召回**，
   只能说「对案例提供的 N 条题录完成全量筛选」。
2. **fixture 不是金标准**：冲突标注 fixture 是输入材料（输入 fixture），两组标注仅作为
   S1/S2 外部标注载入，其分歧仍需 D1–D4 分类并仲裁；不得把任何一方当作正确答案。
3. **不伪造人工复核**：D3 元数据缺失的最终判定、所有 uncertain 升级的记录、任何涉及
   案例未提供之全文信息的判断，只能标「待复核建议」
   （final_decision=needs_human, human_confirmation_required=true），
   并在 result.json 的 uncertainty 字段显式声明「未经人工复核」。
4. **模糊去重不属本方向**：仅做归一 DOI / 归一题名精确合并；疑似模糊重复只列入
   uncertainty（suspected_pairs），绝不合并。
5. **全文精读不做**：判定只依据题录（标题/摘要/元数据）；摘要缺失即按 D3 走人工门。

## 2. 运行环境

- Python 3 标准库（json/re/csv/sys/argparse/pathlib/unicodedata/collections/math），
  无第三方依赖；全部脚本支持 `--help`、幂等（重跑覆盖同名中间产物、不追加）。
- skill 根目录定位（环境变量优先，兜底全盘查找）：

  ```bash
  SKILL="${SKILL:-$(dirname "$(find / -maxdepth 6 -name agreement.py -path '*dual-adjudication*' 2>/dev/null | head -1)")/..}"
  ```

- 退出码约定：**0**=成功；**2**=用法/IO 错误；**3**=校验失败（锚定失败、仲裁缺失、
  计数不闭合等），失败清单写文件后退出，修复后重跑同一脚本即可。
- 所有脚本顶层 try/except 兜底，绝不 traceback-crash 到非受控退出码。
- 工作目录 `/app/work`，交付目录 `/app/output`；运行时输入 `/input`。

## 3. 工作流程（高度脚本化；模型判断批量完成）

> 预算意识：64 次模型请求 / 900 秒。步骤 1–2 与全部脚本调用不占模型判断；
> 模型判断集中在步骤 4（S1/S2 标注）与步骤 6（仲裁），各一次批量请求完成。

1. **解析案例**：`python3 $SKILL/scripts/parse_case.py`
   → `/app/work/case_summary.json`（case_id、research_question、output_contract、
   材料清单、fixture 清单、mode=dual_fixture|dual_model）。
2. **尽早落盘骨架**：`python3 $SKILL/scripts/scaffold_result.py`
   → `/app/output/result.json` 含 case_id 与全部合同字段（null 占位），防超时零交付。
3. **导入与去重**：`load_records.py` → `records.jsonl`（+ fixture 时旁路
   `external_annotations.json`，原样保留）；`exact_dedup.py` → `records_dedup.jsonl`
   + `dedup_ledger.jsonl` + `dedup_summary.json`。
4. **双人独立标注（按模式二选一）**：
   - **dual_fixture**：`prepare_sheets.py` 自动把 fixture 两组标注转换为
     `annotations_s1.jsonl` / `annotations_s2.jsonl`（带 source=external_fixture
     溯源；fixture 原样副本保留）。模型**不修改其判定**，只做后续分类与仲裁。
   - **dual_model**：`prepare_sheets.py` 生成 `sheet_s1.jsonl`（正序）与
     `sheet_s2.jsonl`（逆序）两套空白表——行内只有 record_id 与空槽，
     **不含任何对方信息**。模型用**两次独立请求**分别填表：每次只能依据
     `records_dedup.jsonl` 的标题/摘要重新推导，逐条给出
     {record_id, decision, reason_code, evidence_quote}（格式见
     `templates/annotation_sheet.md`、理由码见 `rules/reason_codes.md`）。
     **明文禁令：S2 不得参照 S1 的任何结论、理由或证据**；两次请求之间不得互相引用。
     填好另存为 `annotations_s1.jsonl` / `annotations_s2.jsonl`。
   - 两份表分别跑 `validate_annotations.py --sheet <表>`：evidence_quote 归一
     （NFKC+小写+压缩空白）后必须是该记录 title/abstract 子串；uncertain 可免引用
     但 note 必填。失败清单写 `validation_errors_<表名>.json` 并 exit 3，重锚后重跑。
5. **一致性度量**：`agreement.py` → `agreement_report.json`（3×3 与 2×2 列联表、
   percent agreement、Cohen's kappa 各报一个）+ `disagreements.json`
   （逐条双方 decision/reason/evidence 对照，附题录供仲裁引用）。
6. **分歧分类与仲裁（一次批量请求）**：模型作为仲裁者阅读
   `rules/disagreement_taxonomy.md`，对 `disagreements.json` 每条写仲裁记录
   （格式见 `templates/arbitration_record.md`）：{record_id, final_decision,
   disagreement_type(D1–D4), arbitration_basis(必须引用标题/摘要片段或声明元数据缺失),
   criteria_interpretation(D1 必填，写下对标准的明确解释供全批一致适用)}，
   存 `/app/work/arbitrations.json`。**禁止用平均或多数票直接掩盖实质争议。**
   D1 产出的标准解释追加写入 `criteria_interpretations.md`（工作目录），
   并回查同类记录适用是否一致。随后 `adjudicate.py` 校验并生成
   `final_labels.jsonl` + `final_counts.json`。
7. **审计链**：`audit_log.py` → `audit.jsonl` + `audit_summary.json`；
   任一计数不闭合 exit 3 并打印差额，回查对应阶段产物。
8. **填充 result.json 并终检**：按下表把各产物字段增量填入
   `/app/output/result.json`，最后 `selfcheck.py`（exit 0 才交付）。

## 4. 输出合同映射表

合同字段名在写 skill 时未知，运行时从 `case_summary.json` 的 output_contract 逐字段填充。
按字段名语义映射（同名/近义字段均按下表取数）：

| 合同字段语义（名含关键词） | 数据来源 |
|---|---|
| case_id / 标识 | case_summary.json |
| research_question / 问题 | case_summary.json |
| identified / 导入总数 | dedup_summary.json: identified |
| duplicates / 去重 | dedup_summary.json: duplicates_removed（+dedup_ledger.jsonl 台账） |
| screened / 筛选数 | dedup_summary.json: screened |
| included / excluded | final_counts.json |
| needs_human / human / 复核 | final_counts.json: human_confirmation_required_ids（清单逐条含 record_id 与理由） |
| agreement / 一致率 | agreement_report.json: percent_agreement |
| kappa（binary/二分类） | agreement_report.json: binary_include_vs_rest.kappa（附列联表） |
| kappa（three/三分类） | agreement_report.json: three_class.kappa（附列联表） |
| disagreement / 分歧 | disagreements.json 全文 + 按 D1–D4 统计分歧类型计数 |
| arbitration / 仲裁 | arbitrations.json 全文（逐条 final_decision、类型、依据、D1 标准解释） |
| final_labels / 筛选结果 / decisions | final_labels.jsonl 全量（含 reason_code 与 evidence_quote） |
| audit / 审计 / 链路 | audit.jsonl 各阶段条目 + audit_summary.json 闭合结论 |
| uncertainty / 局限 | suspected_pairs + human_confirmation_required 清单 + 固定声明：「仅基于案例有限快照，未做实时数据库检索，不保证全局召回；fixture 为输入材料而非金标准；needs_human 记录仅为待复核建议，未经人工复核确认。」 |

## 5. 异常处理表

| 异常 | 处理 |
|---|---|
| 无冲突 fixture（多数案例） | 走 dual_model 双视角模式（S1 正序 / S2 逆序，两次独立请求） |
| fixture 格式异常 / 标注组不足两组 | prepare_sheets exit 3；降级为 dual_model 模式，并在 result.json 的 uncertainty 中显式声明降级原因 |
| fixture 标注指向已被去重/不存在的记录 | 丢弃并写 fixture_dropped.json，审计链 notes 记录条数 |
| evidence_quote 锚定失败 | validate_annotations exit 3 + validation_errors_*.json；回到题录重新摘录原文片段后重跑 |
| S1/S2 表条数或 record_id 集合不一致 | agreement exit 3，打印仅单侧存在的 record_id；补齐后重跑 |
| 仲裁缺失 / 类型非法 / basis 无锚定 | adjudicate exit 3 + adjudication_errors.json；补齐仲裁后重跑 |
| 计数不闭合 | audit_log exit 3 打印各等式差额；回查对应阶段产物 |
| selfcheck 失败 | 按 FAIL 行逐项修复；exit 0 前不得交付 |

## 6. 最小调用示例

`examples/` 内含**合成虚构**示例（example_case.json、example_records.jsonl 9 条虚构记录
含 1 对精确重复与 1 条空摘要、example_fixture_annotations.json 两位虚构标注者含 3 处分歧、
filled_s1/s2.jsonl、filled_arbitrations.json 覆盖 D1 与 D3、example_walkthrough.md 逐步
命令、selftest_log.md 自测记录）。所有示例数据均为虚构，仅演示格式，不代表真实文献。

最小流程（dual_model 模式）：

```bash
SKILL=/path/to/skill-c-dual-adjudication
python3 $SKILL/scripts/parse_case.py --input-dir /input --work /app/work
python3 $SKILL/scripts/scaffold_result.py --work /app/work --output-dir /app/output
python3 $SKILL/scripts/load_records.py --input-dir /input --work /app/work
python3 $SKILL/scripts/exact_dedup.py --work /app/work
python3 $SKILL/scripts/prepare_sheets.py --work /app/work
# 模型两次独立请求填表 -> annotations_s1.jsonl / annotations_s2.jsonl
python3 $SKILL/scripts/validate_annotations.py --work /app/work --sheet /app/work/annotations_s1.jsonl
python3 $SKILL/scripts/validate_annotations.py --work /app/work --sheet /app/work/annotations_s2.jsonl
python3 $SKILL/scripts/agreement.py --work /app/work
# 模型一次批量请求写 arbitrations.json
python3 $SKILL/scripts/adjudicate.py --work /app/work
python3 $SKILL/scripts/audit_log.py --work /app/work
# 填充 /app/output/result.json 各合同字段
python3 $SKILL/scripts/selfcheck.py --work /app/work --output-dir /app/output
```

## 7. 维护信息

- 版本：v1.0.0（2026-11-20）
- 许可证与仓库：见 GITHUB_URL.txt
- 变更策略：脚本接口（输入/输出文件名、退出码）向后兼容；分歧分类法 D1–D4 如需扩展，
  仅追加新类型，不改写既有类型语义。
