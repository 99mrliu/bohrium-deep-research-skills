---
name: claim-evidence-governance-auditor
description: >-
  专利与技术文献检索的证据治理与风险分级审计器。当任务涉及：专利权利要求保护范围的描述
  （须严格区分授权权利要求与说明书内容）、法律状态核验（登记优先、查询日期、未知纪律）、
  同族与状态结论的证据定级、数据源授权边界与合规展示（绿/黄/红分级）、以及结论的引文闸控
  （每条论断必须携带逐字引文+定位并可被确定性回核）时使用本 Skill。兼容 Harbor 运行时契约
  （/input/case.json + /input/task.md，产物写入 /app/output，result.json 镜像 output_contract
  全部字段并携带诚实的 status/sources/uncertainty/change_records）。
---

# Claim Evidence Governance Auditor（权利要求证据治理与风险分级审计器）

## 1. 用途与适用条件

本 Skill 解决专利/技术文献检索任务中的**证据治理**问题：任何出现在最终输出里的论断
（保护范围、法律状态、同族关系、文献结论）都必须是**引文闸控**的——携带逐字引文 +
定位（文件/页/行），并由脚本确定性回核引文真实存在于来源文本；法律状态走**官方登记
优先**协议；数据源按授权**绿/黄/红分级**并给出能力降级方案；每条结论带**风险分级**
与人工复核建议。

适用触发条件（命中任一即应启用）：
- 需要描述某件专利的权利要求保护范围（尤其要区分授权权利要求 vs 说明书实施例）；
- 需要陈述某件专利/申请的法律状态（授权/失效/撤回/驳回/审中/未知）；
- 需要基于"观察到的链接"谈同族关系（注意：观察到的链接**不构成完整同族**）；
- 检索结果来自多种数据源，需要判断哪些能抓取、能展示、能留存；
- 需要输出可审计、可分级的结论（每条结论标注证据强度与置信等级）。

## 2. 输入（Harbor 运行时契约）

- `/input/case.json`：含 `case_id` 与 `output_contract`（输出契约，result.json 必须镜像其全部字段）。
- `/input/task.md`：任务说明（号码查询或主题查询）。
- 材料文件：按题目提供，可能在 `/input`、`/app/work` 或当前目录。**PDF 为原始 PDF
  （无预抽取答案层）**，必须用 `pdftotext` / PDF 渲染 / OCR 读真实内容，
  **严禁按文件名标签臆测内容**。WO 文献可能是 OCR 合并文本（页边界已保留）。
- 工作目录 `/app/work`；最终结果与可编辑产物放 `/app/output`。
- 执行预算：64 次模型请求、900 秒、每响应 16384 tokens（含推理）。**重活全部交给脚本，
  模型只做判断与写作；开工即先落诚实的 partial 骨架，再迭代改进。**

## 3. 调用方式（按顺序的确切命令）

设 `SKILL=/skills/weekly-skill`（评测安装路径；本地开发时为 skill 根目录），
工作目录 `/app/work`。

```bash
# 步骤 0：开工即生成诚实骨架（保证任何中断都有可提交的 partial 结果）
python3 $SKILL/scripts/scaffold_result.py --case /input/case.json --out /app/output/result.json

# 步骤 1：材料文本化（PDF → 文本；扫描件先渲染再 OCR）。pdftotext 按 \f 分页，页码可对到 locator.page
pdftotext -layout /input/<材料>.pdf /app/work/<材料>.txt
# 无文本层的扫描件：先渲染为图像再用 OCR 工具，输出存 /app/work/<材料>.ocr.txt，
# 后续引用它的证据记录必须 source_kind=patent_pdf_ocr 或 ocr_merged 且 allow_ocr_tolerance 视质量开启

# 步骤 2：登记证据账本（每条论断一条记录；quote 必须逐字照录来源文本）
python3 $SKILL/scripts/evidence_ledger.py append --ledger /app/work/evidence_ledger.jsonl \
  --claim-id C1 --statement "<论断>" --quote "<逐字引文>" \
  --file /app/work/<材料>.txt --page 2 --source-kind patent_pdf_text
python3 $SKILL/scripts/evidence_ledger.py validate --ledger /app/work/evidence_ledger.jsonl

# 步骤 3：确定性引文回核（伪造/错位即 exit 非 0；含 OCR 文本时加 --ocr-tolerant）
python3 $SKILL/scripts/quote_audit.py --ledger /app/work/evidence_ledger.jsonl \
  --base-dir /app/work --ocr-tolerant --report /app/output/quote_audit_report.json

# 步骤 4：法律状态台账（登记优先协议；聚合页只能 leads_only；未知必须配复核建议）
python3 $SKILL/scripts/status_ledger.py append --ledger /app/work/status_ledger.jsonl \
  --entity "<公开号>" --status-value 未知 --source-kind official_register \
  --query-date "$(date +%F)" --as-register-basis \
  --review-advice "到官方登记簿复核最新状态并记录查询日期"
python3 $SKILL/scripts/status_ledger.py validate --ledger /app/work/status_ledger.jsonl

# 步骤 5：数据源授权分级（红级源禁止抓取，给出绿色替代与覆盖缺口）
python3 $SKILL/scripts/license_tiers.py classify --sources /app/work/sources.json \
  --report /app/output/license_report.json

# 步骤 6：结论风险分级（每条结论 high/medium/low + 触发规则 + 人工复核清单）
python3 $SKILL/scripts/risk_grade.py --conclusions /app/work/conclusions.json \
  --report /app/output/risk_report.json --checklist-md /app/output/review_checklist.md

# 步骤 7：把通过闸控的结论增量写入 /app/output/result.json（保留 status=partial
# 直到全部核验通过；未完成的界限写入 uncertainty，每步追加 change_records）
```

## 4. 输出字段（/app/output/result.json）

骨架由 `scaffold_result.py` 生成并**镜像 output_contract 全部字段**，另含：
- `case_id`：照录 case.json；
- `status`：`ok / partial / failed`，必须诚实；部分完成必须在 `uncertainty` 说明界限；
- `claims`：每条结论对象，含 `statement`、`evidence`（指向账本 claim_id 与 quote_hash）、
  `risk`（grade + 触发规则）；
- `legal_status`：状态台账引用，状态值必须带 `query_date` 与 `source_kind`；
- `authorization`：数据源分级结果（tier、可展示字段、留存限制、降级方案）；
- `sources`：全部来源（含查询日期）；
- `uncertainty`：不确定性清单（状态未知、OCR 存疑、语料缺口等）；
- `change_records`：变更记录（每步追加，含时间戳）。

字段细则见 `templates/result_fields.md`；账本格式见 `templates/ledger_format.md`。

## 5. 关键方法（指向 rules/）

- `rules/legal_status_protocol.md`：登记优先、查询日期纪律、滞后与 unknown 纪律。
- `rules/authorization_boundary.md`：绿/黄/红分级规则表与能力降级方案。
- `rules/risk_grading.md`：风险触发规则与 high/medium/low 口径。

## 6. 案例路由

| 案例类型 | 判定信号 | 管线 |
|---|---|---|
| 权利要求/法律状态类（全管线） | task 要求描述保护范围、给定法律状态、谈同族/有效性 | 步骤 0–7 全走：每条结论必须引文闸控 + 状态走登记优先协议 + 风险分级 |
| 号码查询类（轻量模式） | task 给出号码要求检索与整理 | 步骤 0、1、2、3、6：**每条命中记录仍须引文闸控**（著录项目引用原文行）+ 风险分级；状态字段若无法核官方登记则一律填"未知"+查询日期 |
| 主题查询类（轻量模式） | task 给主题词要求检索对比 | 同号码类；对比结论（与科学论文的异同）必须逐条挂引文，禁止凭印象概括 |

轻量模式可以省略的仅是"完整权利要求对照表"这类重产物，**引文闸控与风险分级不可省略**。

## 7. 异常处理表

| 异常 | 信号 | 处理 |
|---|---|---|
| 引文核验失败 | quote_audit exit 非 0 | 该论断**不得进入输出**；回到来源文本重新照录逐字引文并修正定位；确系 OCR 质量的，开启 allow_ocr_tolerance 并在结论降级 |
| 状态冲突 | 两个来源状态不一致 | 以 official_register 为准；聚合页只记为线索；冲突写入 uncertainty |
| 状态未知 | 无官方登记可查 | status_value=未知，措辞必须不确定（"截至查询日期……未知"），配 review_advice；台账规则引擎会拦截确定性措辞 |
| 授权不足 | license_tiers 判红 | 禁止抓取/批量下载/二次分发；用绿色官方源替代；覆盖不了的字段在输出中显式标注"覆盖缺口"并降级结论 |
| OCR 不确定 | 容忍匹配通过但相似度接近阈值 | match_mode=ocr_tolerant 必须出现在报告与结论标注中；触发 R-G5，建议人工比对原件渲染页 |
| 语料覆盖缺口 | 有限语料未覆盖全部查询目标 | corpus_coverage=partial/unknown；结论限缩到已覆盖范围；缺口清单写入 uncertainty |

## 8. 自查方法

```bash
python3 $SKILL/scripts/selfcheck.py    # 11 项正/负例断言，全部通过 exit 0
```

自测使用 `examples/fixtures/` 下的**全虚构**合成夹具（标注"示例，非正式案例结果"），
覆盖：引文回核正/负例、OCR 容忍闸控、聚合页拦截、未知纪律拦截、授权分级、风险分级、
契约镜像。修改任何脚本后必须重跑自测。

## 9. 最小调用示例

完整可运行示例见 `examples/example_walkthrough.md`（基于虚构夹具逐步演示）。
30 秒冒烟：

```bash
cd $SKILL
python3 scripts/selfcheck.py && echo SELF-CHECK OK
```

## 10. 纪律红线（违反即典型扣分）

1. **绝不把说明书实施例当作授权权利要求**来描述保护范围；
2. **绝不把聚合转载页当作法律状态的登记依据**（只能作线索并标注）；
3. 每条法律状态结论**必须带查询日期**；当前官方状态核不到就如实标 **未知**；
4. **绝不对受限库（红级）尝试抓取**；
5. 每条结论必须标注**证据强度/风险等级**；观察到的链接不表述为"完整同族"；
6. 绝不预置案例答案；不得按文件名臆测材料内容，必须读真实文件。
