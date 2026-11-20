# 示例演练（example walkthrough）

> **示例，非正式案例结果。** 本演练使用 `examples/fixtures/` 下的**全虚构**合成夹具
> （illustrative），演示完整管线。夹具由 `scripts/selfcheck.py` 自动生成；
> 以下命令在 skill 根目录执行（设 `SKILL=$(pwd)`）。

## 场景设定（虚构）

任务：描述虚构专利 EX-1001 的权利要求 1 保护范围、给出其法律状态、并对比一篇
虚构论文 EX-2001 与一份虚构 WO 文献（OCR 合并文本）的结论。数据源三个：官方库、
Google Patents、一个订阅库。

## 步骤 0：生成诚实骨架

```bash
python3 $SKILL/scripts/scaffold_result.py \
  --case examples/fixtures/case_fixture.json \
  --out /tmp/result.json --force
# → OK: 骨架已写入 /tmp/result.json（镜像契约字段 4 个：summary,claim_chart,legal_status_table,risk_notes）
```

骨架 `status=partial`：即使后续中断，也有一份诚实的部分结果可提交。

## 步骤 1：材料文本化

真实运行时：`pdftotext -layout /input/<材料>.pdf /app/work/<材料>.txt`（按 `\f` 分页，
页码可直接用于 locator.page）；扫描件先渲染再 OCR。本示例直接使用夹具文本
（`fictional_patent_EX1001.txt` 已含 `\f` 分页，权利要求在第 2 页）。

## 步骤 2–3：登记证据并确定性回核

夹具账本 `ledger_ok.jsonl` 已含三条记录（C1 权利要求、C2 论文、C3 OCR 文献）：

```bash
python3 $SKILL/scripts/evidence_ledger.py validate \
  --ledger examples/fixtures/ledger_ok.jsonl
# → 校验通过：3 条证据记录结构与哈希均合规。

python3 $SKILL/scripts/quote_audit.py \
  --ledger examples/fixtures/ledger_ok.jsonl \
  --base-dir examples/fixtures --ocr-tolerant \
  --report /tmp/quote_audit_report.json
# → [PASS] C1 ... mode=verbatim
#   [PASS] C2 ... mode=verbatim
#   [PASS] C3 ... mode=ocr_tolerant（相似度 ≈0.98，已在报告标注）
#   引文审计全部通过（3 条）。其中容忍匹配 1 条。
```

负例演示（必须失败）：

```bash
python3 $SKILL/scripts/quote_audit.py --ledger examples/fixtures/ledger_bad_forged.jsonl \
  --base-dir examples/fixtures --ocr-tolerant ; echo "exit=$?"
# → [FAIL] B1 ... 严格匹配失败；该记录未声明 allow_ocr_tolerance=true … exit=1
```

注意 C1 的 statement 只描述**权利要求文本本身**（"权利要求 1 限定了一种包含
部件甲、乙及连接件的装置"），不把说明书里的"实施例一与二"写成授权范围——
这是"权利要求描述越界"扣分点的正面对照。

## 步骤 4：法律状态台账

夹具 `status_ok.jsonl` 含三种合规形态：官方登记查得的"未知"（配复核建议）、
聚合页线索（leads_only）、推断状态（downgraded）：

```bash
python3 $SKILL/scripts/status_ledger.py validate --ledger examples/fixtures/status_ok.jsonl
# → 法律状态台账核验通过：3 条记录合规（0 条警告）。

# 负例 1：把聚合页当登记依据 → 被拦截
python3 $SKILL/scripts/status_ledger.py validate \
  --ledger examples/fixtures/status_bad_aggregation.jsonl ; echo "exit=$?"
# → [R-S1] aggregation_page 不得作为登记依据 … exit=1

# 负例 2：未知状态配确定性措辞 → 被拦截
python3 $SKILL/scripts/status_ledger.py validate \
  --ledger examples/fixtures/status_bad_unknown.jsonl ; echo "exit=$?"
# → [R-S2] 状态为未知，statement 含确定性措辞 '已授权' … exit=1
```

## 步骤 5：数据源授权分级

```bash
python3 $SKILL/scripts/license_tiers.py classify \
  --sources examples/fixtures/sources.json --report /tmp/license_report.json
# → [GREEN]  国家知识产权局 CNIPA …
#   [YELLOW] Google Patents — 开放聚合（需注明来源）
#   [RED]    PatSnap 智慧芽 — 许可受限；降级方案：改用 CNIPA/USPTO/EPO/WIPO 替代，
#            覆盖缺口逐字段标注
```

## 步骤 6：结论风险分级

```bash
python3 $SKILL/scripts/risk_grade.py \
  --conclusions examples/fixtures/conclusions.json \
  --report /tmp/risk_report.json --checklist-md /tmp/review_checklist.md
# → [LOW]  C-low  score=10 触发规则: R-G2,R-G3,R-G4,R-G6,R-G7,R-G8
#   [HIGH] C-high score=0 触发规则: 无
```

## 步骤 7：回填 result.json

把通过闸控的结论按 `templates/result_fields.md` 的结构写入 `/tmp/result.json`
（claims 引用 quote_hash 与审计结果、risk 引用分级结果），每步追加 change_records；
C-low 这类 low 结论保持降级措辞并列入复核清单；最后把 status 从 partial 改为 ok
的前提是：回核全过、台账 validate 通过、无 R-G7 触发。

## 一键复现

```bash
python3 $SKILL/scripts/selfcheck.py   # 重新生成全部夹具并执行 11 项断言
```
