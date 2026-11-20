# design-typed-itembank-assessor

量表驱动的研究设计分型条目化文献质量评价 Skill。对一批科学文献产出
**"维度—条目—判断—证据—等级"** 的可复核评价表：脚本做重活（抽取、分型、
候选检索、引用门控、阈值分级），模型只做判断，不抄写长文。

## 安装与依赖

- Python ≥ 3.8，**仅标准库**。
- `pdftotext`（poppler-utils，PDF 文本抽取；缺失时自动回退 pypdf，再失败标记 failed）。
- 无网络访问需求。安装方式：把本目录整体复制到 `/skills/weekly-skill`
  （或任意位置，所有路径参数化，不硬编码安装路径）。

## 完整调用步骤

```bash
python3 scripts/extract_corpus.py --case /input/case.json --task /input/task.md \
    --input-dir /input --work /app/work --output /app/output
python3 scripts/classify_design.py --work /app/work
python3 scripts/match_evidence.py --work /app/work --top-n 5
# —— 模型批阅：读 work/candidates/*.json，回 work/pages/ 原文核对，
#    按 templates/assessment_row.md 写 work/assessments/<doc_id>.jsonl ——
python3 scripts/verify_quotes.py --work /app/work
python3 scripts/aggregate_grade.py --work /app/work
python3 scripts/build_result.py --case /input/case.json --work /app/work --output /app/output
```

端到端合成示例见 `examples/example_walkthrough.md`（示例，非正式案例结果）。

## 输入

- `/input/case.json`：case_id（case_id/id/caseId 递归查找）；文献清单
  （documents/papers/references/files/literature/corpus/materials 递归查找，
  元素为路径或含 path/file/pdf/url/title 的字典）；output_contract
  （output_contract/contract/output_fields/required_fields，原样镜像进结果）。
  清单缺失时按 `*.pdf → *.txt → *.md → *.json` 扫描输入目录。
- `/input/task.md`：具体要求，优先于通用流程。
- 文献材料：PDF（pdftotext -layout，按 `\f` 分页）、txt/md（直接读）、
  Crossref/EuropePMC JSON 快照（提取 title/abstract 作 abstract_only 文档）。

## 输出

- `/app/output/result.json`：case_id、status、镜像契约字段、documents
  （分型+置信+信号、等级+推导链+计数、条目判断含 quote/locator/rationale/
  verification）、sources（含 sha256）、uncertainties、change_records、
  verification_summary。失败点之前已存在 status=in_progress 部分版本。
- `/app/output/assessment_table.md`：人读评价表。
- `/app/output/verify_report.json`：门控校验报告。

## 关键方法

1. **设计分型**：关键词加权打分（多词强信号权重 3），置信度 = top/(top+次+1)，
   分差小或总分低标 uncertain 交模型裁决，修正写 design_overrides.json 留痕。
2. **条目库**：`itembank/` 下按设计类型分组；通用 10 条（研究设计/样本与抽样/
   测量与结局/统计分析/报告完整性五维度）+ 类型特有 4–7 条；每条定义所需证据
   与不可评价条件、是否核心条目。
3. **证据锚定**：所有判断强制 verbatim 摘录 + `p<页>.¶<段>` 页锚；门控脚本以
   归一化（NFKC、去 `-\n` 断词、去全部空白、casefold）子串匹配校验摘录真伪，
   失败自动降级 not_assessable 并留痕。
4. **阈值分级**：`rules/grading_thresholds.md` 明文规则 R0–R6（核心条目
   not_met 数、not_assessable 占比、仅摘要封顶 moderate），输出等级 + 推导链，
   禁止孤立等级标签。
5. **弃权**：全文不可得/解析失败/图表不可解析时对应条目 not_assessable，
   解析失败文献单列，不编造。

## 适用场景

多文献离线质量评价、偏倚风险初筛、报告完整性核查、需要可复核证据链的文献评审。
**不适用**：单篇统计数值复算、图表像素级解读、双人独立评价仲裁
（后两者属于其他方向的 Skill）。

## 限制

- 分型为启发式，低置信必须模型裁决；other/unassessable 类型只用通用条目。
- PDF 分页依赖 pdftotext 的 `\f`；扫描版 PDF 无文本层时整篇 failed。
- 条目关键词检索是召回辅助，不保证覆盖所有相关段落；判断以模型通读候选为准。
- 正文词数 < 500 的 txt/md 按 abstract_only 处理（启发式阈值）。

## 失败处理

任何输入缺失不崩溃：错误写入 uncertainties；result.json 在抽取阶段即落盘部分
版本；门控校验失败的判断降级而非删除；零文献时 status=failed 且结果文件仍存在。

## 自查方法

见 SKILL.md 第九节：py_compile、合成 fixture 全链路冒烟、抽查门控通过记录、
核对推导链、核对契约字段镜像。
