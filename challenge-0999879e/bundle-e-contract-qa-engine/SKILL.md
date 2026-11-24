---
name: contract-qa-engine
description: 契约驱动的论文审查交付工程与过程质控技能——以 output_contract 为最高纲领解析契约字段、生成答题纸、对候选 findings 做机械复核与误报抑制（锚点复验/枚举校验/豁免词表）、诚实门终检并原子落盘 result.json；适用于评测/交付场景下要求结构化可复验审查结果（含 case_id 与契约全部字段、编号稳定、留痕可审计）的论文质量审查任务；不适用于替代 Agent 的领域判断（深查靠契约驱动的过程控制保证，事实性深度结论仍需 Agent 撰写候选清单），也不适用于无 output_contract 交付要求的自由评述写作。
---

# contract-qa-engine：契约驱动的审查交付工程与过程质控

## 核心思想

审查质量一半在"审"，一半在"交"。本技能是**流程骨架**：

1. **契约先行**：第一次脚本调用就解析 `/input/case.json` 的 output_contract
   （list/dict 宽容解析，不识别则回退默认字段集并记 uncertainty），生成
   答题纸（每个契约字段一格，含填写状态），并立刻写出保底 partial
   result.json——之后任何中断都有可交付物。
2. **六分面轮查**：事实核验、引用支持、方法设计、统计报告、论证链、
   学术规范，全部按 `references/facet_coverage.md` 的最低检查点轮查一遍，
   状态值四选一（checked_clean / issues_found / partially_checked /
   unable_to_check），不许跳过、不许谎称 checked_clean。
3. **两 Pass 误报抑制**：Agent 写候选清单（Pass 1），脚本机械复核（Pass 2）：
   必填字段齐全、severity/type/facet 枚举合法、original_text 空白归一化后
   在抽取文本中锚点复验、学科惯例豁免词表命中提示 recheck、type-facet
   一致性检查。每条 finding 必须能答"删掉哪句原文这条就不成立"。
4. **诚实门终检**：契约字段全覆盖；null 无 null_reasons → 降 partial；
   pending_review 不凭空补结论；抽取错误如实记录。
5. **稳定可复验**：findings 编号 F001… 按排序后位置稳定分配，同一稿件
   重复运行 schema 与编号不变；result.json 原子写入（临时文件+rename），
   输入文件带 SHA-256，他人可逐条复验。

深查能力来自契约驱动的过程控制与误报抑制，而非脚本的领域判断：
Agent 负责按检查点撰写候选 findings，脚本负责把住交付质量关。

## 适用边界

- 适用：有 `/input/case.json`（含或不含 output_contract）与稿件材料的
  结构化论文审查交付；要求结果可复验、编号稳定、降级留痕的评测场景。
- 不适用：① 不需要结构化交付的自由评述；② 期望脚本自动发现具体问题——
  脚本不做领域判断，问题发现由 Agent 按六分面检查点完成；③ 文献内容
  真实性核验（联网查证超出本技能范围，核对不了的如实记 partially_checked）。

## 运行时契约

- 技能安装于 `/skills/weekly-skill`，脚本以
  `python3 /skills/weekly-skill/scripts/xxx.py` 调用，仅用 Python 3 标准库。
- 输入：`/input/case.json`（schema 未知，宽容解析）、`/input/task.md`、
  稿件材料（MD/TXT/TeX 直读；PDF 尝试 `pdftotext`，`shutil.which` 检测，
  没有则如实记录 extract_error；DOCX 尽力 zipfile 抽取）。统一 utf-8、
  errors=replace。
- 工作目录 `/app/work`；最终成果 `/app/output/result.json`
  （必须含原 case_id 与 output_contract 全部字段）+ `review_report.md`。
- 预算紧：第一步就产出保底 partial result.json，之后增量改进。
- 禁止编造文献、页码、DOI、结论、分数；无法确认的条目 pending_review。

## 分步工作流（5 步）

以下命令在评测沙盒中把 `/skills/weekly-skill` 替换为实际安装路径。

**第 1 步｜契约初始化（必须最先做；第一次调用就写保底 result.json）**

```bash
python3 /skills/weekly-skill/scripts/contract_init.py \
  --input-dir /input --work-dir /app/work --output-dir /app/output
```

产物：`/app/work/answer_sheet.json`（答题纸）、`extracted_text.txt`（锚点
复验基准）、`extracted_index.json`（含各文件 SHA-256）、保底
`/app/output/result.json`（status=partial）。缺 case_id 会报错退出（退出码 2）。

**第 2 步｜六分面轮查并撰写候选 findings**

```bash
python3 /skills/weekly-skill/scripts/adjudicate.py scaffold \
  --work-dir /app/work --count 3
```

Agent 对照 `references/facet_coverage.md` 的六分面检查点逐一核查
`/app/work/extracted_text.txt`，把发现的问题按模板字段填入
`/app/work/findings_candidate.json`（original_text 必须逐字摘自原文，
每条先过"删除测试"，见 `references/false_positive_suppression.md`）；
同时在 `answer_sheet.json` 的 `facet_coverage` 区填写各分面状态并置
`agent_filled: true`，已知字段填 `contract_fields`。

**第 3 步｜机器复核（Pass 2 误报抑制）**

```bash
python3 /skills/weekly-skill/scripts/adjudicate.py check --work-dir /app/work
```

产物：`/app/work/adjudication_report.json`，每条 accepted / downgraded
（pending_review）/ rejected 及理由，豁免词表命中与 type-facet 不一致的
条目带 recheck 提示。对 downgraded/rejected 条目修正后可重跑本步
（agent 修订 findings_candidate.json 后再次 check，全程留痕）。

**第 4 步｜终稿渲染与诚实门终检（幂等，可重复运行）**

```bash
python3 /skills/weekly-skill/scripts/finalize.py \
  --work-dir /app/work --output-dir /app/output
```

动作：accepted findings 按 (facet 序, severity 序, 锚点位置, original_text)
排序并稳定编号 F001…；按 facet 分组、组内按 severity 排序重渲染
`review_report.md`；诚实门终检（契约字段全覆盖、null 必须有 null_reasons，
否则降 partial 并列出降级原因）；原子写入 `result.json` 与
`review_report.md`。打印一行验收摘要（findings 数/待复核数/降级原因）。

**第 5 步｜幂等复验（交付前自检）**

```bash
python3 /skills/weekly-skill/scripts/finalize.py \
  --work-dir /app/work --output-dir /app/output
python3 -c "import json; r=json.load(open('/app/output/result.json')); \
  print(sorted(r.keys())); print([f['id'] for f in r['findings']])"
```

确认重跑后 result.json 的 schema 键集与 findings 编号不变（稳定幂等），
并目检 `review_report.md`。

## 输出 schema

`/app/output/result.json`：顶层含 case_id 与 output_contract 全部字段：

- `case_id`：原 case.json 的 case_id（原样透传）；
- `status`：`complete` | `partial`（诚实门只降不升，partial 必附降级原因）；
- `review_report`：审查报告 markdown 全文（同步写入 review_report.md）；
- `findings`：accepted 条目数组，每条含 id（F001…）、facet、type、severity、
  location{file,section,anchor}、original_text、evidence、suggestion、
  recheck_hints；
- `sources`：`input_files` 数组（文件名 + SHA-256 + 抽取状态/错误）；
- `uncertainty`：字符串数组（回退说明、抽取错误、pending_review 明细等）；
- `change_log`：事件数组（init/finalize 留痕）；
- 额外字段 `null_reasons`：未知契约字段置 null 的原因说明。

facet/type/severity 枚举与锚点定义见 `references/severity_anchors.md`。

## 异常处置

| 异常 | 处置 |
| --- | --- |
| case.json 缺失/非 JSON/非 object | contract_init 退出码 2，stderr 说明 |
| 缺 case_id | 退出码 2，stderr 说明（不可降级） |
| output_contract 不识别 | 回退默认字段集，记 uncertainty，继续 |
| PDF 无 pdftotext / DOCX 解析失败 | 如实记录 extract_error，status 降 partial |
| findings_candidate.json 缺失/非法 JSON | adjudicate check 退出码 2，stderr 说明 |
| severity/type/facet 非法值 | 该条 rejected 并留痕，不影响其他条目 |
| original_text 锚点复验失败 | 该条降级 pending_review，不凭空补结论 |
| 契约字段无法填充 | 置 null + null_reasons；诚实门降 partial |
| 超长/时间不足 | 保底 partial result.json 已在第 1 步落盘；答题纸记 partially_checked 并说明已查范围 |

## 文件清单

```
SKILL.md                        本文件
scripts/contract_init.py        第 1 步：契约解析+抽取+答题纸+保底 result.json
scripts/adjudicate.py           第 2/3 步：scaffold 模板 + check 机械复核
scripts/finalize.py             第 4/5 步：幂等渲染+诚实门+原子落盘
references/contract_protocol.md 契约字段语义/答题纸协议/诚实门/原子写入与幂等
references/false_positive_suppression.md 误报抑制规则与删除测试
references/facet_coverage.md    六分面最低检查点与状态值
references/severity_anchors.md  四级严重度锚点与各 2 个示例
examples/                       合成示例（非正式案例结果）
GITHUB_URL.txt                  公开仓库链接
```
