---
name: skill-b-coverage-ledger
description: 学术规范与合规审查的过程质量控制(coverage & budget ledger)。当任务要求对论文/科研材料按 case.json 声明的审查面(引用规范、伦理审查、隐私合规、版权合规、学术诚信、投稿要求)逐面审查、交付 result.json 时使用:开工 60 秒内先落合法保底 partial result.json,把审查面实例化为检查清单,用覆盖矩阵实时对账防止漏面,未检查面如实进入 not_reviewed,覆盖率不足 100% 绝不允许 status=complete。
---

# Coverage & Budget Ledger — 过程质量控制

## 1. 用途与新增价值

审查任务最常见的失败不是判错,而是**漏面**:case 声明了 N 个审查面,实际只做了
其中几个,却在 result.json 里声称完成。本 skill 把"按材料实际存在的风险面逐项
检查、不漏项"变成机械过程:

- **实例化**:`case_intake.py` 从 case.json 的 task 字段识别声明审查面,并按材料
  内容启发式补充未声明的风险面,生成逐条可核对的 checklist.json;
- **保底**:同一脚本在开工 60 秒内先落一份合法 partial result.json(contract 字段
  齐备),此后任何中断都留下诚实部分结果;
- **对账**:`coverage_check.py` 生成覆盖矩阵,未覆盖 facet 如实写入 not_reviewed,
  并用硬性纪律保证覆盖率 <100% 时 status 绝不为 complete;
- **记账**:`budget_log.py` 追加式记录相位耗时/请求数,超阈值即给出止损建议。

方向只改变重心(覆盖与预算由脚本机械保证),**不改变交付义务**:案例声明的全部
审查面都必须完成完整审查报告;覆盖不全的面必须出现在 not_reviewed 并说明原因。

## 2. 适用条件与不适用情况

**适用**:Harbor 学术规范与合规检查类案例(/input/case.json + /input/task.md +
论文材料);尤其适用于审查面 ≥2、执行预算紧张、需要可复跑结论的场景。

**不适用**:不需要结构化 result.json 的开放式写作任务;case.json 明确只要求单一
自由文本回答且无审查面概念的任务(此时覆盖矩阵退化为单面,仍可用保底 partial 机制)。

## 3. 运行时契约与路径

| 路径 | 用途 |
|------|------|
| `/input/case.json` | 案例定义(case_id、task、materials、output_contract) |
| `/input/task.md` | 任务说明文本(审查面常在此逐条列出) |
| `/input/*` | 科研材料(论文 PDF 等,需先抽取为文本再审) |
| `/app/work` | 中间产物:checklist.json、findings.json、coverage_matrix.json、budget.jsonl |
| `/app/output` | 交付物:result.json(必须含 case_id 与 contract 全部字段) |
| `/skills/weekly-skill/scripts/` | 本 skill 的三个脚本 |
| `/skills/weekly-skill/references/` | checklist_library.md、process_gates.md |

执行预算:64 次模型请求 / 900 秒 / 每响应 16384 tokens。脚本即省预算:机械工作
(清单实例化、覆盖对账、记账)全部交给脚本,模型只做判断。

## 4. 工作流(编号步骤,命令可直接复制)

**步骤 0(门 0+1:intake 与保底,开工 60 秒内完成)**

```bash
python3 /skills/weekly-skill/scripts/case_intake.py \
  --case /input/case.json --task /input/task.md \
  --checklist-out /app/work/checklist.json \
  --result-out /app/output/result.json
python3 /skills/weekly-skill/scripts/budget_log.py \
  --log /app/work/budget.jsonl --phase intake --seconds 5 --requests 1
```

产物:checklist.json(每 facet 6–10 条检查项,状态=未开始)+ 保底 partial
result.json。若有材料文本可先行喂入启发式(`--materials /app/work/paper.txt`)。

**步骤 1(门 2:逐面审查主循环)**

按 checklist.json 逐 facet 逐条审查。每条检查项:要么产出 finding(要素见第 5 节,
quote 必须逐字出自材料),要么标记已查无问题;查不动的标 `待复核`+理由。
每完成一面:把该 facet 追加进 `/app/work/findings.json` 的 `reviewed_facets`,
并记账:

```bash
python3 /skills/weekly-skill/scripts/budget_log.py \
  --log /app/work/budget.jsonl --phase review:<facet> --seconds <估计> --requests <估计>
```

**步骤 2(门 3:覆盖对账,机械,必须执行)**

```bash
python3 /skills/weekly-skill/scripts/coverage_check.py \
  --checklist /app/work/checklist.json \
  --findings /app/work/findings.json \
  --result-in /app/output/result.json \
  --result-out /app/output/result.json \
  --matrix-out /app/work/coverage_matrix.json
```

读取输出的 `coverage_pct` 与 `uncovered_facets`:若仍有未覆盖面且预算允许,
回到步骤 1 补审;预算不足则接受 partial,未覆盖面已在 not_reviewed。

**步骤 3(门 4:compose)** 自检每条 finding:quote 逐字可定位、severity 与证据
强度匹配、类别四选一正确;待复核项与确定结论分列。

**步骤 4(门 5:终审)** 对照 output_contract.required_fields 逐字段验收
result.json;`budget_log.py --status` 看总账;确认 status 诚实后交付。

相位门完整规程(进入/退出条件与降级规则)见 references/process_gates.md。

## 5. 输出契约(result.json 与 findings 要素)

result.json 必须包含 output_contract.required_fields 的全部字段,至少:
`case_id`、`status`(complete/partial/blocked,诚实标注)、`findings`、
`not_reviewed`、`summary`、`sources`、`uncertainty`(partial 必须指明局限)、
`change_log`。

每条 finding 的要素:

```json
{
  "id": "F-001",
  "facet": "citation",
  "category": "fact_error | insufficient_evidence | norm_issue | suggestion",
  "type": "细分类型,如 citation_metadata_incomplete",
  "severity": "critical | major | minor | info",
  "location": {"file": "…", "page": 2, "section": "…", "quote": "逐字摘录"},
  "evidence": "本地规则名 / 外部来源+实际检索到的原文",
  "suggestion": "可执行修改建议",
  "verdict_status": "确认 | 待复核(+理由)"
}
```

## 6. 失败模式与止损表

| 失败模式 | 信号 | 止损动作 |
|----------|------|----------|
| 漏审整个 facet | coverage_check 输出 uncovered_facets 非空 | 补审;预算不足则 not_reviewed 如实记账,partial 交付 |
| 误声称 complete | result.json status=complete 但覆盖率<100% | 脚本自动降级 partial;人工复核为何提前收尾 |
| case.json 损坏 | case_intake notes 报"无法解析" | 按空案例骨架继续,uncertainty 说明,人工确认审查面 |
| findings 文件损坏 | coverage_check notes 报"零 findings" | 从 /app/work 历史版本恢复;恢复不了则全面 not_reviewed,partial 交付 |
| 预算预警 | budget_log 输出 over_budget=true | 立即执行止损建议:固化当前结果(coverage_check 对账)→ compose → 终审,不再开新面 |
| 材料读不出 | intake notes 报"材料不可读" | 该面进 not_reviewed(原因:材料不可读),不硬编结论 |

## 7. 降级策略(honest partial)

1. 保底 partial 永远先于实质审查落盘;中断时的最后一份 result.json 就是交付物。
2. 覆盖率 <100% → status=partial(脚本硬性保证),uncertainty 写明覆盖率与未覆盖面。
3. 未覆盖面进 not_reviewed 并注明原因(未执行/材料缺失/预算耗尽),**not_reviewed
   是合法产出,静默丢面是违规**。
4. 任何指不回原文逐字摘录的结论标 `待复核`,不凭空补结论,不编造条款与文献元数据。

## 8. 预算意识(先存 partial 再迭代)

- 模型请求只花在判断上:清单实例化、覆盖对账、记账全部脚本完成(单脚本 <5 秒)。
- 每面一审一记账;`budget_log.py` 默认预警线 48 请求 / 720 秒(总预算的 75%),
  触线即止损,先固化已覆盖面的成果。
- 迭代顺序:先保证每面至少过一遍(广度),再回头加深严重度存疑的条目(深度)——
  广度决定 status 能否升 complete,深度只影响单条 finding 质量。
