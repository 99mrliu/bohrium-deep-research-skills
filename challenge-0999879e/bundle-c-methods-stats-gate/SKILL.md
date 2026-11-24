---
name: methods-stats-gate
description: 论文方法设计与统计报告完备性门禁——以确定性模式扫描建立"统计报告要素矩阵"，再按 16 条清单逐条登记 pass/fail_reporting/fail_design/unable_to_check，把"方法有缺陷"与"报告不全"系统分开并给出原文定位；适用于审查含统计推断的生物医学/实验类稿件，不适用于无需统计的纯理论、纯定性稿件与事实真伪核验。
---

# bundle-c-methods-stats-gate：方法设计与统计报告完备性门禁

## 核心思想

笼统的"统计报告不规范"无法交办。本 bundle 做两件事：

1. **要素矩阵**（`stats_gate.py`）：把稿件按小节切分，用确定性正则扫描
    12 类统计报告要素（样本量、检验名称、p 值、CI、效应量、多重比较校正、
    随机化、盲法、对照、重复、剔除、软件、误差棒）的存在性，产出
    "要素 × 小节 × 原文引证"矩阵。哪些要素在哪节出现/缺失一目了然。
2. **清单门禁**（`gate_check.py`）：按 16 条清单逐条判定，状态严格四选一：
    - `pass`：满足；
    - `fail_reporting`：方法可接受但报告不全（作者补写即可，minor/major）；
    - `fail_design`：方法本身有缺陷（补写无法挽回，major/critical）；
    - `unable_to_check`：文本不足以下结论，如实登记、不臆断。

    关键区分示例：只有"证明药物有效"式因果结论却无任何对照组 →
    `fail_design critical`；做了 Bonferroni 校正但方法里没写校正名称 →
    `fail_reporting minor`；全文没提盲法 → `unable_to_check`（缺失声明≠未实施）。

深查面 = 方法设计 + 统计报告；其余四分面（事实核验、引用支持、论证链、
学术规范）按 `references/facet_coverage.md` 最低检查点轮查登记，不越界深查。

## 适用边界

- **适用**：含假设检验/组间比较的实验研究、临床研究、观察性研究稿件的
  方法学与统计报告完备性审查；可审查中文或英文稿件。
- **不适用**：纯理论推导、数学证明、纯定性研究（无统计推断，清单多不适用）；
  事实真伪核验、引文-主张逐条对应、论证链深查（本 bundle 只做最低检查点，
  需配合其他 bundle 或人工）。
- **不能做的事**：确定性规则只覆盖清单 16 条的模式证据；任何超出模式的
  判断（如检验真的选对没有）必须交人工，宁可 `unable_to_check` 不臆断。

## 运行时契约

- Skill 安装于 `/skills/weekly-skill`；脚本一律
  `python3 /skills/weekly-skill/scripts/<name>.py` 调用，仅用 Python 3 标准库。
- 输入：`/input/case.json`、`/input/task.md`，稿件在 `/input` 下
  （PDF/DOCX/MD/TXT/TeX）。PDF 用 `pdftotext` 抽取（`shutil.which` 检测，
  缺失则在 uncertainty 如实记 extract_error）；DOCX 用 zipfile 解包；
  统一 `utf-8, errors=replace`。
- `case.json` schema 未知：`output_contract` 兼容 list 与 dict，缺省回退
  `["case_id","status","review_report","findings","sources","uncertainty","change_log"]`
  并在 uncertainty 说明。
- 工作目录 `/app/work`；最终成果 `/app/output/result.json`（必含原 case_id
  与 output_contract 全部字段）+ `/app/output/review_report.md`。
- 预算紧：第一步 `stats_gate.py` 即写出保底 partial result.json，之后增量改进。
- 诚实：不编造结论/定位；fail 必须带原文引证（小节+偏移+句子）或显式
  absent 说明；校验不通过非零退出。

## 分步工作流（确切命令行）

以下 `<B>` 为 bundle 绝对路径，评测时即 `/skills/weekly-skill`。

```bash
# 1. 文本抽取 + 要素矩阵 + 保底 partial result.json
python3 <B>/scripts/stats_gate.py --input-dir /input --work-dir /app/work --output-dir /app/output

# 2. 生成清单登记模板（也可跳过，直接 run 自动填充）
python3 <B>/scripts/gate_check.py scaffold --input-dir /input --work-dir /app/work

# 3. 按确定性规则逐条判定并登记证据（覆盖模板）
python3 <B>/scripts/gate_check.py run --input-dir /input --work-dir /app/work

# 4. 登记完整性校验（fail 必须有引证或 absent 说明；不通过则非零退出）
python3 <B>/scripts/gate_check.py validate --work-dir /app/work

# 5. 汇总 → result.json + review_report.md（契约对齐 + 诚实门 + 原子写）
python3 <B>/scripts/build_result.py --input-dir /input --work-dir /app/work --output-dir /app/output
```

本地复现（以仓库内 synthetic-input 为例）：

```bash
SB=$(mktemp -d) && mkdir -p $SB/input $SB/app/work $SB/app/output
cp <B>/examples/synthetic-input/* $SB/input/
python3 <B>/scripts/stats_gate.py --input-dir $SB/input --work-dir $SB/app/work --output-dir $SB/app/output
python3 <B>/scripts/gate_check.py scaffold --input-dir $SB/input --work-dir $SB/app/work
python3 <B>/scripts/gate_check.py run --input-dir $SB/input --work-dir $SB/app/work
python3 <B>/scripts/gate_check.py validate --work-dir $SB/app/work
python3 <B>/scripts/build_result.py --input-dir $SB/input --work-dir $SB/app/work --output-dir $SB/app/output
```

## 输出 schema

`result.json`（字段以 case.json output_contract 为准，缺省含）：

- `case_id`：原样回抄；
- `status`：`completed`（无抽取失败）/ `partial`（有抽取失败或重大不确定）；
- `review_report`：一句话摘要，正文在 review_report.md；
- `findings[]`：`finding_id`（F-01…，按严重度+清单序稳定编号）、`checklist_id`、
  `facet`、`issue_type`（design_flaw / reporting_gap）、`severity`
  （critical/major/minor）、`title`、`evidence_quote`、`location`
  （section/offset/absent_note）、`basis`、`disposition`；
- `sources[]`：稿件文件 + SHA-256 + 判定依据 references；
- `uncertainty[]`：抽取失败、契约回退、unable_to_check 汇总、待人工复核说明；
- `change_log[]`：各脚本增量记录；
- 附加：`stats_matrix`（要素存在性摘要）、`checklist_summary`、
  `facet_coverage`（六分面状态）。

`review_report.md`：固定分组——一、方法缺陷（fail_design）；二、报告不全
（fail_reporting）；三、待复核（unable_to_check）；四、通过项与要素矩阵摘要；
五、六分面覆盖登记。

## 异常处置

- `pdftotext` 不存在 / PDF 抽取失败：该文件所有依赖条目记 `unable_to_check`，
  uncertainty 记 extract_error，status 降为 partial。
- `case.json` 缺失或损坏：case_id 记 `unknown`，uncertainty 说明。
- 登记校验失败（缺状态/缺依据/fail 无引证）：validate 与 build_result 均非零
  退出并打印原因，**不产出看似完整的结果**。
- 无稿件文本：stats_gate 警告并全要素记 absent；gate_check 全部 unable_to_check；
  build_result 仍产出 partial result.json（保底）。

## 文件清单

```
SKILL.md                          本文件
GITHUB_URL.txt                    仓库链接
scripts/stats_gate.py             文本抽取 + 要素矩阵 + 保底 partial result
scripts/gate_check.py             清单 scaffold / run / validate
scripts/build_result.py           汇总 → result.json + review_report.md
references/stats_reporting_checklist.md   16 条清单 + 防误报规则 R1–R5
references/methods_severity_rubric.md     critical/major/minor 判据
references/facet_coverage.md              六分面最低检查点与状态值
examples/README.md                合成示例说明
examples/synthetic-input/         case.json + task.md + manuscript.md
examples/synthetic-output/        真实跑出的 result.json + review_report.md
```
