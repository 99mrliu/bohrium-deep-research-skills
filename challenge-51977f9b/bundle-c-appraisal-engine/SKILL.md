---
name: slr-appraisal-engine
description: >
  系统性文献综述技能，签名能力为"质量评价方法学引擎"：把偏倚风险量表声明为
  可读、可版本化的 JSON（维度×等级×权重×分级规则），强制每条逐维度判定携带
  原文依据定位（basis_location + verbatim basis_quote），由脚本确定性重算加权
  总分与风险等级，并在综合结论前执行敏感性分析——剔除高风险研究后重算每条
  论断的支撑（stable/weakened/unsupported），使"等级如何影响结论"显式可核。
  治理"质量评价只剩一句'质量较高'"的失败模式。同时覆盖完整综述链：问题拆解、
  检索、纳排筛选、证据综合与结论标注。边界：不替代方法学家做量表内容设计
  （提供协议与默认值），不访问外部数据库（检索结果由案例材料或 Agent 给出）。
---

# slr-appraisal-engine —— 声明式量表 + 确定性评分 + 结论敏感性分析

## 1. 适用场景与边界

**适用**：系统性综述/Meta 分析任务，尤其要求"质量评价逐维度、有依据、
等级影响结论可复核"的场景；纳入研究为 RCT、观察性研究或已有综述
（分别按 RoB2 / ROBINS-I / AMSTAR2 思路配量表，见
`references/rubric_design.md`）。

**边界**：
- 脚本只做可确定性的事（校验量表、核验依据子串、重算评分、重算结论
  支撑）；逐维度判定的**判断**由模型完成，但必须落到 JSONL 并过脚本。
- 脚本不联网、不解析 PDF；全文文本（pdftotext / OCR 产物）须先行备妥，
  每纳入研究一个 `<record_id>.txt`。
- 量表内容设计给协议与默认值，最终维度/权重由模型结合研究问题确定并留痕。

## 2. 运行环境

- 纯 Python 3 标准库；无第三方依赖。
- 脚本定位兜底（评测器将 skill 安装至 `/skills/weekly-skill`，若路径不明）：

```bash
find / -maxdepth 5 -name "appraise.py" -path "*appraisal*" 2>/dev/null
```

  找到后，以该文件所在目录的上一级为 `$SKILL`（脚本在 `$SKILL/scripts/`）。
- 退出码约定（全部脚本一致）：**0=通过；2=输入/材料不足（诚实降级）；
  3=校验失败（违反规则）**。错误信息带规则码（R1–R4、A1–A3、S1–S2、E0/E2/E3）。
- 每个脚本支持 `--help`。

## 3. 工作流程（编号步骤，脚本优先）

> 预算纪律：一切可确定性做的交给脚本；模型只做判断、解读与写作。
> **第 2 步就把 result.json 骨架落盘**，之后每步增量填充。

1. **读案例**：读 `/input/case.json` 与 `/input/task.md`，确认 case_id、
   output_contract 字段、随案材料（题录、PDF 等）。
2. **解析 + 保底脚手架**（两条命令，模型请求之外完成）：
   ```bash
   python3 $SKILL/scripts/parse_case.py --case /input/case.json \
     --task /input/task.md --out /app/work/case_summary.json
   python3 $SKILL/scripts/scaffold_result.py --case-summary \
     /app/work/case_summary.json --out /app/output/result.json
   ```
3. **研究问题结构化拆解**：按 PICO/PECO 拆问题（人群、干预/暴露、对照、
   结局、研究设计），写入 `product.protocol` 并留痕 change_records。
4. **检索式构造**：逐数据库给检索式（字段、布尔逻辑、同义词/主题词、
   时间与语言限制、每段意图）；检索结果进 `sources`，计数进 `counts`。
   （检索执行由案例材料或 Agent 环境承担，本 skill 规范其记录格式。）
5. **条款化纳排 + 两轮筛选**：把纳入/排除标准写成可判定条款；题录轮、
   全文轮各留判定记录（含排除原因），计数进 `counts`
   （如 `{"retrieved":…,"title_screened":…,"fulltext_assessed":…,
   "included":…}`）。
6. **【签名环节】质量评价**，子步骤 6a–6f：
   - 6a **选/配量表**：按纳入研究类型查 `references/rubric_design.md`，
     形成 `/app/work/rubric.json`（维度×等级×权重×grade_rules，
     implication 必填，写法见 `references/grade_rules.md`）。
   - 6b **量表校验**：
     `python3 $SKILL/scripts/rubric_check.py --rubric /app/work/rubric.json`，
     必须 exit 0；R1–R4 任一违规先修量表。
   - 6c **模型逐维度判定**：对每篇纳入研究 × 每维度输出一行
     `{record_id, dim_id, level_id, basis_location, basis_quote}`；
     `basis_quote` 必须是 `basis_location` 所指源文本的 **verbatim**
     子串（可复制粘贴，禁止改写）。写入 `/app/work/appraisals.jsonl`。
   - 6d **确定性评分定级**：
     ```bash
     python3 $SKILL/scripts/appraise.py --rubric /app/work/rubric.json \
       --appraisals /app/work/appraisals.jsonl --sources /app/work/sources \
       --included /app/work/included.json --out /app/work/appraisal_report.json
     ```
     exit 0 才可继续；报告含每研究 `scores_per_dim/total/grade/basis_map`。
   - 6e **综合写作执行"高风险不作主证"纪律**：组织候选结论 claims
     （每条 ≥1 条支撑研究，写入 `/app/work/claims.jsonl`）；主证只能来自
     low 级研究，some_concerns 需低危复核，high 只作佐证。
   - 6f **敏感性分析**：
     ```bash
     python3 $SKILL/scripts/sensitivity.py --appraisal \
       /app/work/appraisal_report.json --claims /app/work/claims.jsonl \
       --min-support 1 --out /app/work/sensitivity_report.json
     ```
     按 stable/weakened/unsupported 标注每条结论；**unsupported 论断必须
     改写或移入 uncertainty**（格式见 `references/sensitivity_guide.md`）。
7. **完成综述链其余环节**：带证据回链写综合结论（每条结论括注支撑研究
   及其等级）；冲突证据与研究空白单列一节；对关键陈述做
   事实/推断/无法确定三分。
8. **组装 result.json**：按第 4 节映射表填充各字段；评价报告、敏感性
   报告（json+md）作为可复核制品一并放入 `/app/output/`。
9. **自查**：按第 6 节逐条核对，结果写入 `checks`，status 定
   complete/partial/failed。

## 4. 输出合同映射表（result.json 每个字段从哪来）

| 字段 | 来源 |
|---|---|
| case_id | case_summary.json |
| skill_name | 固定 `slr-appraisal-engine`（脚手架已写入） |
| status | 第 9 步自查后定；骨架期 partial |
| product | 第 3、7 步：协议（PICO、检索式、纳排条款）、综合结论正文（结论按 stable/weakened/unsupported 标注）、冲突证据与研究空白、事实/推断/无法确定三分 |
| evidence_matrix | appraisal_report.json 的 `studies[]`（每研究 scores_per_dim/total/grade/basis_map：逐维度判定+依据定位+quote）+ sensitivity 标注后的 claims |
| sources | 检索记录（数据库、检索式、命中数）+ 纳入研究清单与材料路径 |
| uncertainty | 量表选择争议、weakened/unsupported 论断（references/sensitivity_guide.md 第 3 节格式）、题录级降级评价、事实/推断/无法确定中的"无法确定"项 |
| change_records | 量表版本变更、判定修订、结论改写等关键决策 |
| counts | 检索/筛选/纳入/判定计数 + appraisal_report.counts + sensitivity summary |
| checks | 第 6 节自查结果（键值对，含 no_high_grade_as_primary_evidence 等） |

## 5. 异常处理（逐条处置）

1. **检索为空**：先放宽检索式一轮（去时间/语言限制、扩同义词）并留痕；
   仍为空则 status=partial，`product` 写明"未检索到符合条件的研究"，
   uncertainty 说明检索式与可能原因，不得编造文献。
2. **数据库或接口超时**：记录失败的数据库与时间，用已得结果继续；
   uncertainty 标注覆盖缺口；不伪造命中数。
3. **全文不可得（签名环节的诚实降级）**：appraise.py 在 sources 目录
   缺失或某研究无源文件时 exit 2。处置：有全文的照常评价；无全文的
   研究只允许**题录级线索评价**（标题/摘要可见信息），且其 grade
   **上限 some_concerns**，判定行注明"bibliographic-only"，
   uncertainty 写明降级范围；若全部无全文，则跳过 6c–6f，status=partial
   并说明"质量评价降级为题录级"。
4. **术语同义歧义**：检索式中并列同义词/主题词/自由词并注明；筛选与
   提取遇到歧义术语时按纳排条款的明确定义裁决，裁决记入 change_records。
5. **纳排条款冲突**：以研究问题（PICO）为最高裁决依据，修订条款并
   版本化留痕；受影响的已筛记录重判。
6. **纳入证据互相矛盾**：不得和稀泥；在 product 单列"冲突证据"节，
   按等级构成分析（若矛盾仅来自 high 级研究，以 low 级结论为准并说明），
   无法解释的矛盾进 uncertainty。
7. **权限不足**（文件/目录不可写等）：换可写目录（/app/work、/tmp）
   重试；仍失败则 status=failed 并如实记录系统报错。
8. **超时**：立即把已完成的 result.json 增量落盘（status=partial，
   status_reason 写明完成到哪一步），优先保证骨架+已算制品交付。
9. **量表与研究类型错配**（如把 RoB2 思路套到观察性研究）：判定时
   发现维度普遍不适用即停，按 references/rubric_design.md 重选量表、
   升版本号、重做受影响判定，记入 change_records。
10. **判定依据找不到原文**（appraise.py A2 exit 3）：按脚本给出的
    "最接近候选位置"提示回原文核对，修正 basis_location/basis_quote
    为 verbatim 子串后重跑；禁止把 quote 改成"大意"。
11. **结论全部 unsupported**：如实交付——status=partial，product 写明
    "剔除高风险研究后现有证据不足以支撑任何候选结论"，全部论断按
    references/sensitivity_guide.md 格式移入 uncertainty；禁止放宽量表
    阈值迁就结论。

## 6. 自查方法

交付前逐条核对并写入 `checks`：

1. `python3 $SKILL/scripts/selfcheck` 通过（exit 0）。
2. rubric_check exit 0；rubric.json 版本号与实际使用一致。
3. appraise exit 0；evidence_matrix 中每研究 × 每维度有 level + 依据
   定位 + verbatim quote（抽查 3 条 quote 回原文可定位）。
4. sensitivity exit 0；结论区**零** unsupported 论断残留；
   `no_high_grade_as_primary_evidence = true`。
5. result.json 含 output_contract 全部字段；counts 各计数互相一致
   （retrieved ≥ screened ≥ included 等）。
6. uncertainty 非空项均可溯源；partial/failed 均有原因说明。

## 7. 最小调用示例（可直接复制执行）

```bash
SKILL=${SKILL:-/skills/weekly-skill}
mkdir -p /app/work /app/output
# 解析 + 骨架
python3 $SKILL/scripts/parse_case.py --case /input/case.json \
  --task /input/task.md --out /app/work/case_summary.json
python3 $SKILL/scripts/scaffold_result.py --case-summary \
  /app/work/case_summary.json --out /app/output/result.json
# 量表校验（rubric.json 由模型按 references/rubric_design.md 编写）
python3 $SKILL/scripts/rubric_check.py --rubric /app/work/rubric.json
# 评分定级（appraisals.jsonl 由模型逐维度判定产出）
python3 $SKILL/scripts/appraise.py --rubric /app/work/rubric.json \
  --appraisals /app/work/appraisals.jsonl --sources /app/work/sources \
  --included /app/work/included.json --out /app/work/appraisal_report.json
# 敏感性分析
python3 $SKILL/scripts/sensitivity.py --appraisal /app/work/appraisal_report.json \
  --claims /app/work/claims.jsonl --min-support 1 \
  --out /app/work/sensitivity_report.json
# 自检
python3 $SKILL/scripts/selfcheck
```

examples/ 下有完整合成示例（合成示例 / synthetic, illustrative），
含手算评分对照，见 `examples/README.md`。
