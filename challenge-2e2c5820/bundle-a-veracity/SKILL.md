---
name: veracity-anchored-feasibility-audit
description: >-
  用于"实验方案可行性评估"类任务：当需要对一份或多份候选实验方案进行可复现、可审计的可行性
  审查时使用。核心机制是证据锚定——每一条判定必须携带方案文本的逐字引文，由确定性脚本校验
  引文确为原文子串并计算偏移，无法锚定的判定一律被拒；"方案未写明"按未满足计入门槛，
  绝不视为已满足。配套矛盾扫描器对同方案内与跨版本的数值口径做启发式核查，保证结论分级
  （可行/有条件可行/不可行/无法判定）建立在可回查的证据链上。
---

# 证据锚定式可行性审查（Veracity-Anchored Feasibility Audit）

## 解决什么问题

实验方案可行性评审最常见的两类失真：其一，评审者把"方案没写 X"误当成"X 已满足"，使门槛项
（伦理、安全、预算硬顶）被静默放行；其二，方案各章节之间、以及同一方案的多个版本之间存在
数值口径矛盾而无人察觉。本技能以**证据锚定**消除第一类失真，以**确定性校验 + 矛盾扫描**
暴露第二类失真，使任何结论都能被第三方重跑复核。

## 何时使用

- 对 1 份或多份（多版本）候选实验方案做可行性评估，且案例附带组织方合同、价格、
  设备预约、参数域等素材；
- 需要输出符合 `output_contract` 的 `result.json`，且结论必须诚实标注
  complete / partial / failed；
- 任何"结论必须可回查、禁止臆造"的审查场景。

## 输入与输出契约

- 运行时输入：`/input/case.json` 与 `/input/task.md`。**case.json 的字段名不固定**，
  必须先实际读取文件，不得凭字段名标签臆断结构。
- 工作目录：`/app/work`（一切中间产物：plans.json、evidence.jsonl、锚定结果、矛盾报告）。
- 交付目录：`/app/output/result.json` 必须包含 `case_id`、`status`
  （complete/partial/failed）、`sources`、`uncertainty`、`change_record`，以及
  case.json 中 `output_contract` 声明的**全部字段**（字段形态可能是 list/dict/properties，
  assemble_result.py 会容忍三种形态；无法自动映射的字段置 null 并记 uncertainty）。
- partial 必须写明边界：缺什么材料、哪些判定未完成。

## 严格按序工作流

**步骤 0 — 建区与 inspect（1 次模型调用内完成）**
建立 `/app/work` 与 `/app/output`；通读 `/input/case.json` 与 `/input/task.md`，
用 `jq` 或肉眼列出顶层键、`output_contract` 字段清单、候选方案所在路径、合同/参数域所在
路径。把这份"结构笔记"写入 `/app/work/inspect_notes.md`，后续步骤以此为准。

**步骤 1 — 建索引**
`python3 /skills/weekly-skill/scripts/build_plan_index.py /input/case.json /app/work`
产出 `plans.json`（含每份方案的 plan_id/title/text/source_path）、
`plans.lineindex.json`（行偏移）、`materials.json`（合同/清单/参数域及其 JSON 路径）。
若退出码 3（未定位到方案），回退方案是把整份 case 序列化为单一文档，并记 uncertainty；
脚本已内置该回退。

**步骤 2 — 模型逐项判定，产出 evidence.jsonl（质量关键）**
对照 `references/audit_protocol.md` 的七约束清单，为每份方案逐类写证据条目，格式见
`references/evidence_schema.md`。铁律：
- **quote 必须逐字**——从 plans.json 的 text 字段复制粘贴，一字不差（含全角标点与空格），
  ≤120 字符；凭记忆转写必然被步骤 3 拒绝。
- **missing 必须写 absence_scope**（检索范围：哪些章节、用什么关键词、结论）。
- basis 用词表：SOP / 设备手册 / 伦理规范 / 合同 / 文献 / 计算。
- 预算类判定必须做**真实算术**（单价×数量 对合同硬顶），把算式写进 note。

**步骤 3 — 锚点校验（确定性，不耗模型调用）**
`python3 /skills/weekly-skill/scripts/verify_anchors.py /app/work/plans.json /app/work/evidence.jsonl /app/work`
退出码 2 表示存在被拒条目——逐条修复（通常是引文不逐字或缺 absence_scope）后**重跑**，
直至退出码 0。被拒判定不得以任何理由保留在台账中。

**步骤 4 — 矛盾扫描**
`python3 /skills/weekly-skill/scripts/scan_contradictions.py /app/work/plans.json /app/work/contradictions.md`
输出 (a) 方案内矛盾表 与 (b) 跨版本差异表。该扫描为纯启发式，对每条标记**回查原文**确认，
确认属实的矛盾记入结论（只记录，不擅自调和）。

**步骤 5 — 汇总分级**
依据 `references/audit_protocol.md` §3 的分级规则给出 verdict：
任何门槛项（伦理否决/安全红线/预算硬顶）fail 或 missing → 不可行；
素材缺失导致门槛无从核验 → 无法判定；
存在非门槛 missing/unknown → 有条件可行（附显式条件清单）；
全部 pass/not_applicable → 可行。
将结论、条件清单、证据统计写入 `/app/output/review_report.md`。

**步骤 6 — 装配 result.json**
```
python3 /skills/weekly-skill/scripts/assemble_result.py \
  --case /input/case.json \
  --anchors /app/work/anchors_verified.json \
  --contradictions /app/work/contradictions.md \
  --out /app/output/result.json \
  --status complete \
  --note "一审完成" \
  --sources /app/work/materials.json
```
脚本保证 output_contract 的每个字段都存在；自动映射不到的字段置 null 并记 uncertainty，
随后由模型补写这些字段（直接编辑 result.json，脚本重跑不会覆盖非空值）。

**步骤 7 — 自查清单**
- [ ] result.json 含 case_id 与 output_contract 全部字段；
- [ ] status 诚实（有任何环节未完成即 partial，并写明边界）；
- [ ] 每条判定有逐字引文且 verify_anchors 退出码 0；
- [ ] missing 条目均有 absence_scope；门槛项无一被静默放行；
- [ ] 矛盾扫描的标记已逐条回查并在结论中处理；
- [ ] sources 记录素材路径；change_record 有时间戳条目。

## 异常处理

- **缺材料**：合同/参数域/清单任一缺失 → status=partial，verdict 记"无法判定"，
  uncertainty 列明缺什么；已能判定的部分照常给出。
- **超长文档**：只对相关章节建索引并判定（在 absence_scope 与 uncertainty 中如实写明
  检索范围只覆盖哪些章节），不得假装通读全文。
- **方案自相矛盾**：记入 contradiction 报告并在分级中处理，**不擅自择一调和**。
- **PDF 输入**：先用平台自带工具提取文本再建索引；提取失败记 partial。
- **脚本退出码非 0**：读 stderr 修复输入，禁止绕过校验。

## 预算意识

目标在 **≤12 次模型调用**内完成：inspect（1）+ 证据撰写（2–3，分批）+ 被拒修复（1–2）+
矛盾回查（1）+ 结论与报告（1）+ result 补写（1）。**先存 partial**：步骤 3 一通过就立即以
status=partial 跑一次步骤 6，把当前成果落盘到 `/app/output/result.json`，再迭代完善；
脚本只会追加、绝不覆盖已有非空值。
